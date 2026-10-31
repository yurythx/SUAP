"""Testes da aba "Comissão" do dashboard (``views/dashboard_comissao.py``).

A tela reproduz o relatório "Trabalho da CRSC": um card por categoria, MEMBRO e TOTAL em ordem
decrescente, total da categoria no rodapé. Os cards são dinâmicos — vêm do cadastro de categorias,
não de uma lista fixa —, e é isso que a maior parte destes testes protege.
"""

from decimal import Decimal

import pytest
from django.template.loader import render_to_string
from django.utils import timezone

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import (
    CategoriaMembroComissaoRSCTae,
    ComissaoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    GrupoSaberCompetencia,
    MembroComissaoRSCTae,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    VotoDeliberacaoFinalRSCTae,
)
from rsc_tae.views.dashboard_comissao import SEM_CATEGORIA, cards_por_categoria, montar_painel_comissao


class BaseComissao:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        self.comissao = ComissaoRSCTae.objects.create(nome='CRSC 2026', data_inicio=timezone.now().date(), ativa=True)
        self.consup = CategoriaMembroComissaoRSCTae.objects.create(nome='CONSUP', ordem=1)
        self.digpe = CategoriaMembroComissaoRSCTae.objects.create(nome='DIGPE', ordem=2)

        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.5'), descricao='G1')
        self.item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(), nivel_requisitado=self.nivel, situacao=SituacaoProcesso.AGUARDANDO_CRSC
        )

    # ---------------------------------------------------------------- helpers

    def _membro(self, servidor, categoria=None, ativo=True):
        return MembroComissaoRSCTae.objects.create(comissao=self.comissao, vinculo=servidor.get_vinculo(), categoria=categoria, ativo=ativo)

    def _votar_item(self, servidor, quantidade=1, desempate=False):
        for numero in range(quantidade):
            anexo = RolSaberCompetenciaAnexo.objects.create(
                processo=self.processo, rol_saber_competencia=self.item, arquivo=f'{servidor.matricula}-{numero}-{desempate}.pdf'
            )
            DeliberacaoItemCRSCRSCTae.objects.create(
                processo=self.processo,
                anexo=anexo,
                decisao=DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR,
                pontuacao_crsc=Decimal('1.00'),
                deliberado_por_vinculo=servidor.get_vinculo(),
                desempate=desempate,
            )

    def _votar_final(self, servidor, desempate=False):
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=servidor.get_vinculo(),
            resultado=SituacaoProcesso.DEFERIDO,
            pontuacao_final=Decimal('1.00'),
            desempate=desempate,
        )

    def _card(self, cards, titulo):
        return next(card for card in cards if card['titulo'] == titulo)


@pytest.mark.django_db(databases='__all__')
class TestCardsPorCategoria(BaseComissao):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    def test_uma_categoria_cadastrada_vira_um_card(self):
        cards = cards_por_categoria()

        assert [card['titulo'] for card in cards] == ['CONSUP', 'DIGPE']

    def test_categoria_nova_aparece_sem_tocar_no_codigo(self):
        """O requisito é ser dinâmico: hoje são três categorias, amanhã podem ser outras."""
        CategoriaMembroComissaoRSCTae.objects.create(nome='CIS-PCCTAE', ordem=3)

        assert [card['titulo'] for card in cards_por_categoria()] == ['CONSUP', 'DIGPE', 'CIS-PCCTAE']

    def test_ordem_dos_cards_segue_o_cadastro(self):
        """Não é alfabética nem por total: a sequência do relatório é uma escolha da comissão."""
        CategoriaMembroComissaoRSCTae.objects.filter(pk=self.digpe.pk).update(ordem=0)

        assert [card['titulo'] for card in cards_por_categoria()] == ['DIGPE', 'CONSUP']

    def test_categoria_sem_membros_aparece_vazia(self):
        """Card vazio sinaliza que ninguém foi associado ainda — some seria pior."""
        card = self._card(cards_por_categoria(), 'CONSUP')

        assert card['linhas'] == []
        assert card['total'] == 0


@pytest.mark.django_db(databases='__all__')
class TestSemCategoria(BaseComissao):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    def test_membro_sem_categoria_ganha_card_proprio(self):
        self._membro(self.servidor_b)

        titulos = [card['titulo'] for card in cards_por_categoria()]

        assert SEM_CATEGORIA in titulos

    def test_card_sem_categoria_vem_por_ultimo(self):
        self._membro(self.servidor_b)
        self._membro(self.servidor_c, categoria=self.consup)

        assert cards_por_categoria()[-1]['titulo'] == SEM_CATEGORIA

    def test_sem_membros_orfaos_o_card_nao_existe(self):
        self._membro(self.servidor_b, categoria=self.consup)

        assert SEM_CATEGORIA not in [card['titulo'] for card in cards_por_categoria()]


@pytest.mark.django_db(databases='__all__')
class TestContagem(BaseComissao):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    def test_total_soma_votos_de_item_e_finais(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=3)
        self._votar_final(self.servidor_b)

        card = self._card(cards_por_categoria(), 'CONSUP')

        assert card['linhas'][0]['total'] == 4

    def test_voto_de_desempate_nao_entra(self):
        """É prerrogativa da presidência: contaria cargo, não trabalho."""
        self._membro(self.servidor_b, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=2)
        self._votar_item(self.servidor_b, quantidade=1, desempate=True)
        self._votar_final(self.servidor_b, desempate=True)

        assert self._card(cards_por_categoria(), 'CONSUP')['linhas'][0]['total'] == 2

    def test_total_da_categoria_e_a_soma_dos_membros(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._membro(self.servidor_c, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=3)
        self._votar_item(self.servidor_c, quantidade=2)

        card = self._card(cards_por_categoria(), 'CONSUP')

        assert card['total'] == 5
        assert card['total'] == sum(linha['total'] for linha in card['linhas'])

    def test_membros_ordenados_do_maior_para_o_menor(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._membro(self.servidor_c, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=1)
        self._votar_item(self.servidor_c, quantidade=5)

        totais = [linha['total'] for linha in self._card(cards_por_categoria(), 'CONSUP')['linhas']]

        assert totais == [5, 1]

    def test_membro_sem_nenhuma_deliberacao_aparece_zerado(self):
        self._membro(self.servidor_b, categoria=self.consup)

        assert self._card(cards_por_categoria(), 'CONSUP')['linhas'][0]['total'] == 0

    def test_membro_inativo_fica_de_fora(self):
        self._membro(self.servidor_b, categoria=self.consup, ativo=False)

        assert self._card(cards_por_categoria(), 'CONSUP')['linhas'] == []

    def test_membro_de_comissao_inativa_fica_de_fora(self):
        ComissaoRSCTae.objects.filter(pk=self.comissao.pk).update(ativa=False)
        self._membro(self.servidor_b, categoria=self.consup)

        assert self._card(cards_por_categoria(), 'CONSUP')['linhas'] == []

    def test_contagem_nao_cresce_com_o_numero_de_membros(self, django_assert_num_queries):
        """Duas consultas agregadas (uma por modelo de voto), mais membros, servidores e categorias."""
        for servidor in (self.servidor_b, self.servidor_c, self.servidor_d):
            self._membro(servidor, categoria=self.consup)

        with django_assert_num_queries(5):
            cards_por_categoria()


@pytest.mark.django_db(databases='__all__')
class TestPainelERenderizacao(BaseComissao):
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    def test_kpis_do_painel(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._membro(self.servidor_c)
        self._votar_item(self.servidor_b, quantidade=2)

        painel = montar_painel_comissao()

        assert painel['total_geral'] == 2
        assert painel['total_membros'] == 2
        assert painel['tem_sem_categoria'] is True

    def test_kpi_de_categorias_ignora_o_card_sem_categoria(self):
        """Com duas categorias cadastradas e membros órfãos, o KPI precisa dizer 2, não 3."""
        self._membro(self.servidor_b, categoria=self.consup)
        self._membro(self.servidor_c)

        painel = montar_painel_comissao()

        assert len(painel['cards']) == 3
        assert painel['total_categorias'] == 2

    def test_painel_sem_comissao_nao_quebra(self):
        ComissaoRSCTae.objects.filter(pk=self.comissao.pk).update(ativa=False)

        painel = montar_painel_comissao()

        assert painel['total_geral'] == 0
        assert painel['tem_sem_categoria'] is False

    def _renderizar(self):
        return render_to_string(
            'rsc_tae/partials/dashboard_comissao.html',
            {'painel_comissao': montar_painel_comissao()},
        )

    def test_renderiza_os_cards_com_nomes_e_totais(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=7)

        html = self._renderizar()

        assert 'CONSUP' in html
        assert self.servidor_b.pessoa_fisica.nome in html
        assert '>7<' in html

    def test_nomes_aparecem_sem_anonimizacao(self):
        """Diferente do painel de avaliadores: aqui o número é volume de trabalho, não avaliação."""
        self._membro(self.servidor_b, categoria=self.consup)
        self._membro(self.servidor_c, categoria=self.digpe)

        html = self._renderizar()

        assert self.servidor_b.pessoa_fisica.nome in html
        assert self.servidor_c.pessoa_fisica.nome in html
        assert 'Membro 1' not in html

    def test_sem_categorias_orienta_o_cadastro(self):
        CategoriaMembroComissaoRSCTae.objects.all().delete()

        html = self._renderizar()

        assert 'Categorias de Membros' in html

    def test_renderiza_o_total_da_categoria(self):
        self._membro(self.servidor_b, categoria=self.consup)
        self._votar_item(self.servidor_b, quantidade=4)

        assert 'Total da categoria' in self._renderizar()
