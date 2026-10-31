from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from contratos.models import Contrato
from contratos.views import receber_definitivamente_medicao


class ContratoRecebimentoDefinitivoPermissaoTest(SimpleTestCase):
    @staticmethod
    def _request(eh_servidor: bool = True) -> SimpleNamespace:
        usuario = SimpleNamespace(eh_servidor=eh_servidor, get_relacionamento=object)
        return SimpleNamespace(user=usuario)

    @staticmethod
    def _contrato(*, fiscal_eh_gestor: bool | None, gerente: bool = False, cancelado: bool = False) -> SimpleNamespace:
        fiscal = None
        if fiscal_eh_gestor is not None:
            fiscal = SimpleNamespace(tipo=SimpleNamespace(eh_gestor_contrato=fiscal_eh_gestor))
        return SimpleNamespace(
            cancelado=cancelado,
            pode_executar_acoes_coordenador_gerente=lambda request: gerente,
            get_fiscal=lambda servidor: fiscal,
        )

    def test_fiscal_comum_nao_pode_gerenciar_recebimento_definitivo(self) -> None:
        contrato = self._contrato(fiscal_eh_gestor=False)

        assert Contrato.pode_gerenciar_recebimento_definitivo(contrato, self._request()) is False

    def test_fiscal_gestor_pode_gerenciar_recebimento_definitivo(self) -> None:
        contrato = self._contrato(fiscal_eh_gestor=True)

        assert Contrato.pode_gerenciar_recebimento_definitivo(contrato, self._request()) is True

    def test_gerente_pode_gerenciar_recebimento_definitivo(self) -> None:
        contrato = self._contrato(fiscal_eh_gestor=None, gerente=True)

        assert Contrato.pode_gerenciar_recebimento_definitivo(contrato, self._request(eh_servidor=False)) is True

    def test_contrato_cancelado_bloqueia_recebimento_definitivo(self) -> None:
        contrato = self._contrato(fiscal_eh_gestor=True, cancelado=True)

        assert Contrato.pode_gerenciar_recebimento_definitivo(contrato, self._request()) is False


class ReceberDefinitivamenteMedicaoViewTest(SimpleTestCase):
    def test_post_sem_recebimento_provisorio_emitido_nao_processa_formulario(self) -> None:
        resposta_bloqueio = object()
        contrato = SimpleNamespace(id=10, contas=MagicMock(), pode_gerenciar_recebimento_definitivo=lambda request: True)
        contrato.contas.filter.return_value.order_by.return_value = []
        medicao = SimpleNamespace(
            parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)),
            recebimento_provisorio_emitido=lambda: False,
        )
        request = SimpleNamespace(method='POST', POST={}, FILES={}, user=SimpleNamespace())

        with (
            patch('contratos.views.get_object_or_404', return_value=medicao),
            patch('contratos.views.httprr', return_value=resposta_bloqueio) as httprr,
            patch('contratos.views.formset_factory') as formset_factory,
        ):
            resposta = unwrap(receber_definitivamente_medicao)(request, medicao_id=20)

        assert resposta is resposta_bloqueio
        httprr.assert_called_once_with(
            '/contratos/contrato/10/?tab=cronograma',
            'O recebimento definitivo só pode ser realizado após a emissão do relatório de recebimento provisório.',
            tag='warning',
        )
        formset_factory.assert_not_called()
