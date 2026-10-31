from unittest import mock
from unittest.mock import MagicMock

from contratos.models import ContaContrato


class ContaContratoGetSaldoTest:
    """Testa o método get_saldo do modelo ContaContrato."""

    def _make_movimentacoes_mock(self, items):
        qs = MagicMock()
        qs.__iter__.return_value = iter(items)
        return qs

    def test_get_saldo_quando_apenas_depositos_retorna_soma(self):
        """get_saldo retorna soma dos valores quando todas sao depositos."""
        items = [
            MagicMock(deposito=True, valor='100.00'),
            MagicMock(deposito=True, valor='200.00'),
            MagicMock(deposito=True, valor='50.00'),
        ]
        manager = MagicMock()
        manager.all.return_value = self._make_movimentacoes_mock(items)
        p = mock.PropertyMock(return_value=manager)
        with mock.patch.object(ContaContrato, 'movimentacoes_conta', p):
            conta = ContaContrato()
            assert conta.get_saldo() == 350.0

    def test_get_saldo_quando_apenas_retiradas_retorna_negativo(self):
        """get_saldo retorna valor negativo quando todas sao retiradas."""
        items = [
            MagicMock(deposito=False, valor='100.00'),
            MagicMock(deposito=False, valor='50.00'),
        ]
        manager = MagicMock()
        manager.all.return_value = self._make_movimentacoes_mock(items)
        p = mock.PropertyMock(return_value=manager)
        with mock.patch.object(ContaContrato, 'movimentacoes_conta', p):
            conta = ContaContrato()
            assert conta.get_saldo() == -150.0

    def test_get_saldo_quando_misturado_retorna_diferenca(self):
        """get_saldo retorna saldo liquido entre depositos e retiradas."""
        items = [
            MagicMock(deposito=True, valor='500.00'),
            MagicMock(deposito=False, valor='200.00'),
            MagicMock(deposito=True, valor='100.00'),
        ]
        manager = MagicMock()
        manager.all.return_value = self._make_movimentacoes_mock(items)
        p = mock.PropertyMock(return_value=manager)
        with mock.patch.object(ContaContrato, 'movimentacoes_conta', p):
            conta = ContaContrato()
            assert conta.get_saldo() == 400.0

    def test_get_saldo_quando_sem_movimentacoes_retorna_zero(self):
        """get_saldo retorna 0 quando nao ha movimentacoes."""
        manager = MagicMock()
        manager.all.return_value = self._make_movimentacoes_mock([])
        p = mock.PropertyMock(return_value=manager)
        with mock.patch.object(ContaContrato, 'movimentacoes_conta', p):
            conta = ContaContrato()
            assert conta.get_saldo() == 0

    def test_get_saldo_quando_valor_com_casas_decimais_preserva_precisao(self):
        """get_saldo preserva precisao decimal nos calculos."""
        items = [
            MagicMock(deposito=True, valor='100.50'),
            MagicMock(deposito=False, valor='50.25'),
        ]
        manager = MagicMock()
        manager.all.return_value = self._make_movimentacoes_mock(items)
        p = mock.PropertyMock(return_value=manager)
        with mock.patch.object(ContaContrato, 'movimentacoes_conta', p):
            conta = ContaContrato()
            assert conta.get_saldo() == 50.25
