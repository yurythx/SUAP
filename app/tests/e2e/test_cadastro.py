"""Fluxo: cadastro completo pela UI (``ModelAdminPlus``), do formulário ao objeto salvo.

Por que este fluxo: é o caminho felizes mais repetido do SUAP — abrir listagem, clicar em
"Adicionar", preencher, salvar, ver o objeto. Cobre a pilha inteira: menu/listagem do
``ModelAdminPlus``, o formset inline que toda tela de cadastro carrega, a validação de
CNPJ, o redirect pós-save e a persistência.

Tela usada: ``/admin/rh/pessoajuridica/`` — os rótulos vieram da feature
``comum/features/001.comum.cadastros_basicos.feature``, removida na migração do ``comum``
para pytest; o histórico do git ainda a tem.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAGEM = '/admin/rh/pessoajuridica/'
# CNPJ válido (dígitos verificadores conferem) e fixo: a suíte e2e nunca dá flush, então o
# teste apaga o registro antes de criar em vez de depender de banco limpo.
CNPJ = '50.834.073/0001-57'
CNPJ_DIGITOS = '50834073000157'
CNPJ_INVALIDO = '11.111.111/1111-11'


@pytest.fixture
def razao_social_livre():
    """Libera o CNPJ do teste e devolve uma razão social única.

    Único ponto onde o teste limpa estado: o CNPJ é ``unique``, e a suíte não dá flush
    entre testes (ver ``tests/e2e/conftest.py``). A razão social é única para a asserção
    não depender de contagem global.
    """
    from uuid import uuid4

    from rh.models import PessoaJuridica

    PessoaJuridica.objects.filter(cnpj__in=(CNPJ, CNPJ_DIGITOS)).delete()
    return f'E2E Empresa {uuid4().hex[:8]}'


def test_cadastra_pessoa_juridica_pela_ui(logado, razao_social_livre):
    page = logado('admin')

    page.goto(LISTAGEM)
    page.get_by_role('link', name='Adicionar Pessoa Jurídica').click()
    expect(page.get_by_role('heading', name='Adicionar Pessoa Jurídica')).to_be_visible()

    page.fill('input[name=nome]', razao_social_livre)
    page.fill('input[name=cnpj]', CNPJ)
    page.click('input[name=_save]')

    # O admin redireciona para a tela do objeto, cujo h2 traz razão social e CNPJ.
    expect(page.get_by_role('heading', name=f'Pessoa Jurídica: {razao_social_livre} ({CNPJ_DIGITOS})')).to_be_visible()

    from rh.models import PessoaJuridica

    assert PessoaJuridica.objects.filter(nome=razao_social_livre).exists(), 'a UI disse que salvou, mas não persistiu'


def test_cnpj_invalido_nao_cadastra(logado, razao_social_livre):
    page = logado('admin')

    page.goto(f'{LISTAGEM}add/')
    page.fill('input[name=nome]', razao_social_livre)
    page.fill('input[name=cnpj]', CNPJ_INVALIDO)
    page.click('input[name=_save]')

    # Continua no formulário e nada foi criado.
    expect(page.get_by_role('heading', name='Adicionar Pessoa Jurídica')).to_be_visible()

    from rh.models import PessoaJuridica

    assert not PessoaJuridica.objects.filter(nome=razao_social_livre).exists()
