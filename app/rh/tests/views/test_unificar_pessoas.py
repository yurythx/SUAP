"""Tela ``/rh/unificar_pessoas/``: o superusuário une duas PFs escolhidas à mão (prévia, depois confirmação)."""

import re
from datetime import date

import pytest

from django.db import connection
from django.test.utils import CaptureQueriesContext

from comum.models import Comentario, ContatoEmergencia, PessoaTelefone
from comum.tests.factories import PrestadorServicoFactory, UserFactory
from djtools.utils import anonimizar_documento
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaFisica
from rh.tests.factories import PessoaFisicaFactory, ServidorFactory, SetorFactory

URL = '/rh/unificar_pessoas/'


@pytest.fixture
def superusuario(db):
    return UserFactory(is_superuser=True)


def test_previa_nao_altera_e_confirmacao_unifica(client, superusuario):
    fica = PessoaFisicaFactory(nome_mae='Maria')
    sai = PessoaFisicaFactory(nome_mae='Maria José', nascimento_data=date(1971, 4, 7))
    telefone = PessoaTelefone.objects.create(pessoa=sai, numero='84999999999')
    comentario = Comentario.objects.create(content_object=sai, texto='da pessoa que sai')
    client.force_login(superusuario)

    previa = client.post(URL, {'sobrevivente': fica.pk, 'perdedora': sai.pk})

    assert previa.status_code == 200
    assert 'Maria José' in previa.content.decode()
    assert PessoaFisica.objects.filter(pk=sai.pk).exists()

    client.post(URL, {'sobrevivente': fica.pk, 'perdedora': sai.pk, 'confirmar': 'on'})

    assert not PessoaFisica.objects.filter(pk=sai.pk).exists()
    fica.refresh_from_db()
    assert (fica.nascimento_data, fica.nome_mae) == (date(1971, 4, 7), 'Maria')
    telefone.refresh_from_db()
    comentario.refresh_from_db()
    assert telefone.pessoa_id == comentario.object_id == fica.pk
    mesclada = D.objects.get(pf_id=sai.pk, acao=D.MESCLADA)
    assert (mesclada.sobrevivente_id, mesclada.documento, mesclada.motivo) == (fica.pk, sai.cpf, f'unificação manual por {superusuario.username}')
    assert mesclada.aplicado_em is not None
    assert D.objects.get(pf_id=sai.pk, acao=D.CAMPO_DESCARTADO, campo='nome_mae').valor_original == 'Maria José'


def test_recusa_pessoa_que_fica_sem_documento_quando_a_outra_tem(client, superusuario):
    fica, sai = PessoaFisicaFactory(), PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=fica.pk).update(cpf=None, documento_identificador=f'CONFLITO-{fica.pk}-{sai.cpf}')
    client.force_login(superusuario)

    resposta = client.post(URL, {'sobrevivente': fica.pk, 'perdedora': sai.pk, 'confirmar': 'on'})

    assert 'inverta as duas' in resposta.content.decode()
    assert PessoaFisica.objects.filter(pk__in=[fica.pk, sai.pk]).count() == 2


def test_falha_nao_altera_nada(client, superusuario):
    fica, sai = PessoaFisicaFactory(), PessoaFisicaFactory()
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
    for pessoa in (fica, sai):
        ContatoEmergencia.objects.create(pessoa_fisica=pessoa, nome_contato='Mãe', telefone='84999999999')
    client.force_login(superusuario)

    resposta = client.post(URL, {'sobrevivente': fica.pk, 'perdedora': sai.pk, 'confirmar': 'on'}, follow=True)

    assert 'Nada foi alterado' in resposta.content.decode()
    assert PessoaFisica.objects.filter(pk__in=[fica.pk, sai.pk]).count() == 2
    assert ContatoEmergencia.objects.get(pessoa_fisica=sai).pessoa_fisica_id == sai.pk
    assert not D.objects.filter(pf_id=sai.pk).exists()


def test_previa_omite_senha_do_ponto(client, superusuario):
    fica, sai = PessoaFisicaFactory(), PessoaFisicaFactory()
    PessoaFisica.objects.filter(pk=sai.pk).update(senha_ponto='segredo123')
    client.force_login(superusuario)

    conteudo = client.post(URL, {'sobrevivente': fica.pk, 'perdedora': sai.pk}).content.decode()

    assert '(valor omitido)' in conteudo
    assert 'segredo123' not in conteudo


def test_so_superusuario(client, sync_permissions):
    client.force_login(ServidorFactory(setor=SetorFactory()).get_user())
    assert client.get(URL).status_code == 403


def test_autocomplete_mostra_pessoa_sem_papel(client, superusuario):
    """A PF sem servidor/aluno/prestador quebrava o ``get_ext_combo_template`` e o select2 mostrava "Buscando..."."""
    PessoaFisicaFactory(nome='Fulana Sem Papel')
    client.force_login(superusuario)
    control = re.search(r"control: '([^']+)'", client.get(URL).content.decode()).group(1)

    itens = client.post('/json/rh/pessoafisica/', {'q': 'Fulana', 'control': control}).json()['items']

    assert ['class="person"' in item['html'] and 'Fulana Sem Papel' in item['html'] for item in itens] == [True]


def _controle_do_autocomplete(client) -> str:
    return re.search(r"control: '([^']+)'", client.get(URL).content.decode()).group(1)


def test_autocomplete_lista_os_vinculos(client, superusuario):
    prestador = PrestadorServicoFactory(pessoa_fisica__nome='Beltrano Prestador')
    client.force_login(superusuario)

    [item] = client.post('/json/rh/pessoafisica/', {'q': 'Beltrano', 'control': _controle_do_autocomplete(client)}).json()['items']

    username = prestador.get_vinculo().user.username  # a matrícula do prestador é o CPF: sai anonimizada
    assert f'<dd>{prestador._meta.verbose_name}: {anonimizar_documento(username)}</dd>' in item['html']
    assert username not in item['html']


def test_autocomplete_nao_consulta_por_pessoa(client, superusuario):
    client.force_login(superusuario)
    control = _controle_do_autocomplete(client)

    def consultas() -> int:
        with CaptureQueriesContext(connection) as contexto:
            client.post('/json/rh/pessoafisica/', {'q': 'Ciclano', 'control': control})
        return len(contexto.captured_queries)

    PrestadorServicoFactory(pessoa_fisica__nome='Ciclano Um')
    com_uma = consultas()
    PrestadorServicoFactory(pessoa_fisica__nome='Ciclano Dois')
    PrestadorServicoFactory(pessoa_fisica__nome='Ciclano Três')

    assert consultas() == com_uma


def test_autocomplete_anonimiza_matricula_de_pessoa_separada(client, superusuario):
    prestador = PrestadorServicoFactory(pessoa_fisica__nome='Fulano Separado')
    pessoa = prestador.pessoa_fisica
    username = prestador.get_vinculo().user.username
    PessoaFisica.objects.filter(pk=pessoa.pk).update(cpf=None, documento_identificador=f'CONFLITO-{pessoa.pk}-{pessoa.cpf}')
    client.force_login(superusuario)

    [item] = client.post('/json/rh/pessoafisica/', {'q': 'Separado', 'control': _controle_do_autocomplete(client)}).json()['items']

    assert username not in item['html']
