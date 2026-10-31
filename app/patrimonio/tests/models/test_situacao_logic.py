from unittest.mock import patch, Mock

from patrimonio.models import Inventario, MovimentoPatrimTipo, Requisicao


class TestGetSituacaoDisplayFromSituacao:
    """Testes para ``Inventario.get_situacao_display_from_situacao``."""

    def test_situacao_none_retorna_traco(self):
        """situacao=None deve retornar '-'."""
        resultado = Inventario.get_situacao_display_from_situacao(None)
        assert resultado == '-'

    def test_situacao_vazia_retorna_traco(self):
        """situacao='' (falsy) deve retornar '-'."""
        resultado = Inventario.get_situacao_display_from_situacao('')
        assert resultado == '-'

    def test_situacao_status_aguardando_aprovacao_retorna_display(self):
        """situacao = 1 (aguardando aprovação) deve retornar o label do choice."""
        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_REQUISICAO_STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO  # 1
        )
        assert resultado == 'Aguardando aprovação do servidor de destino'

    def test_situacao_status_deferida_aguardando_pa_origem_retorna_display(self):
        """situacao = 4 (deferida aguardando PA origem) deve retornar o label do choice."""
        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM  # 4
        )
        assert resultado == 'Aguardando informação de PA Campus Origem'

    def test_situacao_status_deferida_aguardando_pa_destino_retorna_display(self):
        """situacao = 6 (deferida aguardando PA destino) deve retornar o label do choice."""
        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO  # 6
        )
        assert resultado == 'Aguardando informação de PA Campus Destino'

    @patch.object(MovimentoPatrimTipo, 'PENDENCIA')
    def test_situacao_pendencia_retorna_nome(self, mock_pendencia):
        """situacao = 'pendência' deve retornar o nome do tipo pendência."""
        mock_obj = Mock(nome='pendência')
        mock_pendencia.return_value = mock_obj

        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_PENDENCIA  # 'pendência'
        )
        assert resultado == 'pendência'

    @patch.object(MovimentoPatrimTipo, 'BAIXA')
    def test_situacao_baixa_retorna_nome(self, mock_baixa):
        """situacao = 'baixa' deve retornar o nome do tipo baixa."""
        mock_obj = Mock(nome='baixa')
        mock_baixa.return_value = mock_obj

        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_BAIXA  # 'baixa'
        )
        assert resultado == 'baixa'

    def test_situacao_desconhecida_retorna_traco(self):
        """situacao desconhecida (sem match) deve retornar '-'."""
        resultado = Inventario.get_situacao_display_from_situacao('valor_inexistente')
        assert resultado == '-'

    def test_situacao_requisicao_com_get_status_display_falho_retorna_interrogacao(self):
        """situacao de requisição com ``get_status_display`` quebrado deve retornar '?'."""
        with patch.object(Requisicao, 'get_status_display', side_effect=RuntimeError('falha')):
            resultado = Inventario.get_situacao_display_from_situacao(
                Inventario.SITUACAO_REQUISICAO_STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO  # 1
            )
        assert resultado == '?'

    @patch.object(MovimentoPatrimTipo, 'PENDENCIA')
    def test_situacao_movimento_com_exception_retorna_interrogacao(self, mock_pendencia):
        """situacao de movimento cujo lookup falha deve retornar '?'."""
        mock_pendencia.side_effect = RuntimeError('falha no banco')

        resultado = Inventario.get_situacao_display_from_situacao(
            Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_PENDENCIA  # 'pendência'
        )
        assert resultado == '?'
