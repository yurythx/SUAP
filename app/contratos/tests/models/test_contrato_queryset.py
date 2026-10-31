from datetime import date
from decimal import Decimal

from contratos.models import Contrato, TipoContrato
import pytest

from rh.tests.factories import PessoaJuridicaFactory


pytestmark = pytest.mark.django_db


class ContratoQuerysetBaseSetup:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        self.tipo_contrato = TipoContrato.objects.create(descricao='Teste')
        # O contrato aponta para o VÍNCULO da pessoa jurídica, não para ela.
        self.vinculo = PessoaJuridicaFactory().get_vinculo()
        self.contrato_kwargs = {
            'tipo': self.tipo_contrato,
            'valor': Decimal('1000.00'),
            'data_inicio': date(2024, 1, 1),
            'objeto': 'Teste',
            'vinculo_contratado': self.vinculo,
        }

    def _criar_contrato(self, numero='00001/2024', **extra):
        return Contrato.objects.create(numero=numero, **self.contrato_kwargs, **extra)


class ContratoQuerysetAtivosTest(ContratoQuerysetBaseSetup):
    """Testa o método ativos do ContratoQueryset."""

    def test_ativos_retorna_contratos_nao_concluidos_e_nao_cancelados(self):
        """ativos retorna apenas contratos com concluido=False e cancelado=False."""
        ativo = self._criar_contrato(concluido=False, cancelado=False)
        self._criar_contrato('00002/2024', concluido=True, cancelado=False)
        self._criar_contrato('00003/2024', concluido=False, cancelado=True)
        self._criar_contrato('00004/2024', concluido=True, cancelado=True)
        result = Contrato.objects.ativos()
        assert list(result) == [ativo]


class ContratoQuerysetConcluidosTest(ContratoQuerysetBaseSetup):
    """Testa o método concluidos do ContratoQueryset."""

    def test_concluidos_retorna_contratos_concluidos_e_nao_cancelados(self):
        """concluidos retorna apenas contratos com concluido=True e cancelado=False."""
        concluido = self._criar_contrato(concluido=True, cancelado=False)
        self._criar_contrato('00002/2024', concluido=False, cancelado=False)
        self._criar_contrato('00003/2024', concluido=True, cancelado=True)
        result = Contrato.objects.concluidos()
        assert list(result) == [concluido]


class ContratoQuerysetComVigenciaExpiradaTest(ContratoQuerysetBaseSetup):
    """Testa o método com_vigencia_expirada do ContratoQueryset."""

    def test_com_vigencia_expirada_quando_vencimento_passado_retorna_contrato(self):
        """com_vigencia_expirada retorna contratos com data_vencimento no passado."""
        expirado = self._criar_contrato(
            concluido=False,
            cancelado=False,
            data_fim=date(2020, 1, 2),
        )
        result = Contrato.objects.com_vigencia_expirada()
        assert list(result) == [expirado]

    def test_com_vigencia_expirada_quando_vencimento_futuro_retorna_vazio(self):
        """com_vigencia_expirada nao retorna contratos com data_vencimento no futuro."""
        self._criar_contrato(
            concluido=False,
            cancelado=False,
            data_fim=date(2099, 1, 1),
        )
        result = Contrato.objects.com_vigencia_expirada()
        assert list(result) == []

    def test_com_vigencia_expirada_ignora_contratos_concluidos(self):
        """com_vigencia_expirada ignora contratos concluidos mesmo com vencimento passado."""
        self._criar_contrato(
            '00002/2024',
            concluido=True,
            cancelado=False,
            data_fim=date(2020, 1, 2),
        )
        result = Contrato.objects.com_vigencia_expirada()
        assert list(result) == []

    def test_com_vigencia_expirada_ignora_contratos_cancelados(self):
        """com_vigencia_expirada ignora contratos cancelados mesmo com vencimento passado."""
        self._criar_contrato(
            '00002/2024',
            concluido=False,
            cancelado=True,
            data_fim=date(2020, 1, 2),
        )
        result = Contrato.objects.com_vigencia_expirada()
        assert list(result) == []
