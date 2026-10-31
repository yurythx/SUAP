"""Testes do management command ``alterar_situacao_processo``.

O command é a ferramenta de saneamento para o caso que motivou sua criação: uma situação
alterada direto pelo formulário do admin não passa por ``ProcessoRSCTae.transicionar()``,
não grava ``HistoricoSituacaoProcessoRSCTae`` e, sem esse registro, a expressão de ordenação
cai em ``data_cadastro`` — o processo aparece no topo da fila da etapa em vez do fim.

Por isso os testes olham para o efeito observável (posição na fila, histórico gravado) e não
apenas para o campo ``situacao``.
"""

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import HistoricoSituacaoProcessoRSCTae, Nivel, ProcessoRSCTae


@pytest.mark.django_db(databases='__all__')
class TestAlterarSituacaoProcessoCommand:
    ATORES = ('servidor_a', 'servidor_b')
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, atores):
        self.nivel = Nivel.objects.create(nome='Nível Teste', numero_minimo_itens=0, pontuacao_minima=0)

    def _processo(self, servidor, situacao=SituacaoProcesso.EM_ANALISE, entrou_ha_dias=0):
        """Processo já na situação desejada, com a entrada nela datada no passado."""
        processo = ProcessoRSCTae.objects.create(
            vinculo=servidor.get_vinculo(),
            nivel_requisitado=self.nivel,
            situacao=situacao,
        )
        historico = HistoricoSituacaoProcessoRSCTae.objects.create(
            processo=processo,
            situacao_anterior=None,
            situacao_nova=situacao,
        )
        quando = timezone.now() - timedelta(days=entrou_ha_dias)
        HistoricoSituacaoProcessoRSCTae.objects.filter(pk=historico.pk).update(data_transicao=quando)
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(data_cadastro=quando)
        processo.refresh_from_db()
        return processo

    def _rodar(self, processo, **kwargs):
        saida = io.StringIO()
        call_command('alterar_situacao_processo', processo.pk, stdout=saida, stderr=saida, **kwargs)
        return saida.getvalue()

    # ------------------------------------------------------------------ aplicação

    def test_transicao_valida_grava_historico(self):
        processo = self._processo(self.servidor_a, entrou_ha_dias=300)

        self._rodar(processo, para='aguardando-crsc', motivo='Correção administrativa.', commit=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC
        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=processo).latest('data_transicao')
        assert registro.situacao_nova == SituacaoProcesso.AGUARDANDO_CRSC
        assert registro.motivo == 'Correção administrativa.'

    def test_processo_alterado_entra_no_fim_da_fila_da_etapa(self):
        """O efeito que o saneamento precisa produzir: entrar na fila agora, não pela idade do cadastro."""
        self._processo(self.servidor_b, situacao=SituacaoProcesso.AGUARDANDO_CRSC, entrou_ha_dias=5)
        antigo = self._processo(self.servidor_a, situacao=SituacaoProcesso.EM_ANALISE, entrou_ha_dias=300)

        self._rodar(antigo, para='aguardando-crsc', motivo='Correção administrativa.', commit=True)

        antigo.refresh_from_db()
        assert antigo.posicao_na_fila() == {'posicao': 2, 'total': 2}

    def test_aceita_o_codigo_numerico_da_situacao(self):
        processo = self._processo(self.servidor_a)

        self._rodar(processo, para=str(SituacaoProcesso.AGUARDANDO_CRSC), motivo='Correção.', commit=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC

    def test_responsavel_por_matricula_vai_para_o_historico(self):
        processo = self._processo(self.servidor_a)

        self._rodar(
            processo,
            para='aguardando-crsc',
            motivo='Correção.',
            responsavel_matricula=self.servidor_b.matricula,
            commit=True,
        )

        registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=processo).latest('data_transicao')
        assert registro.realizado_por_vinculo_id == self.servidor_b.get_vinculo().id

    # ------------------------------------------------------------------ simulação

    def test_sem_commit_nao_grava(self):
        processo = self._processo(self.servidor_a)

        saida = self._rodar(processo, para='aguardando-crsc', motivo='Correção.')

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.EM_ANALISE
        assert not HistoricoSituacaoProcessoRSCTae.objects.filter(processo=processo, situacao_nova=SituacaoProcesso.AGUARDANDO_CRSC).exists()
        assert 'SIMULAÇÃO' in saida

    def test_listar_mostra_destinos_validos_sem_alterar(self):
        processo = self._processo(self.servidor_a)

        saida = self._rodar(processo, listar=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.EM_ANALISE
        assert 'aguardando-crsc' in saida
        assert 'aguardando-correcao' in saida

    # ------------------------------------------------------------------ recusas

    def test_destino_invalido_e_recusado(self):
        processo = self._processo(self.servidor_a)

        with pytest.raises(CommandError, match='não é uma transição válida'):
            self._rodar(processo, para='aguardando-preenchimento', motivo='Correção.', commit=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.EM_ANALISE

    def test_destino_final_e_recusado_apontando_a_deliberacao(self):
        """Deferir/indeferir exige quórum da CRSC e crédito no banco de pontos — não passa por aqui."""
        processo = self._processo(self.servidor_a, situacao=SituacaoProcesso.AGUARDANDO_CRSC)

        with pytest.raises(CommandError, match='deliberação'):
            self._rodar(processo, para='deferido', motivo='Correção.', commit=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC

    def test_sair_de_processo_finalizado_aponta_o_comando_de_reversao(self):
        processo = self._processo(self.servidor_a, situacao=SituacaoProcesso.DEFERIDO)

        with pytest.raises(CommandError, match='reverter_deliberacao_final'):
            self._rodar(processo, para='aguardando-crsc', motivo='Correção.', commit=True)

    def test_motivo_e_obrigatorio(self):
        processo = self._processo(self.servidor_a)

        with pytest.raises(CommandError, match='--motivo'):
            self._rodar(processo, para='aguardando-crsc', commit=True)

    def test_processo_inexistente(self):
        with pytest.raises(CommandError, match='não encontrado'):
            call_command('alterar_situacao_processo', 999999, listar=True, stdout=io.StringIO())

    # ------------------------------------------------------------------ avisos

    def test_avisa_quando_avaliadores_ainda_nao_finalizaram(self):
        """Pré-condição não satisfeita é aviso, não bloqueio: a tela de saneamento precisa poder agir."""
        processo = self._processo(self.servidor_a)
        processo.avaliadores.add(self.servidor_b.get_vinculo())

        saida = self._rodar(processo, para='aguardando-crsc', motivo='Correção.', commit=True)

        processo.refresh_from_db()
        assert processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC
        assert 'ATENÇÃO' in saida

    def test_responsavel_por_matricula_resolve_o_vinculo_daquela_matricula(self):
        """Duas matrículas da mesma pessoa (ex.: TAE que também é docente) são dois vínculos.

        A busca precisa partir do vínculo: partindo da pessoa, QUALQUER uma das matrículas dela
        alcança os DOIS vínculos e o registro de auditoria fica com um deles ao acaso. Por isso o
        teste cobra as duas matrículas — assim nenhuma ordem de retorno acidental o satisfaz.
        """
        from rh.models import Servidor

        segundo = Servidor.objects.create(
            matricula='5555555',
            pessoa_fisica=self.servidor_b.pessoa_fisica,
            situacao=self.servidor_b.situacao,
            cargo_emprego=self.servidor_b.cargo_emprego,
            setor=self.servidor_b.setor,
            setor_lotacao=self.servidor_b.setor_lotacao,
            setor_exercicio=self.servidor_b.setor_exercicio,
            jornada_trabalho=self.servidor_b.jornada_trabalho,
            data_inicio_exercicio_na_instituicao=self.servidor_b.data_inicio_exercicio_na_instituicao,
            data_inicio_exercicio_no_cargo=self.servidor_b.data_inicio_exercicio_no_cargo,
        )

        for matricula, esperado in ((self.servidor_b.matricula, self.servidor_b), ('5555555', segundo)):
            processo = self._processo(self.servidor_a)
            self._rodar(processo, para='aguardando-crsc', motivo='Correção.', responsavel_matricula=matricula, commit=True)

            registro = HistoricoSituacaoProcessoRSCTae.objects.filter(processo=processo).latest('data_transicao')
            assert registro.realizado_por_vinculo_id == esperado.get_vinculo().id, f'matrícula {matricula} resolveu para o vínculo errado'
