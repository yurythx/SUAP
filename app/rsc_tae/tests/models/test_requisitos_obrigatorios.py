from decimal import Decimal

import pytest

from rsc_tae.models import (
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaPreenchimento,
)
from rsc_tae.views._helpers import status_requisitos_obrigatorios


@pytest.mark.django_db(databases='__all__')
class TestStatusRequisitosObrigatorios:
    """RN04: status dos requisitos obrigatórios do nível (indicador do resumo do formulário)."""

    ATORES = ('servidor_a',)

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.requisito = Requisito.objects.create(
            numero=4, descricao='Produção técnica', descricao_curta='IV - Produção técnica', numeral_romano='IV'
        )
        self.grupo = GrupoSaberCompetencia.objects.create(requisito=self.requisito, numero=1, pontuacao_unidade=Decimal('1.000'))
        self.item = RolSaberCompetencia.objects.create(numero=1, grupo=self.grupo, titulo='Item IV', descricao='x', unidade_medida='un')
        self.nivel = Nivel.objects.create(nome='RSC-IV', numero_minimo_itens=1, pontuacao_minima=Decimal('3.00'))
        self.nivel.requisitos_obrigatorios.set([self.requisito])
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel)

    def test_aplicavel_e_pendente_sem_pontuacao(self):
        st = status_requisitos_obrigatorios(self.processo)
        assert st['aplicavel'] is True
        assert st['alcancado'] is False
        assert 'IV - Produção técnica' in st['labels']

    def test_alcancado_quando_pontua_no_requisito_obrigatorio(self):
        RolSaberCompetenciaPreenchimento.objects.create(vinculo=self.processo.vinculo, rol_saber_competencia=self.item, quantidade=2)
        st = status_requisitos_obrigatorios(self.processo)
        assert st['alcancado'] is True

    def test_nao_aplicavel_quando_nivel_sem_requisitos_obrigatorios(self):
        self.nivel.requisitos_obrigatorios.clear()
        st = status_requisitos_obrigatorios(self.processo)
        assert st['aplicavel'] is False
        assert st['alcancado'] is False
