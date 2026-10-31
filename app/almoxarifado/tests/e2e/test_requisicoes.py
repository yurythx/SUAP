"""Fluxo: atendimento de requisições — o lado do almoxarifado.

``test_saidas.py`` cobre o pedido (o servidor requisita). Aqui está o outro lado, que é a
razão de existir do módulo: a fila de pendentes, o atendimento com baixa de estoque, a
busca de requisições e a transferência intercampi. Nenhum desses tinha cenário no behave.

O atendimento é o fluxo mais consequente do módulo — é o único que **move estoque para
fora** —, e é POST puro (``requisicao_resposta`` lê ``idRequisicoesMaterial`` e
``quantidadesAceitas``, chama ``requisicao.avaliar()`` e engole exceção num redirect com
mensagem de erro). Ou seja: quando quebra, quebra silenciosamente, com o usuário de volta
na fila sem entender.
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PENDENTES = '/almoxarifado/requisicoes_pendentes/'
BUSCA = '/almoxarifado/requisicao_busca/'
INTERCAMPI = '/almoxarifado/form_requisicao_uo_pedido/'


def test_fila_de_pendentes_mostra_a_requisicao(logado_almox, requisicao_pendente):
    requisicao, _ = requisicao_pendente
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(PENDENTES)

    expect(page.get_by_role('heading', name='Requisições Pendentes')).to_be_visible()
    # A fila é separada por origem: servidor e outro campus.
    expect(page.get_by_text('Saída para Servidores')).to_be_visible()
    expect(page.get_by_text('Saída para Outros Campi')).to_be_visible()
    # E a requisição aparece com link para a tela de atendimento.
    expect(page.locator(f'a[href="/almoxarifado/requisicao_detalhe/user/{requisicao.pk}/"]')).to_have_count(1)


def test_atender_requisicao_da_baixa_no_estoque(logado_almox, requisicao_pendente, almoxarifado_a0):
    """O fluxo completo: fila → tela de atendimento → responder → estoque diminui.

    A quantidade atendida (2) é menor que a pedida (3) de propósito: atendimento parcial é
    o caso comum no almoxarifado e é onde a conta de baixa erra mais fácil.
    """
    from almoxarifado.models import MaterialEstoque

    requisicao, item = requisicao_pendente
    uo, _, material = almoxarifado_a0
    antes = MaterialEstoque.objects.get(material=material, uo=uo).quantidade

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(PENDENTES)
    page.locator(f'a[href="/almoxarifado/requisicao_detalhe/user/{requisicao.pk}/"]').click()

    expect(page.get_by_role('heading', name=f'Requisição #{requisicao.pk}')).to_be_visible()
    expect(page.get_by_role('heading', name='Responder Requisição')).to_be_visible()

    page.check(f'input[name=idRequisicoesMaterial][value="{item.pk}"]')
    page.fill('input[name=quantidadesAceitas]', '2')
    page.get_by_role('button', name='Responder').click()

    expect(page.get_by_text('Saída de Material Realizada')).to_be_visible()

    depois = MaterialEstoque.objects.get(material=material, uo=uo).quantidade
    assert depois == antes - 2, f'estoque deveria cair 2 (atendido), foi de {antes} para {depois}'


def test_atendimento_acima_do_estoque_e_recusado(logado_almox, requisicao_pendente, almoxarifado_a0):
    """Não se entrega o que não existe — e o estoque não pode ficar negativo."""
    from almoxarifado.models import MaterialEstoque

    requisicao, item = requisicao_pendente
    uo, _, material = almoxarifado_a0
    antes = MaterialEstoque.objects.get(material=material, uo=uo).quantidade

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(f'/almoxarifado/requisicao_detalhe/user/{requisicao.pk}/')
    page.check(f'input[name=idRequisicoesMaterial][value="{item.pk}"]')
    page.fill('input[name=quantidadesAceitas]', str(int(antes) + 1000))
    page.get_by_role('button', name='Responder').click()

    expect(page.get_by_text('Saída de Material Realizada')).to_have_count(0)
    depois = MaterialEstoque.objects.get(material=material, uo=uo).quantidade
    assert depois == antes, f'estoque não devia mudar numa recusa: {antes} → {depois}'


def test_busca_de_requisicoes_filtra_por_periodo(logado_almox, requisicao_pendente):
    from datetime import datetime

    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(BUSCA)
    expect(page.get_by_role('heading', name='Buscar Requisição')).to_be_visible()

    page.fill('input[name=data_inicial]', '2019-01-01')
    page.fill('input[name=data_final]', datetime.now().date().isoformat())
    page.click('input[name=requisicaobusca_form]')

    expect(page.get_by_role('heading', name='Buscar Requisição')).to_be_visible()
    expect(page.locator('.errorlist')).to_have_count(0)


def test_transferencia_intercampi_pede_destino_e_material(logado_almox):
    """Transferência entre campi é fluxo próprio: tem almoxarifado de destino, o pedido comum não."""
    page = logado_almox('CoordDeAlmoxSiste')
    page.goto(INTERCAMPI)

    expect(page.get_by_role('heading', name='Requisição de Transferência de Material de Consumo Intercampi')).to_be_visible()
    expect(page.locator('select[name=uo_id]')).to_be_visible()
    expect(page.locator('input[name=itens]')).to_be_visible()
    expect(page.locator('input[name=quantidades]')).to_be_visible()


def test_contador_nao_atende_requisicoes(logado_almox):
    """Atender requisição é do almoxarifado; a contabilidade não entra na fila."""
    page = logado_almox('ContadorAdministra')
    assert page.goto(PENDENTES).status == 403
