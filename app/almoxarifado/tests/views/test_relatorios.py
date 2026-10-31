"""Relatórios do almoxarifado (balancete de elemento de despesa)."""

from datetime import date
from decimal import Decimal

import pytest
from django.apps.registry import apps

from almoxarifado.estoque import Estoque

RequisicaoAlmoxUser = apps.get_model('almoxarifado', 'RequisicaoAlmoxUser')
RequisicaoAlmoxUserMaterial = apps.get_model('almoxarifado', 'RequisicaoAlmoxUserMaterial')

pytestmark = pytest.mark.django_db

BALANCETE_ED = '/almoxarifado/balancete_ed/'


def _consumir_todo_o_estoque(almox_context, material, qtd):
    """Cria e atende uma requisição de consumo, zerando o estoque do material."""
    requisicao = RequisicaoAlmoxUser.objects.create(
        uo_fornecedora=almox_context.campus_a_suap,
        vinculo_solicitante=almox_context.servidor_a.get_vinculo(),
        setor_solicitante=almox_context.servidor_a.setor,
    )
    item = RequisicaoAlmoxUserMaterial.objects.create(requisicao=requisicao, material=material, qtd=qtd)
    Estoque.efetuar_saida_ou_transferencia(item, qtd)


def test_balancete_ed_com_estoque_zerado_no_periodo(almox_context):
    """Regressão: entrada e saída que se anulam produzem um total zerado.

    Com `qtd` (5 casas) x `valor` (6 casas), `sum(qtd * valor)` tem 11 casas decimais e o
    total zerado volta do banco como `Decimal('0E-11')`, cujo `str()` é notação científica.
    A máscara de dinheiro fatiava essa string e gerava `'-0.E11,00'`, quebrando a soma da
    linha de totais com `could not convert string to float: '-0E11.00'`.
    """
    empenho, item1, _ = almox_context.criar_empenho_consumo_com_dois_itens(usuario=almox_context.servidor_a)
    almox_context.registrar_entrada_compra(empenho, [item1], [5], usuario=almox_context.servidor_a)
    _consumir_todo_o_estoque(almox_context, almox_context.mat1, 5)

    estoque = almox_context.mat1.estoque(uo_id=almox_context.campus_a_suap.pk)
    assert estoque['valor'] == Decimal(0)
    if 'E' not in str(estoque['valor']):
        pytest.skip('o total zerado não voltou em notação científica; cenário não reproduz o defeito')

    hoje = date.today().strftime('%d/%m/%Y')
    almox_context.login(almox_context.servidor_a)
    response = almox_context.client.post(
        BALANCETE_ED,
        {'faixa_0': hoje, 'faixa_1': hoje, 'uos': almox_context.campus_a_suap.pk},
    )

    assert response.status_code == 200
    assert 'Balancete Elemento de Despesa de Material de Consumo' in response.content.decode()
