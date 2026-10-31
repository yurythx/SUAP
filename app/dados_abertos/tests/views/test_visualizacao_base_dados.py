"""Visualização da base de dados e do recurso (``get_absolute_url``) e a listagem de eventos do LAI."""

import pytest
from django.urls import reverse

from dados_abertos.enums import SituacaoLAI

from dados_abertos.forms import BaseDadosForm
from rh.tests.factories import ServidorFactory
from dados_abertos.tests.factories import (
    AtualizacaoBaseDadosFactory,
    BaseDadosFactory,
    DeliberacaoLAIFactory,
    OrganizacaoFactory,
    PDABaseDadosFactory,
    RecursoDadosFactory,
)


@pytest.fixture
def base(db):
    base = BaseDadosFactory(titulo='Auxílios estudantis', ods=[4])
    RecursoDadosFactory(dataset=base, nome='Auxílios 2026')
    DeliberacaoLAIFactory(pda_base_dados=PDABaseDadosFactory(base_dados=base), texto='Parecer interno do LAI.')
    return base


def test_superusuario_ve_todas_as_secoes_da_base(admin_client, base):
    html = admin_client.get(base.get_absolute_url()).content.decode()

    for aba in ('Dados gerais', 'Recursos', 'PDAs relacionados', 'Matriz de priorização', 'Linha do tempo do LAI', 'Atualizações automáticas'):
        assert f'data-title="{aba}"' in html
    # Contrato com os get_absolute_url dos models relacionados, que abrem a aba por ?tab=.
    for aba in ('pdas', 'matriz', 'lai', 'atualizacoes'):
        assert f'data-tab="{aba}"' in html
    recurso = base.recursos.get()
    # Os ícones da tabela de recursos levam às URLs reais (a tag `icon` não resolve variável sem aspas).
    assert f'<a href="{recurso.get_absolute_url()}" class="icon icon-view' in html
    assert f'<a href="{reverse("admin:dados_abertos_recursodados_change", args=[recurso.pk])}" class="icon icon-edit' in html
    assert '4 - Educação de Qualidade' in html
    assert 'Parecer interno do LAI.' in html


def test_grupo_de_trabalho_ve_a_base_mas_nao_os_pareceres_do_lai(cliente_membro_gt, base):
    resposta = cliente_membro_gt.get(base.get_absolute_url())

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert 'data-title="Recursos"' in html
    assert 'Linha do tempo do LAI' not in html
    assert 'Parecer interno do LAI.' not in html


def test_recurso_mostra_a_previa_dos_dados(admin_client, base):
    recurso = base.recursos.get()

    html = admin_client.get(recurso.get_absolute_url()).content.decode()

    assert '<th>id</th>' in html
    assert '<td>10</td>' in html


@pytest.mark.parametrize(('listagem', 'aba'), [('deliberacaolai', 'lai'), ('atualizacaobasedados', 'atualizacoes')])
def test_historico_somente_leitura_abre_a_aba_da_base_e_nao_a_edicao_negada(admin_client, base, listagem, aba):
    AtualizacaoBaseDadosFactory(base_dados=base)

    html = admin_client.get(reverse(f'admin:dados_abertos_{listagem}_changelist')).content.decode()

    assert f'{base.get_absolute_url()}?tab={aba}' in html
    assert '/change/' not in html.split('<tbody>')[1].split('</tbody>')[0]


def test_extras_livres_fora_do_formato_de_dicionario_nao_derrubam_as_telas(admin_client):
    # Formato do próprio CKAN colado no campo: JSON válido, mas lista em vez de dicionário.
    base = BaseDadosFactory(extras=[{'key': 'fonte', 'value': 'SUAP'}], cobertura_espacial='ESTADUAL')

    for url in (base.get_absolute_url(), reverse('admin:dados_abertos_basedados_change', args=[base.pk])):
        resposta = admin_client.get(url)
        assert resposta.status_code == 200
        assert '<dt>coberturaEspacial</dt><dd>ESTADUAL</dd>' in resposta.content.decode()


def test_base_fora_de_pda_nao_aparece_como_aguardando_o_lai(admin_client):
    base = BaseDadosFactory()

    html = admin_client.get(base.get_absolute_url()).content.decode()

    assert 'Fora de PDA' in html
    assert 'Aguardando o LAI' not in html


def test_form_recusa_extras_livres_que_nao_sejam_objeto_json(db):
    base = BaseDadosFactory(organizacao=OrganizacaoFactory())
    dados = {'nome': base.nome, 'titulo': base.titulo, 'organizacao': base.organizacao_id, 'estado': base.estado}

    form = BaseDadosForm(data={**dados, 'extras': '[{"key": "fonte", "value": "SUAP"}]'}, instance=base)

    assert not form.is_valid()
    assert 'extras' in form.errors


def test_base_devolvida_mostra_a_devolucao_e_nao_que_aguarda_o_lai(admin_client):
    base = BaseDadosFactory()
    PDABaseDadosFactory(base_dados=base, situacao_lai=SituacaoLAI.DEVOLVIDO)

    html = admin_client.get(base.get_absolute_url()).content.decode()

    assert SituacaoLAI.LABELS[SituacaoLAI.DEVOLVIDO] in html
    assert 'Aguardando o LAI' not in html


@pytest.mark.usefixtures('sync_permissions')
def test_servidor_sem_permissao_nao_ve_a_base_nem_o_recurso(client, base):
    servidor = ServidorFactory()
    client.force_login(servidor.get_user())

    for url in (base.get_absolute_url(), base.recursos.get().get_absolute_url()):
        assert client.get(url).status_code == 403
