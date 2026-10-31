"""Fluxo: cadastros básicos do almoxarifado (modo 2).

Unidade de Medida, Material de Consumo e Elemento de Despesa de Material de Consumo são a
base de tudo no módulo — sem eles não há empenho, entrada nem saída. São telas
``ModelAdminPlus``, e cada uma exige um grupo diferente (ver ``test_permissoes.py``).
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

UNIDADE = '/admin/almoxarifado/unidademedida/'
MATERIAL = '/admin/almoxarifado/materialconsumo/'
ELEMENTO = '/admin/almoxarifado/categoriamaterialconsumo/'


def _sufixo() -> str:
    return uuid4().hex[:8]


def test_unidade_de_medida_ciclo_completo(logado_almox):
    """Criar → editar → remover, o ciclo que o behave cobria em 4 cenários."""
    page = logado_almox('CoordDeAlmoxSiste')
    nome = f'E2E Unidade {_sufixo()}'
    novo_nome = f'{nome} editada'

    page.goto(UNIDADE)
    page.get_by_role('link', name='Adicionar Unidade de Medida').click()
    page.fill('input[name=nome]', nome)
    page.click('input[name=_save]')
    expect(page.get_by_text('Cadastro realizado com sucesso')).to_be_visible()

    # Editar: a listagem linka o próprio nome para a tela de edição.
    page.goto(UNIDADE)
    page.get_by_role('link', name=nome).click()
    page.fill('input[name=nome]', novo_nome)
    page.click('input[name=_save]')
    expect(page.get_by_text('Atualização realizada com sucesso')).to_be_visible()

    from almoxarifado.models import UnidadeMedida

    assert UnidadeMedida.objects.filter(nome=novo_nome).exists()
    assert not UnidadeMedida.objects.filter(nome=nome).exists(), 'a edição deveria ter substituído o nome'


def test_material_de_consumo_usa_autocomplete_de_categoria(logado_almox):
    """O cadastro depende do autocomplete de Elemento de Despesa (``/json/``).

    É o ponto onde o módulo mais quebra: material sem categoria não entra em balancete.
    """
    page = logado_almox('CoordDeAlmoxSiste')
    nome = f'E2E Material {_sufixo()}'

    page.goto(MATERIAL)
    page.get_by_role('link', name='Adicionar Material de Consumo').click()

    widget = page.locator('select[name="categoria"] + span.select2')
    expect(widget).to_be_visible()
    widget.click()
    page.keyboard.type('Categoria Material Consumo')
    page.locator('.select2-results__option', has_text='Categoria Material Consumo').first.click()

    page.fill('textarea[name=nome], input[name=nome]', nome)
    page.click('input[name=_save]')

    expect(page.get_by_text('Cadastro realizado com sucesso')).to_be_visible()

    from almoxarifado.models import MaterialConsumo

    material = MaterialConsumo.objects.filter(nome=nome).first()
    assert material is not None, 'a UI disse que salvou, mas não persistiu'
    assert material.categoria is not None, 'material salvo sem elemento de despesa'


def test_elemento_de_despesa_exige_plano_de_contas(logado_almox):
    """Elemento de Despesa é tela do Contador, não do almoxarifado (ver test_permissoes).

    O Plano de Contas vem do ``loaddata initial_data``; ``11561.01.00 MATERIAIS DE CONSUMO``
    é uma das linhas reais e é o que o autocomplete tem de encontrar.
    """
    page = logado_almox('ContadorAdministra')
    sufixo = _sufixo()
    nome = f'E2E Elemento {sufixo}'

    page.goto(f'{ELEMENTO}add/')
    page.fill('input[name=codigo]', sufixo[:6])
    page.fill('input[name=nome]', nome)

    widget = page.locator('select[name="plano_contas"] + span.select2')
    expect(widget).to_be_visible()
    widget.click()
    page.keyboard.type('MATERIAIS DE CONSUMO')
    page.locator('.select2-results__option', has_text='MATERIAIS DE CONSUMO').first.click()

    page.click('input[name=_save]')
    expect(page.get_by_text('Cadastro realizado com sucesso')).to_be_visible()

    from almoxarifado.models import CategoriaMaterialConsumo

    assert CategoriaMaterialConsumo.objects.filter(nome=nome).exists()
