from __future__ import annotations

from unittest.mock import patch
from pit_rit_v3.models import PlanoIndividualTrabalhoV3


class TestPlanoIndividualTrabalhoV3Configuracao:
    def test_constantes_removidas_do_modelo(self) -> None:
        assert not hasattr(PlanoIndividualTrabalhoV3, 'ANO_INICIO_APP')
        assert not hasattr(PlanoIndividualTrabalhoV3, 'PERIODO_INICIO_APP')

    @patch('comum.models.Configuracao.get_valor_por_chave', return_value=None)
    def test_valores_inicio_retornam_none_quando_nao_configurado(self, mock_get_valor) -> None:
        assert PlanoIndividualTrabalhoV3.get_ano_inicio() is None
        assert PlanoIndividualTrabalhoV3.get_periodo_inicio() is None

    @patch('comum.models.Configuracao.get_valor_por_chave', return_value=None)
    def test_modulo_inativo_quando_nao_configurado(self, mock_get_valor) -> None:
        assert PlanoIndividualTrabalhoV3.modulo_ativo() is False
        assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 2) is False

    def test_valores_inicio_quando_configurado(self) -> None:
        def fake_get_valor_por_chave(app: str, chave: str):
            if app == 'pit_rit_v3':
                if chave == 'ano_inicio_app':
                    return '2027'
                if chave == 'periodo_inicio_app':
                    return '1'
            return None

        with patch('comum.models.Configuracao.get_valor_por_chave', side_effect=fake_get_valor_por_chave):
            assert PlanoIndividualTrabalhoV3.get_ano_inicio() == 2027
            assert PlanoIndividualTrabalhoV3.get_periodo_inicio() == 1
            assert PlanoIndividualTrabalhoV3.modulo_ativo() is True

            # Anos anteriores ao início
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 1) is False
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 2) is False

            # No ano de início
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2027, 1) is True
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2027, 2) is True

            # Anos posteriores ao início
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2028, 1) is True

    def test_valores_inicio_quando_inicio_no_segundo_periodo(self) -> None:
        def fake_get_valor_por_chave(app: str, chave: str):
            if app == 'pit_rit_v3':
                if chave == 'ano_inicio_app':
                    return '2026'
                if chave == 'periodo_inicio_app':
                    return '2'
            return None

        with patch('comum.models.Configuracao.get_valor_por_chave', side_effect=fake_get_valor_por_chave):
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 1) is False
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 2) is True
            assert PlanoIndividualTrabalhoV3.modulo_ativo(2027, 1) is True

    @patch('comum.models.Configuracao.get_valor_por_chave', return_value='invalido')
    def test_resiliencia_a_valores_nao_numericos(self, mock_get_valor) -> None:
        assert PlanoIndividualTrabalhoV3.get_ano_inicio() is None
        assert PlanoIndividualTrabalhoV3.get_periodo_inicio() is None
        assert PlanoIndividualTrabalhoV3.modulo_ativo() is False
        assert PlanoIndividualTrabalhoV3.modulo_ativo(2026, 2) is False


class TestPlanoIndividualTrabalhoV3CargasHorarias:
    def test_get_ch_aulas_nao_inclui_diarios_especiais(self) -> None:
        pit = PlanoIndividualTrabalhoV3()
        with (
            patch.object(pit, 'get_ch_diarios', side_effect=[(4, 4), (2, 2)]),
            patch.object(pit, 'get_ch_minicursos', return_value=(1, 1)),
        ):
            ch_semanal_aulas, ch_aulas = pit.get_ch_aulas()
            # 4 (regulares) + 2 (fic) + 1 (minicurso) = 7
            assert ch_semanal_aulas == 7
            assert ch_aulas > 0
