"""Testes do requerimento no modelo padrão da Portaria MEC nº 608/2026."""

from decimal import Decimal

import pytest

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import Nivel, ProcessoRSCTae, Requisito
from rsc_tae.views.documentos import _montar_contexto_requerimento_608


@pytest.mark.django_db(databases='__all__')
class TestRequerimento608:
    ATORES = ('servidor_a',)
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        for numero, romano in enumerate(('I', 'II', 'III', 'IV', 'V', 'VI'), start=1):
            Requisito.objects.get_or_create(
                numero=numero,
                defaults={'descricao': f'Requisito {romano}', 'descricao_curta': f'Req {romano}', 'numeral_romano': romano},
            )

        self.nivel = Nivel.objects.create(nome='Nível IV', ordem=4, numero_minimo_itens=5, pontuacao_minima=Decimal('30.00'))
        self.processo = ProcessoRSCTae.objects.create(vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel)
        ProcessoRSCTae.objects.filter(pk=self.processo.pk).update(situacao=SituacaoProcesso.EM_ANALISE)
        self.processo.refresh_from_db()

    def test_gera_seis_criterios_e_marca_nivel_pretendido(self):
        """A seção 3 traz os 6 critérios (I a VI) e o RSC pretendido é marcado conforme o nível."""
        contexto = _montar_contexto_requerimento_608(self.processo)

        assert len(contexto['criterios']) == 6
        assert [c['numeral'] for c in contexto['criterios']] == ['I', 'II', 'III', 'IV', 'V', 'VI']

        marcados = [nivel_rsc['romano'] for nivel_rsc in contexto['niveis_rsc'] if nivel_rsc['marcado']]
        assert marcados == ['IV']

    def test_campos_pendentes_ficam_como_xxx(self):
        """Campos sem origem no modelo de dados saem como 'XXX' para preenchimento posterior.

        ``data_ingresso`` e ``funcao`` deixaram de ser placeholders: passaram a ser data-driven
        (data de exercício no cargo e função gratificada). Sem esses dados, saem vazios/None.
        """
        contexto = _montar_contexto_requerimento_608(self.processo)

        assert contexto['data_ingresso'] is None
        assert contexto['funcao'] == ''
        assert contexto['num_processo_anterior'] == 'XXX'

    def test_sem_itens_zera_subtotais_totais_e_pontuacao_minima(self):
        """Processo sem itens preenchidos: subtotais/total zerados e pontuação mínima do nível preservada."""
        contexto = _montar_contexto_requerimento_608(self.processo)

        assert contexto['pontos_minimos'] == Decimal('30.00')
        assert contexto['qtd_criterios'] == 0
        assert all(criterio['subtotal'] == Decimal('0') for criterio in contexto['criterios'])
        assert contexto['total_apresentada'] == Decimal('0')

    def test_anexar_requerimento_gera_snapshot_pdf(self):
        """A conclusão anexa o snapshot do requerimento (PDF) ao processo."""
        from rsc_tae.views.documentos import anexar_requerimento_ao_processo

        assert anexar_requerimento_ao_processo(self.processo) is True

        self.processo.refresh_from_db()
        assert self.processo.requerimento_arquivo
        assert self.processo.requerimento_arquivo.name.endswith('.pdf')
