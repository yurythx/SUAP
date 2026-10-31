"""Fluxo: fronteira de permissão por papel, verificada pela resposta HTTP real.

Por que este fluxo: regressão de `permissions.yaml` / `sync_permissions` / decorator de view
é silenciosa — a tela simplesmente passa a abrir (ou a fechar) para quem não devia, e
nenhum teste de unidade de model pega isso. Aqui um servidor sem grupo e um superusuário
atacam as mesmas URLs e as respostas são comparadas.

A verificação é por **status HTTP da URL**, não por varredura de menu: o menu do SUAP é
gerado por `menu.yaml` com marcação que muda de tema para tema, e testar ausência de item
de menu confundiria "não tem permissão" com "mudou o HTML do menu". O status é o contrato.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Só superusuário: a view faz `raise PermissionDenied` explícito (djtools/views.py).
URL_SO_SUPERUSER = '/djtools/give_permission/'
SERVIDOR_SEM_GRUPO = '7000001'  # criado pelo `e2e_seed` de `tests/e2e/conftest.py`


def test_servidor_comum_e_barrado_em_tela_de_superusuario(logado):
    page = logado(SERVIDOR_SEM_GRUPO)
    resposta = page.request.get(URL_SO_SUPERUSER)
    assert resposta.status == 403, f'servidor sem grupo deveria levar 403, veio {resposta.status}'


def test_superusuario_acessa_a_mesma_tela(logado):
    page = logado('admin')
    page.goto(URL_SO_SUPERUSER)
    expect(page.get_by_role('heading', name='Atribuir Permissão')).to_be_visible()


def test_anonimo_e_redirecionado_para_o_login(new_context):
    """Sem `storage_state` de propósito: o teste precisa ser anônimo."""
    page = new_context().new_page()
    page.goto(URL_SO_SUPERUSER)
    # `LOGIN_URL = '/accounts/login/'` (suap/settings_base.py); o marker do template de
    # login é a asserção estável, não a URL final.
    expect(page.locator('meta[name=test_suap_login]')).to_have_count(1)
