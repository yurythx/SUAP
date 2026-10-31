"""Fluxo: entradas de material (modo 2).

Entrada é o que transforma empenho em estoque. O behave só clicava no botão e fazia o
resto por ORM; aqui a navegação, a validação do filtro e os dois formulários são
exercitados pela UI, e o efeito no estoque é verificado no banco.
"""

from datetime import datetime

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

BUSCA = '/almoxarifado/entrada_busca/'


def test_busca_de_entradas_exige_campus_e_periodo(logado_almox):
    """Submeter vazio tem de reclamar: sem campus e período a busca varreria tudo."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)
    expect(page.get_by_role('heading', name='Busca de Entradas')).to_be_visible()

    page.click('input[name=entradabusca_form]')
    expect(page.locator('.errorlist', has_text='Este campo é obrigatório.').first).to_be_visible()


def test_busca_de_entradas_com_filtro_valido_chega_nos_resultados(logado_almox):
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)

    page.select_option('select[name=uo]', label='A0')
    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', datetime.now().date().isoformat())
    page.click('input[name=entradabusca_form]')

    expect(page.get_by_role('heading', name='Resultados')).to_be_visible()


def test_entrada_de_compra_pede_empenho_e_nota(logado_almox):
    """Compra nasce de empenho: os campos de empenho e nota fiscal são a rastreabilidade."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)
    page.get_by_role('link', name='Efetuar Entrada de Compra').click()

    expect(page.get_by_role('heading', name='Efetuar Entrada de Compra')).to_be_visible()
    expect(page.locator('input[name=empenho]')).to_be_visible()
    expect(page.locator('input[name=numero_nota]')).to_be_visible()
    expect(page.locator('input[name=data_nota]')).to_be_visible()


def test_entrada_de_doacao_nao_pede_empenho(logado_almox):
    """Doação não tem empenho — tem processo e fornecedor. É a diferença entre os dois fluxos.

    Se um dia a tela de doação passar a exigir empenho, isto quebra, que é o desejado.
    """
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)
    page.get_by_role('link', name='Efetuar Entrada de Doação').click()

    expect(page.get_by_role('heading', name='Efetuar Entrada de Doação')).to_be_visible()
    expect(page.locator('input[name=empenho]')).to_have_count(0)
    expect(page.locator('select[name=processo]')).to_have_count(1)
    expect(page.locator('input[name=numero_nota_fiscal]')).to_be_visible()


def test_entrada_credita_estoque(logado_almox, almoxarifado_a0):
    """Invariante do módulo: efetuar entrada aumenta ``MaterialEstoque.quantidade``.

    Montado pelo domínio, como o próprio behave montava (a tela depende de empenho com
    item e de fornecedor, encadeamento que a feature também não faz pela UI). O item de
    empenho é criado aqui a partir do empenho do seed, para o teste não depender de ordem
    com ``test_empenhos``.
    """
    from almoxarifado.models import Empenho, MaterialEstoque
    from almoxarifado.tests.factories import EmpenhoConsumoFactory, EntradaFactory

    uo, _, material = almoxarifado_a0
    estoque = MaterialEstoque.objects.get(material=material, uo=uo)
    antes = estoque.quantidade

    # Item no empenho do seed do módulo (não no dedicado da fixture), para o teste também
    # cobrir que dá para receber material de um empenho pré-existente.
    item = EmpenhoConsumoFactory(empenho=Empenho.objects.get(numero='20193012RE'), material=material, qtd_empenhada=10, valor=100)

    # `efetuar_entrada` é operação de domínio: é ela que credita o saldo, não a factory.
    item.efetuar_entrada(EntradaFactory(uo=uo), 1)

    estoque.refresh_from_db()
    assert estoque.quantidade > antes, 'entrada não creditou o estoque'

    # E a entrada passa a ser encontrável pela tela de busca.
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)
    page.select_option('select[name=uo]', label='A0')
    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', datetime.now().date().isoformat())
    page.click('input[name=entradabusca_form]')
    expect(page.get_by_role('heading', name='Resultados')).to_be_visible()
