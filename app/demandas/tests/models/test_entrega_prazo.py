"""Regressão dos cálculos de prazo da Entrega.

`prazo_vencido` e `dias_em_atraso` comparavam `timezone.now().today()` (um
datetime) com `prazo_feedback` (um date), o que disparava
``TypeError: can't compare datetime.datetime to datetime.date`` ao abrir a aba
de Entregas de uma demanda com entrega pendente e prazo informado.

São propriedades puras (não tocam o banco), então os testes instanciam a
Entrega sem salvar.
"""

from datetime import timedelta

from django.utils import timezone

from demandas.models.entrega import StatusEntrega
from demandas.tests.factories import EntregaFactory


def _entrega(prazo_feedback, status=StatusEntrega.ENVIADA):
    return EntregaFactory.build(status=status, prazo_feedback=prazo_feedback)


class TestPrazoVencido:
    def test_prazo_no_passado_e_pendente_esta_vencido(self):
        entrega = _entrega(timezone.now().date() - timedelta(days=3))
        # Antes do fix, esta linha levantava TypeError (datetime vs date).
        assert entrega.prazo_vencido is True
        assert entrega.dias_em_atraso == 3

    def test_prazo_no_futuro_nao_esta_vencido(self):
        entrega = _entrega(timezone.now().date() + timedelta(days=2))
        assert entrega.prazo_vencido is False
        assert entrega.dias_em_atraso is None

    def test_sem_prazo_nao_esta_vencido(self):
        entrega = _entrega(prazo_feedback=None)
        assert entrega.prazo_vencido is False
        assert entrega.dias_em_atraso is None

    def test_prazo_vencido_mas_encerrada_nao_conta(self):
        entrega = _entrega(timezone.now().date() - timedelta(days=5), status=StatusEntrega.APROVADA)
        assert entrega.prazo_vencido is False
        assert entrega.dias_em_atraso is None
