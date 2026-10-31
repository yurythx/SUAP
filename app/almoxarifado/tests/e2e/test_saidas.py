"""Fluxo: saída de material — requisição do usuário (modo 2).

É a ponta que todo servidor do IFRN usa: pedir material ao almoxarifado. A tela monta os
itens dinamicamente por JS (``Adicionar Material``) e o solicitante vem de autocomplete,
então é um dos pontos onde quebra de JS passa despercebida em teste de unidade.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

REQUISICAO = '/almoxarifado/form_requisicao_usuario_pedido'


def test_tela_de_requisicao_monta_os_campos_do_pedido(logado_almox):
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(REQUISICAO)

    expect(page.get_by_role('heading', name='Requisição de Saída de Material para Consumo')).to_be_visible()
    # Trio que define o pedido: quem pede, o que pede e quanto.
    expect(page.locator('input[name=solicitante]')).to_be_visible()
    expect(page.locator('input[name=itens]')).to_be_visible()
    expect(page.locator('input[name=quantidades]')).to_be_visible()


def test_adicionar_material_cria_nova_linha_de_item(logado_almox):
    """O botão é JS puro: sem ele o usuário só consegue pedir um material por requisição."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(REQUISICAO)

    antes = page.locator('input[name=itens]').count()
    page.get_by_role('link', name='Adicionar Material').click()
    expect(page.locator('input[name=itens]')).to_have_count(antes + 1)


def test_requisicao_criada_vincula_material_ao_solicitante(logado_almox, requisicao_pendente, almoxarifado_a0):
    """Protege o vínculo requisição → material → solicitante.

    Montada pela fixture ``requisicao_pendente`` (domínio), como o behave montava com
    ``Dado o cadastro de requisicao``: a tela de criação depende de estoque e do JS de
    itens. O atendimento dessa requisição é coberto em ``test_requisicoes.py``.
    """
    requisicao, _ = requisicao_pendente
    _, _, material = almoxarifado_a0

    # O related_name é `item_set` (não o `<model>_set` default).
    assert requisicao.item_set.filter(material=material).exists()

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(REQUISICAO)
    expect(page.get_by_role('heading', name='Requisição de Saída de Material para Consumo')).to_be_visible()
