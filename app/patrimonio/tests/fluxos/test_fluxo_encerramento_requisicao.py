"""Requisição de transferência encerrada sem transferir: os itens não podem continuar pendentes."""

import pytest

from patrimonio.models import Inventario, InventarioStatus, Requisicao, RequisicaoItem
from patrimonio.tests.factories import BaixaFactory, EntradaPermanenteFactory, RequisicaoFactory, RequisicaoItemFactory
from rh.tests.factories import ServidorFactory


@pytest.fixture
def requisicao(db, dados_referencia, sync_permissions):
    """Requisição aguardando o destino, com um item já aprovado e outro ainda pendente."""
    origem = ServidorFactory()
    destino = ServidorFactory()
    entrada = EntradaPermanenteFactory(entrada__uo=origem.setor.uo, qtd=2)
    Inventario.objects.filter(entrada_permanente=entrada).update(status=InventarioStatus.ATIVO(), responsavel_vinculo=origem.get_vinculo())
    aprovado, pendente = Inventario.objects.filter(entrada_permanente=entrada).order_by('pk')
    requisicao = RequisicaoFactory(
        vinculo_origem=origem.get_vinculo(),
        vinculo_destino=destino.get_vinculo(),
        campus_origem=origem.setor.uo,
        campus_destino=destino.setor.uo,
    )
    RequisicaoItemFactory(requisicao=requisicao, inventario=aprovado, situacao=RequisicaoItem.APROVADO)
    RequisicaoItemFactory(requisicao=requisicao, inventario=pendente)
    return requisicao


def test_indeferir_rejeita_todos_os_itens(client, requisicao):
    client.force_login(requisicao.vinculo_destino.user)

    response = client.post(f'/patrimonio/indeferir_requisicao/{requisicao.pk}/', {'observacao': 'Não recebo estes bens.'})

    assert response.status_code == 302
    requisicao.refresh_from_db()
    assert requisicao.status == Requisicao.STATUS_INDEFERIDA
    assert set(requisicao.itens.values_list('situacao', flat=True)) == {RequisicaoItem.REJEITADO}


def test_baixa_de_inventario_cancela_os_itens_da_requisicao_pendente(requisicao):
    inventario = requisicao.itens.order_by('pk').last().inventario

    Inventario.efetuar_baixa(inventarios=inventario, baixa=BaixaFactory(uo=requisicao.campus_origem))

    requisicao.refresh_from_db()
    assert requisicao.status == Requisicao.STATUS_CANCELADA
    assert set(requisicao.itens.values_list('situacao', flat=True)) == {RequisicaoItem.CANCELADO}
