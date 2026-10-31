"""Testes do admin de Base de Dados: actions, permissões e busca."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from dados_abertos.admin.base_dados import BaseDadosAdmin
from dados_abertos.forms import BaseDadosForm
from dados_abertos.models import BaseDados
from dados_abertos.tests.factories import BaseDadosFactory, OrganizacaoFactory


class ServicoCKANFake:
    base_url = 'https://ckan.exemplo.br'
    api_key = 'chave'


@pytest.fixture
def base(db):
    return BaseDados.objects.create(nome='contratos', titulo='Contratos', id_remoto='pkg-1')


@pytest.fixture
def admin_instrumentado(monkeypatch):
    """Admin com CKAN e sincronização substituídos, registrando as chamadas."""
    chamadas = []

    def _sync(queryset, base_url, api_key, *, force_file=False):
        chamadas.append({'bases': [b.pk for b in queryset], 'force_file': force_file})
        return len(chamadas), 0

    monkeypatch.setattr('dados_abertos.admin.base_dados.get_ckan_service', ServicoCKANFake)
    monkeypatch.setattr('dados_abertos.admin.base_dados.sync_dataset_resources_with_ckan', _sync)

    admin = BaseDadosAdmin(BaseDados, None)
    monkeypatch.setattr(admin, 'message_user', lambda *a, **kw: None)
    return admin, chamadas


def _requisicao():
    pedido = RequestFactory().post('/admin/dados_abertos/basedados/')
    pedido.user = None
    return pedido


def _liberar_lai(monkeypatch):
    """A sincronização é bloqueada por base não liberada pelo LAI; aqui isso não está sob teste."""
    monkeypatch.setattr(BaseDados, 'lai_liberada_para_sync', lambda self: True)


def test_action_normal_nao_forca_reenvio(base, admin_instrumentado, monkeypatch):
    admin, chamadas = admin_instrumentado
    _liberar_lai(monkeypatch)

    admin.action_sync_resources_ckan(_requisicao(), BaseDados.objects.filter(pk=base.pk))

    assert chamadas == [{'bases': [base.pk], 'force_file': False}]


def test_action_forcada_reenvia_o_arquivo(base, admin_instrumentado, monkeypatch):
    """Saída pela interface para o caso em que o arquivo sumiu do CKAN sem o SUAP saber."""
    admin, chamadas = admin_instrumentado
    _liberar_lai(monkeypatch)

    admin.action_sync_resources_ckan_forcado(_requisicao(), BaseDados.objects.filter(pk=base.pk))

    assert chamadas == [{'bases': [base.pk], 'force_file': True}]


def test_as_duas_actions_estao_registradas():
    """Sem registro em `actions` a opção não aparece no seletor do admin."""
    assert 'action_sync_resources_ckan' in BaseDadosAdmin.actions
    assert 'action_sync_resources_ckan_forcado' in BaseDadosAdmin.actions


def test_action_forcada_respeita_o_bloqueio_do_lai(base, admin_instrumentado, monkeypatch):
    """Forçar o reenvio não pode furar a análise LAI: base não liberada não vai ao CKAN."""
    admin, chamadas = admin_instrumentado
    monkeypatch.setattr(BaseDados, 'lai_liberada_para_sync', lambda self: False)

    admin.action_sync_resources_ckan_forcado(_requisicao(), BaseDados.objects.filter(pk=base.pk))

    assert chamadas == [], 'base bloqueada pelo LAI não pode ser sincronizada nem no modo forçado'


def test_membro_do_grupo_de_trabalho_so_consulta_as_bases(cliente_membro_gt, base):
    """Quem só pode ver não recebe ícones nem actions de sincronizar, apenas o de visualizar."""
    resposta = cliente_membro_gt.get(reverse('admin:dados_abertos_basedados_changelist'))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert reverse('admin:dados_abertos_basedados_sync', args=[base.pk]) not in html
    assert 'icon-edit' not in html
    assert 'icon-view' in html
    assert 'action_sync_ckan' not in html


def test_busca_encontra_base_por_parte_de_uma_tag(admin_client):
    """``tags`` é um array de texto: a busca casa um trecho de qualquer uma das tags (Sentry SUAP-VW5)."""
    com_tag = BaseDadosFactory(titulo='Contratos', tags=['licitacao', 'transparencia'])
    sem_tag = BaseDadosFactory(titulo='Servidores', tags=['pessoal'])

    resposta = admin_client.get(reverse('admin:dados_abertos_basedados_changelist'), {'q': 'transpar'})

    assert resposta.status_code == 200
    encontradas = list(resposta.context['cl'].result_list)
    assert com_tag in encontradas
    assert sem_tag not in encontradas


def test_ods_em_colunas_sao_gravados_e_a_tela_mostra_os_extras_que_sobem(admin_client):
    base = BaseDadosFactory(organizacao=OrganizacaoFactory())
    dados = {
        'nome': base.nome,
        'titulo': base.titulo,
        'organizacao': base.organizacao_id,
        'estado': base.estado,
        'cobertura_espacial': 'ESTADUAL',
        'ods': ['4', '10'],
    }
    form = BaseDadosForm(data=dados, instance=base)
    assert form.is_valid(), form.errors
    form.save()

    html = admin_client.get(reverse('admin:dados_abertos_basedados_change', args=[base.pk])).content.decode()

    assert BaseDados.objects.get(pk=base.pk).ods == [4, 10]
    # Widget que o tema distribui em colunas, sem o "Marcar todos".
    assert '<ul class="checkboxes">' in html
    assert 'Marcar todos' not in html
    assert '<dt>coberturaEspacial</dt><dd>ESTADUAL</dd>' in html
    assert '<dt>ods</dt><dd>4 - ' in html
