"""Testes unitários para os métodos clean() dos modelos do app ponto.

Testes de lógica pura — sem acesso ao banco de dados.
"""

from datetime import date

from django.core.exceptions import ValidationError
from ponto.models import Maquina, RecessoPeriodo
import pytest


class MaquinaCleanTestCase:
    """Testes para o método clean() de Maquina."""

    @pytest.fixture(autouse=True)
    def _auto_setup(self):
        self.maquina = Maquina()

    def test_refeitorio_com_ponto_raise_validation_error(self):
        """Deve levantar ValidationError quando cliente_refeitorio e cliente_ponto são True."""
        self.maquina.cliente_refeitorio = True
        self.maquina.cliente_ponto = True
        self.maquina.cliente_chaves = False
        self.maquina.cliente_cadastro_impressao_digital = False
        with pytest.raises(ValidationError):
            self.maquina.clean()

    def test_refeitorio_com_chaves_raise_validation_error(self):
        """Deve levantar ValidationError quando cliente_refeitorio e cliente_chaves são True."""
        self.maquina.cliente_refeitorio = True
        self.maquina.cliente_ponto = False
        self.maquina.cliente_chaves = True
        self.maquina.cliente_cadastro_impressao_digital = False
        with pytest.raises(ValidationError):
            self.maquina.clean()

    def test_refeitorio_com_cadastro_impressao_digital_raise_validation_error(self):
        """Deve levantar ValidationError quando cliente_refeitorio
        e cliente_cadastro_impressao_digital são True."""
        self.maquina.cliente_refeitorio = True
        self.maquina.cliente_ponto = False
        self.maquina.cliente_chaves = False
        self.maquina.cliente_cadastro_impressao_digital = True
        with pytest.raises(ValidationError):
            self.maquina.clean()

    def test_refeitorio_sozinho_sem_erro(self):
        """Não deve levantar erro quando apenas cliente_refeitorio é True."""
        self.maquina.cliente_refeitorio = True
        self.maquina.cliente_ponto = False
        self.maquina.cliente_chaves = False
        self.maquina.cliente_cadastro_impressao_digital = False
        self.maquina.clean()

    def test_ponto_sem_refeitorio_sem_erro(self):
        """Não deve levantar erro quando cliente_ponto é True mas cliente_refeitorio é False."""
        self.maquina.cliente_refeitorio = False
        self.maquina.cliente_ponto = True
        self.maquina.cliente_chaves = False
        self.maquina.cliente_cadastro_impressao_digital = False
        self.maquina.clean()

    def test_todos_false_sem_erro(self):
        """Não deve levantar erro quando todos os campos de cliente são False."""
        self.maquina.cliente_refeitorio = False
        self.maquina.cliente_ponto = False
        self.maquina.cliente_chaves = False
        self.maquina.cliente_cadastro_impressao_digital = False
        self.maquina.clean()


class RecessoPeriodoCleanTestCase:
    """Testes para o método clean() de RecessoPeriodo."""

    @pytest.fixture(autouse=True)
    def _auto_setup(self):
        self.periodo = RecessoPeriodo()

    def test_dados_validos_sem_erro(self):
        """Não deve levantar erro quando todos os campos estão preenchidos e válidos."""
        self.periodo.data_inicio = date(2025, 1, 1)
        self.periodo.data_fim = date(2025, 1, 10)
        self.periodo.dias_excluidos = '05/01/2025'
        self.periodo.qtde_max_dias_a_escolher = 5
        self.periodo.clean()

    def test_dias_excluidos_sem_refeitorio_com_formato_invalido_raise_validation_error(self):
        """Deve levantar ValidationError quando dias_excluidos possui formato inválido."""
        self.periodo.dias_excluidos = 'formato inválido'
        with pytest.raises(ValidationError):
            self.periodo.clean()

    def test_dias_excluidos_fora_do_periodo_raise_validation_error(self):
        """Deve levantar ValidationError quando dias_excluidos contém data fora do período."""
        self.periodo.data_inicio = date(2025, 1, 1)
        self.periodo.data_fim = date(2025, 1, 10)
        self.periodo.dias_excluidos = '15/01/2025'
        self.periodo.qtde_max_dias_a_escolher = 0
        with pytest.raises(ValidationError):
            self.periodo.clean()

    def test_qtde_max_dias_a_escolher_maior_que_disponiveis_raise_validation_error(self):
        """Deve levantar ValidationError quando qtde_max_dias_a_escolher
        excede a quantidade de dias disponíveis (total - excluídos)."""
        self.periodo.data_inicio = date(2025, 1, 1)
        self.periodo.data_fim = date(2025, 1, 5)  # 5 dias no total
        self.periodo.dias_excluidos = '03/01/2025'  # 1 dia excluído → 4 disponíveis
        self.periodo.qtde_max_dias_a_escolher = 5  # 5 > 4 → erro
        with pytest.raises(ValidationError):
            self.periodo.clean()
