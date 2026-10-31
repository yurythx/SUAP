"""Testes do management command ``remover_avaliador_processo``.

Remover um avaliador só pelo M2M (o que o formulário do admin faz) deixa rastro: a
``AvaliacaoProcessoRSCTae`` continua ativa e entra na média e no "todos finalizaram",
e as ``AvaliacaoAnexoRSCTae`` continuam aparecendo nas divergências que a CRSC delibera —
nenhum desses cálculos lê o M2M. O command existe para fechar esses três pontos de uma vez,
registrando a auditoria da remoção.
"""

import io
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from rsc_tae.enums import SituacaoAvaliacaoItem, SituacaoProcesso
from rsc_tae.models import (
    AvaliacaoAnexoRSCTae,
    AvaliacaoProcessoRSCTae,
    GrupoSaberCompetencia,
    Nivel,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    SorteioAvaliadorRSCTae,
    VotoDeliberacaoFinalRSCTae,
)


@pytest.mark.django_db(databases='__all__')
class TestRemoverAvaliadorProcessoCommand:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)
        self.processo = ProcessoRSCTae.objects.create(
            vinculo=self.servidor_a.get_vinculo(),
            nivel_requisitado=nivel,
            situacao=SituacaoProcesso.EM_ANALISE,
        )

        requisito = Requisito.objects.create(numero=1, descricao='Requisito I', descricao_curta='I', numeral_romano='I')
        grupo = GrupoSaberCompetencia.objects.create(requisito=requisito, numero=1, pontuacao_unidade=Decimal('0.500'), descricao='Grupo 1')
        item = RolSaberCompetencia.objects.create(numero=1, grupo=grupo, titulo='Item', descricao='Item', unidade_medida='unidade')
        self.anexo = RolSaberCompetenciaAnexo.objects.create(processo=self.processo, rol_saber_competencia=item, arquivo='x.pdf')

        # Quatro avaliadores: remover um deixa os três que o regulamento exige.
        self.avaliadores = [self.servidor_b, self.servidor_c, self.servidor_d, self.admin]
        for servidor, pontuacao in zip(self.avaliadores, ['10.00', '10.00', '10.00', '2.00'], strict=False):
            self._designar(servidor, Decimal(pontuacao))

        self.removido = self.admin

    def _designar(self, servidor, pontuacao):
        vinculo = servidor.get_vinculo()
        self.processo.avaliadores.add(vinculo)
        AvaliacaoProcessoRSCTae.objects.create(
            processo=self.processo,
            avaliador_vinculo=vinculo,
            finalizada=True,
            pontuacao_final=pontuacao,
        )
        AvaliacaoAnexoRSCTae.objects.create(
            anexo=self.anexo,
            avaliador_vinculo=vinculo,
            situacao=SituacaoAvaliacaoItem.DEFERIDO,
            pontuacao_validada=pontuacao,
        )

    def _rodar(self, **kwargs):
        saida = io.StringIO()
        call_command('remover_avaliador_processo', self.processo.pk, stdout=saida, stderr=saida, **kwargs)
        return saida.getvalue()

    def _remover_admin(self, **kwargs):
        return self._rodar(avaliador_matriculas=[self.removido.matricula], motivo='Designado indevidamente.', **kwargs)

    # ------------------------------------------------------------------ remoção

    def test_remove_do_m2m(self):
        self._remover_admin(commit=True)

        assert not self.processo.avaliadores.filter(pk=self.removido.get_vinculo().pk).exists()

    def test_marca_a_avaliacao_do_processo_como_substituida_sem_apagar(self):
        """A linha fica para auditoria; o que muda é ela deixar de contar."""
        self._remover_admin(commit=True)

        avaliacao = AvaliacaoProcessoRSCTae.objects.get(processo=self.processo, avaliador_vinculo=self.removido.get_vinculo())
        assert avaliacao.substituido is True

    def test_apaga_as_avaliacoes_de_anexo_do_removido(self):
        """Sem isso, os itens dele continuariam nas divergências que a CRSC delibera."""
        self._remover_admin(commit=True)

        assert not AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=self.processo, avaliador_vinculo=self.removido.get_vinculo()).exists()
        assert AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=self.processo).count() == 3

    def test_media_deixa_de_considerar_o_removido(self):
        assert self.processo.media_pontuacao_avaliadores == Decimal('8.00')

        self._remover_admin(commit=True)

        self.processo.refresh_from_db()
        assert self.processo.media_pontuacao_avaliadores == Decimal('10.00')

    def test_registra_auditoria_da_remocao(self):
        self._remover_admin(commit=True)

        registro = SorteioAvaliadorRSCTae.objects.get(processo=self.processo, avaliador_substituido=self.removido.get_vinculo())
        assert registro.motivo == SorteioAvaliadorRSCTae.MOTIVO_REMOCAO_ADMINISTRATIVA
        assert registro.avaliador_sorteado is None
        assert registro.justificativa == 'Designado indevidamente.'

    def test_responsavel_por_matricula_fica_registrado(self):
        self._rodar(
            avaliador_matriculas=[self.removido.matricula],
            motivo='Designado indevidamente.',
            responsavel_matricula=self.servidor_b.matricula,
            commit=True,
        )

        registro = SorteioAvaliadorRSCTae.objects.get(processo=self.processo, avaliador_substituido=self.removido.get_vinculo())
        assert registro.realizado_por_vinculo_id == self.servidor_b.get_vinculo().id

    def test_aceita_processo_em_aguardando_crsc(self):
        """O caso que motivou o comando: o processo já tinha passado para a deliberação da CRSC."""
        self.processo.situacao = SituacaoProcesso.AGUARDANDO_CRSC
        self.processo.save()

        self._remover_admin(commit=True)

        assert not self.processo.avaliadores.filter(pk=self.removido.get_vinculo().pk).exists()

    # ------------------------------------------------------------------ simulação e listagem

    def test_sem_commit_nao_grava(self):
        saida = self._remover_admin()

        assert self.processo.avaliadores.filter(pk=self.removido.get_vinculo().pk).exists()
        assert AvaliacaoAnexoRSCTae.objects.filter(anexo__processo=self.processo).count() == 4
        assert 'SIMULAÇÃO' in saida

    def test_listar_mostra_os_avaliadores_sem_alterar(self):
        saida = self._rodar(listar=True)

        assert self.processo.avaliadores.count() == 4
        assert str(self.removido.matricula) in saida

    # ------------------------------------------------------------------ recusas

    def test_recusa_quando_restariam_menos_de_tres(self):
        with pytest.raises(CommandError, match='três'):
            self._rodar(
                avaliador_matriculas=[self.removido.matricula, self.servidor_d.matricula],
                motivo='Designados indevidamente.',
                commit=True,
            )

        assert self.processo.avaliadores.count() == 4

    def test_recusa_avaliador_que_nao_esta_no_processo(self):
        with pytest.raises(CommandError, match='não está designado'):
            self._rodar(avaliador_matriculas=[self.servidor_a.matricula], motivo='Teste.', commit=True)

    def test_recusa_situacao_fora_de_analise_ou_deliberacao(self):
        self.processo.situacao = SituacaoProcesso.AGUARDANDO_PREENCHIMENTO
        self.processo.save()

        with pytest.raises(CommandError, match='Em Análise'):
            self._remover_admin(commit=True)

    def test_recusa_quando_ja_ha_voto_de_deliberacao_final(self):
        """Remover muda a média por baixo de votos já dados — a reversão é o caminho."""
        VotoDeliberacaoFinalRSCTae.objects.create(
            processo=self.processo,
            deliberado_por_vinculo=self.servidor_b.get_vinculo(),
            resultado=SituacaoProcesso.DEFERIDO,
            pontuacao_final=Decimal('10.00'),
        )

        with pytest.raises(CommandError, match='reverter_deliberacao_final'):
            self._remover_admin(commit=True)

        assert self.processo.avaliadores.count() == 4

    def test_motivo_e_obrigatorio(self):
        with pytest.raises(CommandError, match='--motivo'):
            self._rodar(avaliador_matriculas=[self.removido.matricula], commit=True)

    def test_recusa_alvo_repetido(self):
        """Repetir a matrícula geraria dois registros de auditoria e contaria duas saídas."""
        with pytest.raises(CommandError, match='mais de uma vez'):
            self._rodar(
                avaliador_matriculas=[self.removido.matricula, self.removido.matricula],
                motivo='Designado indevidamente.',
                commit=True,
            )

        assert self.processo.avaliadores.count() == 4
