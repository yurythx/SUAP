from decimal import Decimal

import pytest

from plan_estrategico.models import RequisicaoDespesa
from plan_estrategico.tests.factories import AtividadeEtapaFactory, RequisicaoDespesaFactory

pytestmark = pytest.mark.django_db


def test_anulacao_de_empenho_so_libera_saldo_da_atividade_depois_de_validada():
    atividade = AtividadeEtapaFactory(valor_rateio=Decimal('1000'))
    RequisicaoDespesaFactory(atividade=atividade, status=RequisicaoDespesa.STATUS_CONCLUIDA, valor=Decimal('600'))
    saldo_apos_empenho = atividade.saldo_disponivel_empenho_atividade()

    anulacao = RequisicaoDespesaFactory(
        atividade=atividade,
        tipo_requisicao=RequisicaoDespesa.TIPO_ANULACAO_EMPENHO,
        status=RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO,
        valor=Decimal('-200'),
    )
    for status in (
        RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO,
        RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
        RequisicaoDespesa.STATUS_CANCELADA,
    ):
        anulacao.status = status
        anulacao.save()
        assert atividade.saldo_disponivel_empenho_atividade() == saldo_apos_empenho

    anulacao.status = RequisicaoDespesa.STATUS_CONCLUIDA
    anulacao.save()
    assert atividade.saldo_disponivel_empenho_atividade() == saldo_apos_empenho + Decimal('200')
