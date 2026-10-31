from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from pit_rit_v3.models import PlanoIndividualTrabalhoV3


class TestDesfazerEnvioPlano:
    def _criar_pit_com_professor(self) -> tuple[PlanoIndividualTrabalhoV3, MagicMock]:
        user = MagicMock()
        professor = MagicMock()
        professor.vinculo.user = user

        pit = PlanoIndividualTrabalhoV3()
        pit._state.fields_cache['professor'] = professor
        pit.aprovado = None
        pit.data_envio = datetime.datetime.now()
        pit._state.fields_cache['avaliador'] = MagicMock()
        return pit, user

    def test_pode_desfazer_envio_plano_sucesso(self) -> None:
        pit, user = self._criar_pit_com_professor()
        assert pit.pode_desfazer_envio_plano(user) is True

    @patch('djtools.utils.tl.get_user')
    def test_pode_desfazer_envio_plano_com_user_none_obtem_do_tl(self, mock_get_user) -> None:
        pit, user = self._criar_pit_com_professor()
        mock_get_user.return_value = user
        assert pit.pode_desfazer_envio_plano() is True
        assert pit.pode_desfazer_envio_plano(None) is True

    @patch('djtools.utils.tl.get_user', return_value=None)
    def test_pode_desfazer_envio_plano_com_user_none_e_tl_none_retorna_false(self, mock_get_user) -> None:
        pit, _ = self._criar_pit_com_professor()
        assert pit.pode_desfazer_envio_plano() is False

    def test_pode_desfazer_envio_plano_nao_enviado(self) -> None:
        pit, user = self._criar_pit_com_professor()
        pit.data_envio = None
        assert pit.pode_desfazer_envio_plano(user) is False

    def test_pode_desfazer_envio_plano_ja_aprovado(self) -> None:
        pit, user = self._criar_pit_com_professor()
        pit.aprovado = True
        assert pit.pode_desfazer_envio_plano(user) is False

    def test_pode_desfazer_envio_plano_outro_usuario(self) -> None:
        pit, _ = self._criar_pit_com_professor()
        outro_user = MagicMock()
        assert pit.pode_desfazer_envio_plano(outro_user) is False

    def test_desfazer_envio_plano_executa_e_limpa_campos(self) -> None:
        pit, user = self._criar_pit_com_professor()
        with patch.object(pit, 'save') as mock_save:
            pit.desfazer_envio_plano(user)
            assert pit.data_envio is None
            assert pit.avaliador is None
            mock_save.assert_called_once()

    def test_desfazer_envio_plano_nao_executa_se_nao_puder(self) -> None:
        pit, _ = self._criar_pit_com_professor()
        outro_user = MagicMock()
        with patch.object(pit, 'save') as mock_save:
            pit.desfazer_envio_plano(outro_user)
            assert pit.data_envio is not None
            assert pit.avaliador is not None
            mock_save.assert_not_called()


class TestDesfazerEnvioRelatorio:
    def _criar_pit_com_professor(self) -> tuple[PlanoIndividualTrabalhoV3, MagicMock]:
        user = MagicMock()
        professor = MagicMock()
        professor.vinculo.user = user

        pit = PlanoIndividualTrabalhoV3()
        pit._state.fields_cache['professor'] = professor
        pit.relatorio_aprovado = None
        pit.data_envio_relatorio = datetime.datetime.now()
        pit._state.fields_cache['avaliador_relatorio'] = MagicMock()
        return pit, user

    def test_pode_desfazer_envio_relatorio_sucesso(self) -> None:
        pit, user = self._criar_pit_com_professor()
        assert pit.pode_desfazer_envio_relatorio(user) is True

    @patch('djtools.utils.tl.get_user')
    def test_pode_desfazer_envio_relatorio_com_user_none_obtem_do_tl(self, mock_get_user) -> None:
        pit, user = self._criar_pit_com_professor()
        mock_get_user.return_value = user
        assert pit.pode_desfazer_envio_relatorio() is True
        assert pit.pode_desfazer_envio_relatorio(None) is True

    @patch('djtools.utils.tl.get_user', return_value=None)
    def test_pode_desfazer_envio_relatorio_com_user_none_e_tl_none_retorna_false(self, mock_get_user) -> None:
        pit, _ = self._criar_pit_com_professor()
        assert pit.pode_desfazer_envio_relatorio() is False

    def test_pode_desfazer_envio_relatorio_nao_enviado(self) -> None:
        pit, user = self._criar_pit_com_professor()
        pit.data_envio_relatorio = None
        assert pit.pode_desfazer_envio_relatorio(user) is False

    def test_pode_desfazer_envio_relatorio_ja_aprovado(self) -> None:
        pit, user = self._criar_pit_com_professor()
        pit.relatorio_aprovado = True
        assert pit.pode_desfazer_envio_relatorio(user) is False

    def test_pode_desfazer_envio_relatorio_outro_usuario(self) -> None:
        pit, _ = self._criar_pit_com_professor()
        outro_user = MagicMock()
        assert pit.pode_desfazer_envio_relatorio(outro_user) is False

    def test_desfazer_envio_relatorio_executa_e_limpa_campos(self) -> None:
        pit, user = self._criar_pit_com_professor()
        with patch.object(pit, 'save') as mock_save:
            pit.desfazer_envio_relatorio(user)
            assert pit.data_envio_relatorio is None
            assert pit.avaliador_relatorio is None
            mock_save.assert_called_once()

    def test_desfazer_envio_relatorio_nao_executa_se_nao_puder(self) -> None:
        pit, _ = self._criar_pit_com_professor()
        outro_user = MagicMock()
        with patch.object(pit, 'save') as mock_save:
            pit.desfazer_envio_relatorio(outro_user)
            assert pit.data_envio_relatorio is not None
            assert pit.avaliador_relatorio is not None
            mock_save.assert_not_called()
