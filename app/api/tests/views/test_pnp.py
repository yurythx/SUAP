from types import SimpleNamespace

import pytest

from api.schemas.pnp import ServidorNaoDocenteSchema
from djtools.middleware import threadlocals as tl
from pnp.models import EstruturaPNP
from rh.models import Servidor, Setor, Situacao
from rh.tests.factories import SituacaoFactory

URL = '/api/pnp/servidores-nao-docentes/'


@pytest.fixture
def dados_pnp(servidor_a, servidor_b, campus_a) -> SimpleNamespace:
    """Marca os servidores do substrato como docente e não docente e devolve os envolvidos.

    ``categoria`` é uma property derivada de ``eh_docente``/``eh_tecnico_administrativo``,
    então o que o teste ajusta são esses dois campos.
    """
    tl.context.user = None
    campus = campus_a
    Servidor.objects.update(eh_docente=False, eh_tecnico_administrativo=False)

    tecnico = servidor_a
    Servidor.objects.filter(pk=tecnico.pk).update(eh_tecnico_administrativo=True, ativo=True, situacao=SituacaoFactory())

    docente = servidor_b
    Servidor.objects.filter(pk=docente.pk).update(eh_docente=True)

    return SimpleNamespace(campus=campus, tecnico=Servidor.objects.get(pk=tecnico.pk), docente=Servidor.objects.get(pk=docente.pk))


def get_resposta(api_client, dados_pnp):
    """Chama o endpoint autenticado como o TrustedAppAuth espera."""
    return api_client.get(URL, user=dados_pnp.tecnico.get_user(), HTTP_AUTHORIZATION='Bearer fake-token')


def get_item(resposta, matricula: str) -> dict | None:
    """Localiza um servidor na resposta, que vem paginada em ``results``."""
    return next((item for item in resposta.json()['results'] if item['matricula'] == matricula), None)


def _servidor_fake(ativo, codigo_situacao):
    return SimpleNamespace(ativo=ativo, situacao=SimpleNamespace(codigo=codigo_situacao))


def test_situacao_ativo_para_servidor_vinculado_em_situacao_ativa():
    assert ServidorNaoDocenteSchema.resolve_situacao(_servidor_fake(True, Situacao.ATIVO_PERMANENTE)) == 'Ativo'


def test_situacao_inativo_para_aposentado():
    assert ServidorNaoDocenteSchema.resolve_situacao(_servidor_fake(True, Situacao.APOSENTADOS)) == 'Inativo'


def test_situacao_inativo_para_servidor_sem_vinculo():
    assert ServidorNaoDocenteSchema.resolve_situacao(_servidor_fake(False, Situacao.ATIVO_PERMANENTE)) == 'Inativo'


@pytest.mark.django_db
def test_endpoint_exige_autenticacao(client, dados_pnp):
    """O endpoint usa TrustedAppAuth: sem token, não devolve a listagem."""
    assert client.get(URL).status_code == 401


@pytest.mark.django_db
def test_docente_nao_entra_na_listagem(api_client, dados_pnp):
    resposta = get_resposta(api_client, dados_pnp)

    assert get_item(resposta, dados_pnp.tecnico.matricula) is not None
    assert get_item(resposta, dados_pnp.docente.matricula) is None


@pytest.mark.django_db
def test_campos_retornados_do_servidor(api_client, dados_pnp):
    EstruturaPNP.objects.create(codigo='26435.2408102.01.001', nome='Campus A0', uo=dados_pnp.campus)

    item = get_item(get_resposta(api_client, dados_pnp), dados_pnp.tecnico.matricula)

    assert item['id'] == dados_pnp.tecnico.id
    assert item['cpf'] == dados_pnp.tecnico.pessoa_fisica.cpf
    assert item['categoria_funcional'] == 'tecnico_administrativo'
    assert item['situacao'] == 'Ativo'
    assert item['estrutura'] == '26435.2408102.01.001'


@pytest.mark.django_db
def test_estrutura_nula_quando_a_unidade_ainda_nao_foi_importada(api_client, dados_pnp):
    """Estado logo após o deploy: as unidades existem, mas nenhuma EstruturaPNP foi importada."""
    assert not EstruturaPNP.objects.exists()

    resposta = get_resposta(api_client, dados_pnp)

    assert resposta.status_code == 200
    assert get_item(resposta, dados_pnp.tecnico.matricula)['estrutura'] is None


@pytest.mark.django_db
def test_estrutura_nula_para_servidor_sem_setor(api_client, dados_pnp):
    EstruturaPNP.objects.create(codigo='26435.2408102.01.001', nome='Campus A0', uo=dados_pnp.campus)
    Servidor.objects.filter(pk=dados_pnp.tecnico.pk).update(setor=None)

    assert get_item(get_resposta(api_client, dados_pnp), dados_pnp.tecnico.matricula)['estrutura'] is None


@pytest.mark.django_db
def test_estrutura_nula_para_setor_sem_unidade(api_client, dados_pnp):
    EstruturaPNP.objects.create(codigo='26435.2408102.01.001', nome='Campus A0', uo=dados_pnp.campus)
    setor_solto = Setor.objects.create(nome='SETOR SEM UO', sigla='SSU')
    Servidor.objects.filter(pk=dados_pnp.tecnico.pk).update(setor=setor_solto)

    assert get_item(get_resposta(api_client, dados_pnp), dados_pnp.tecnico.matricula)['estrutura'] is None


@pytest.mark.django_db
def test_aposentado_aparece_como_inativo(api_client, dados_pnp):
    aposentado, _ = Situacao.objects.get_or_create(codigo=Situacao.APOSENTADOS, defaults={'nome': 'Aposentado', 'nome_siape': 'APOSENTADO'})
    Servidor.objects.filter(pk=dados_pnp.tecnico.pk).update(situacao=aposentado)

    assert get_item(get_resposta(api_client, dados_pnp), dados_pnp.tecnico.matricula)['situacao'] == 'Inativo'


@pytest.mark.django_db
def test_resultado_ordenado_por_id(api_client, dados_pnp):
    ids = [item['id'] for item in get_resposta(api_client, dados_pnp).json()['results']]

    assert ids == sorted(ids)


@pytest.mark.django_db
def test_servidor_sem_categoria_definida_entra_na_listagem(api_client, dados_pnp):
    """``eh_docente`` é anulável, e quem está com ele nulo também não é docente.

    Com ``filter(eh_docente=False)`` esses servidores sumiam da listagem — 1.291 dos 9.017
    da base de desenvolvimento.
    """
    Servidor.objects.filter(pk=dados_pnp.tecnico.pk).update(eh_docente=None)

    assert get_item(get_resposta(api_client, dados_pnp), dados_pnp.tecnico.matricula) is not None


def test_openapi_declara_os_campos_derivados_como_anulaveis():
    """Os campos vindos de travessia de relacionamento podem vir nulos; o contrato precisa dizê-lo."""
    from suap.api import api

    propriedades = api.get_openapi_schema()['components']['schemas']['ServidorNaoDocenteSchema']['properties']

    for campo in ('cpf', 'estrutura', 'categoria_funcional'):
        tipos = {variante.get('type') for variante in propriedades[campo].get('anyOf', [])}
        assert tipos == {'string', 'null'}, f'{campo} deveria ser anulável no OpenAPI, veio {propriedades[campo]}'
