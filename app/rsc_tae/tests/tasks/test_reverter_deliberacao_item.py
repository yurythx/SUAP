"""Testes do management command ``reverter_deliberacao_item``.

Cobrem principalmente o modo ``--somente-desempate``, que remove o voto de minerva do
presidente preservando os votos dos membros — o item volta a ``aguardando_desempate``
em vez de reabrir para nova votação.
"""

import io
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import (
    ConfiguracaoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
)
from rsc_tae.views._helpers import quantidade_deliberacoes_item, status_deliberacao_item


@pytest.mark.django_db(databases='__all__')
class TestReverterDeliberacaoItemSomenteDesempate:
    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        # Quórum 2 para caber nos quatro servidores da fixture: dono + 2 membros + presidente.
        ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=2)

        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )

        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.anexo = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='x.pdf')

        # Dois votos normais empatados (1.00 x 0) + a minerva do presidente.
        self.voto_membro_b = self._votar(self.servidor_b, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))
        self.voto_membro_c = self._votar(self.servidor_c, DeliberacaoItemCRSCRSCTae.DECISAO_INDEFERIR, None)
        self.voto_desempate = self._votar(self.servidor_d, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'), desempate=True)

    def _votar(self, servidor, decisao, pontuacao, desempate=False):
        return DeliberacaoItemCRSCRSCTae.objects.create(
            processo=self.processo,
            anexo=self.anexo,
            decisao=decisao,
            pontuacao_crsc=pontuacao,
            deliberado_por_vinculo=servidor.get_vinculo(),
            desempate=desempate,
        )

    def _status_do_anexo(self):
        votos = list(DeliberacaoItemCRSCRSCTae.objects.filter(processo=self.processo, anexo=self.anexo))
        return status_deliberacao_item(votos, quantidade_deliberacoes_item())

    # ------------------------------------------------------------------ #

    def test_item_comeca_consolidado_pela_minerva(self):
        status = self._status_do_anexo()
        assert status['fechado'] is True
        assert status['empatado'] is True

    def test_remove_apenas_a_minerva_e_preserva_os_votos_dos_membros(self):
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            anexos=[self.anexo.pk],
            membro_vinculos=[self.servidor_d.get_vinculo().pk],
            somente_desempate=True,
            commit=True,
        )

        assert not DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_desempate.pk).exists()
        assert DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_membro_b.pk).exists()
        assert DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_membro_c.pk).exists()

    def test_item_volta_a_aguardar_desempate_sem_ninguem_revotar(self):
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            anexos=[self.anexo.pk],
            membro_vinculos=[self.servidor_d.get_vinculo().pk],
            somente_desempate=True,
            commit=True,
        )

        status = self._status_do_anexo()
        assert status['fechado'] is False
        assert status['aguardando_desempate'] is True
        assert status['total'] == 2  # quórum dos membros segue completo

    def test_simulacao_nao_grava(self):
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            anexos=[self.anexo.pk],
            membro_vinculos=[self.servidor_d.get_vinculo().pk],
            somente_desempate=True,
        )

        assert DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_desempate.pk).exists()
        assert self._status_do_anexo()['fechado'] is True

    def test_sem_a_flag_o_presidente_com_so_minerva_nao_e_encontrado(self):
        """Regressão: o modo normal filtra ``desempate=False`` e não alcança a minerva isolada."""
        with pytest.raises(CommandError, match='Nenhum voto de item encontrado'):
            call_command(
                'reverter_deliberacao_item',
                self.processo.pk,
                anexos=[self.anexo.pk],
                membro_vinculos=[self.servidor_d.get_vinculo().pk],
                commit=True,
            )

    def test_mensagem_final_nao_convoca_a_comissao_a_revotar(self):
        """A última linha é a que o operador lê na tela de manutenção — não pode contradizer a flag."""
        saida = io.StringIO()
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            anexos=[self.anexo.pk],
            membro_vinculos=[self.servidor_d.get_vinculo().pk],
            somente_desempate=True,
            commit=True,
            stdout=saida,
        )

        texto = saida.getvalue()
        assert 'reaberto' not in texto.lower()
        assert 'aguardando o desempate do presidente — nenhum membro precisa revotar' in texto

    def test_modo_normal_remove_voto_do_membro_e_derruba_a_minerva_junto(self):
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            anexos=[self.anexo.pk],
            membro_vinculos=[self.servidor_b.get_vinculo().pk],
            commit=True,
        )

        assert not DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_membro_b.pk).exists()
        assert not DeliberacaoItemCRSCRSCTae.objects.filter(pk=self.voto_desempate.pk).exists()
        status = self._status_do_anexo()
        assert status['fechado'] is False
        assert status['aguardando_desempate'] is False
        assert status['total'] == 1


@pytest.mark.django_db(databases='__all__')
class TestReverterDeliberacaoItemLoteMisto:
    """Lote em que um anexo termina aguardando desempate e outro termina reaberto.

    O relatório precisa orientar os DOIS públicos: o presidente, no anexo empatado, e os
    membros, no anexo que voltou a aceitar votos normais.
    """

    ATORES = ('servidor_a', 'servidor_b', 'servidor_c', 'servidor_d')

    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):

        ConfiguracaoRSCTae.objects.create(quantidade_deliberacoes_item=2)
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.AGUARDANDO_CRSC,
        )
        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')

        # Anexo com 3 votos (acima do quórum 2): remover o do servidor_b deixa 1.00 x 0 empatados.
        self.anexo_empate = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='a.pdf')
        self._votar(self.anexo_empate, self.servidor_b, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))
        self._votar(self.anexo_empate, self.servidor_c, DeliberacaoItemCRSCRSCTae.DECISAO_INDEFERIR, None)
        self._votar(self.anexo_empate, self.servidor_d, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))

        # Anexo no quórum exato: remover o do servidor_b derruba para 1 de 2 e reabre.
        self.anexo_reabre = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='b.pdf')
        self._votar(self.anexo_reabre, self.servidor_b, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))
        self._votar(self.anexo_reabre, self.servidor_c, DeliberacaoItemCRSCRSCTae.DECISAO_DEFERIR, Decimal('1.00'))

    def _votar(self, anexo, servidor, decisao, pontuacao):
        return DeliberacaoItemCRSCRSCTae.objects.create(
            processo=self.processo,
            anexo=anexo,
            decisao=decisao,
            pontuacao_crsc=pontuacao,
            deliberado_por_vinculo=servidor.get_vinculo(),
        )

    def _rodar(self):
        saida = io.StringIO()
        call_command(
            'reverter_deliberacao_item',
            self.processo.pk,
            membro_vinculos=[self.servidor_b.get_vinculo().pk],
            commit=True,
            stdout=saida,
        )
        return saida.getvalue()

    def test_orienta_presidente_e_membros_no_mesmo_lote(self):
        texto = self._rodar()

        assert f'Anexo(s) #{self.anexo_empate.pk}: o presidente da comissão registra o desempate' in texto
        assert 'Os membros reabrem o item pela tela de Deliberação da CRSC' in texto

    def test_mensagem_final_distingue_os_dois_grupos(self):
        texto = self._rodar()

        assert f'anexo(s) #{self.anexo_reabre.pk} reaberto(s) para nova deliberação' in texto
        assert f'anexo(s) #{self.anexo_empate.pk} aguardando o desempate do presidente' in texto

    def test_detalhe_do_empate_nao_afirma_que_os_votos_foram_mantidos(self):
        """No modo normal os votos foram removidos, não mantidos — a frase precisa ser neutra."""
        texto = self._rodar()

        assert 'foram mantidos' not in texto
        assert 'aguardando desempate — restaram 2 voto(s) dos membros, empatados' in texto
