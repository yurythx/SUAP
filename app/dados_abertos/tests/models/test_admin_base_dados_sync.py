"""Testes das actions de sincronização do admin de bases de dados."""

import pytest
from django.contrib import admin as django_admin

from dados_abertos.admin.base_dados import BaseDadosAdmin
from dados_abertos.models import BaseDados


class ServicoCKANFake:
    """Substituto de ``get_ckan_service()`` — só carrega as credenciais."""

    base_url = 'https://ckan.exemplo.br'
    api_key = 'chave'


@pytest.fixture
def chamadas(monkeypatch):
    """Captura os argumentos com que o serviço de sincronização é chamado."""
    registro: list[dict] = []

    def _fake(queryset, base_url, api_key, *, force_file=False):
        registro.append({'bases': list(queryset), 'force_file': force_file})
        return len(registro), 0

    monkeypatch.setattr('dados_abertos.admin.base_dados.get_ckan_service', ServicoCKANFake)
    monkeypatch.setattr('dados_abertos.admin.base_dados.sync_dataset_resources_with_ckan', _fake)
    monkeypatch.setattr(BaseDados, 'lai_liberada_para_sync', lambda self: True)
    monkeypatch.setattr(BaseDadosAdmin, 'message_user', lambda self, *args, **kwargs: None)
    return registro


@pytest.fixture
def base(db):
    return BaseDados.objects.create(nome='contratos', titulo='Contratos', id_remoto='pkg-1')


def _executar(nome_da_action, base):
    admin_de_bases = BaseDadosAdmin(BaseDados, django_admin.site)
    getattr(admin_de_bases, nome_da_action)(None, BaseDados.objects.filter(pk=base.pk))


@pytest.mark.django_db
def test_action_normal_nao_forca_o_reenvio(base, chamadas):
    """A action padrão deixa o serviço decidir pelo diff."""
    _executar('action_sync_resources_ckan', base)

    assert len(chamadas) == 1
    assert chamadas[0]['force_file'] is False
    assert chamadas[0]['bases'] == [base]


@pytest.mark.django_db
def test_action_forcada_propaga_o_force_file(base, chamadas):
    """A action forçada precisa mesmo chegar com ``force_file=True`` no serviço.

    Sem esta trava a variante forçada vira uma duplicata inofensiva da normal: o
    ``force_file`` só muda o comportamento dentro de ``_precisa_reenviar_arquivo``, e
    perder o flag no caminho não quebra nada visível.
    """
    _executar('action_sync_resources_ckan_forcado', base)

    assert len(chamadas) == 1
    assert chamadas[0]['force_file'] is True


@pytest.mark.django_db
def test_bases_bloqueadas_pelo_lai_nao_sao_sincronizadas(base, chamadas, monkeypatch):
    """A trava do LAI vale igual na variante forçada."""
    monkeypatch.setattr(BaseDados, 'lai_liberada_para_sync', lambda self: False)

    _executar('action_sync_resources_ckan_forcado', base)

    assert chamadas == []
