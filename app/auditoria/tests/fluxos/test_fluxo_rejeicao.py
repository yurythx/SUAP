"""Regressão + reparo: posicionamento de Rejeição não pode deixar a solicitação
de providência presa em "Aguardando Posicionamento".

Cenário: o auditado pede revisão (manifestação SOLICITACAO_REVISAO) e o auditor
publica uma rejeição (posicionamento REJEITAR_SOLICITACAO). A rejeição deve
analisar a manifestação e reabrir a solicitação para nova ciência (a demanda
original permanece), em vez de travar o fluxo.

Cobre também o comando ``corrigir_solicitacoes_travadas``, que destrava casos
legados (publicados antes da correção do handler).
"""

from __future__ import annotations

from django.core.management import call_command

from auditoria.models import Motivacao, Posicionamento, TipoPosicionamentoValido
from auditoria.models.manifestacao import ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.models.posicionamento import PosicionamentoStatus, TipoPosicionamento
from auditoria.models.providencia import SolicitacaoProvidenciaStatus
from auditoria.tests import factories as f
from djtools.utils import get_datetime_now


def _reload(obj):
    return type(obj).objects.get(pk=obj.pk)


def preparar_revisao_recebida(cenario):
    """Leva o monitoramento até: gestor pediu revisão e o auditor recebeu.

    Retorna ``(manifestacao, solicitacao, motivacao_rs)`` com a solicitação em
    AGUARDANDO_POSICIONAMENTO e a manifestação em RECEBIDA.

    Idempotente o suficiente para ser chamado mais de uma vez sobre o mesmo cenário
    (reaproveita o monitoramento já iniciado e a motivação), permitindo montar
    múltiplas solicitações travadas em um único monitoramento.
    """
    mon = _reload(cenario.monitoramento)

    TipoPosicionamentoValido.objects.get_or_create(
        tipo_manifestacao=TipoManifestacao.SOLICITACAO_REVISAO,
        tipo_posicionamento=TipoPosicionamento.REJEITAR_SOLICITACAO,
    )
    motivacao_rs, _ = Motivacao.objects.get_or_create(tipo_posicionamento=TipoPosicionamento.REJEITAR_SOLICITACAO, motivo='Solicitação improcedente')

    solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=cenario.setor)
    if mon.status == MonitoramentoStatus.REGISTRADO:
        mon.iniciar_monitoramento()
        mon.save()
    solicitacao = _reload(solicitacao)
    solicitacao.informar_ciencia(cenario.gestor_user)
    solicitacao.save()

    manifestacao = f.ManifestacaoFactory(
        monitoramento=mon,
        solicitacao_providencia=solicitacao,
        incluido_por=cenario.gestor_user,
        tipo=TipoManifestacao.SOLICITACAO_REVISAO,
    )
    manifestacao.enviar(cenario.gestor_user)
    manifestacao.save()
    manifestacao.receber(cenario.auditor_user)
    manifestacao.save()
    return manifestacao, _reload(solicitacao), motivacao_rs


class TestRejeicaoNaoTravaSolicitacao:
    def test_rejeitar_revisao_reabre_solicitacao(self, cenario_atendimento):
        c = cenario_atendimento
        manifestacao, solicitacao, motivacao_rs = preparar_revisao_recebida(c)
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO
        assert manifestacao.status == ManifestacaoStatus.RECEBIDA

        posicionamento = f.PosicionamentoFactory(
            manifestacao=manifestacao,
            incluido_por=c.auditor_user,
            tipo=TipoPosicionamento.REJEITAR_SOLICITACAO,
            motivacao=motivacao_rs,
        )
        posicionamento.publicar(c.auditor_user)
        posicionamento.save()

        solicitacao = _reload(solicitacao)
        manifestacao = _reload(manifestacao)
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_CIENTE
        assert manifestacao.status == ManifestacaoStatus.ANALISADA


class TestComandoCorrigeSolicitacoesTravadas:
    def _criar_caso_travado_legado(self, cenario):
        """Simula dado legado: posicionamento de Rejeição PUBLICADO cuja pós-transição
        nunca rodou (escreve o status direto, sem passar por ``save``/handler)."""
        manifestacao, solicitacao, motivacao_rs = preparar_revisao_recebida(cenario)
        posicionamento = f.PosicionamentoFactory(
            manifestacao=manifestacao,
            incluido_por=cenario.auditor_user,
            tipo=TipoPosicionamento.REJEITAR_SOLICITACAO,
            motivacao=motivacao_rs,
        )
        Posicionamento.objects.filter(pk=posicionamento.pk).update(
            status=PosicionamentoStatus.PUBLICADO,
            publicado_por=cenario.auditor_vinculo,
            publicado_em=get_datetime_now(),
        )
        return manifestacao, solicitacao, posicionamento

    def test_dry_run_nao_altera(self, cenario_atendimento):
        manifestacao, solicitacao, _ = self._criar_caso_travado_legado(cenario_atendimento)
        call_command('corrigir_solicitacoes_travadas')
        assert _reload(solicitacao).status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO
        assert _reload(manifestacao).status == ManifestacaoStatus.RECEBIDA

    def test_apply_destrava(self, cenario_atendimento):
        manifestacao, solicitacao, _ = self._criar_caso_travado_legado(cenario_atendimento)
        call_command('corrigir_solicitacoes_travadas', '--apply')
        assert _reload(solicitacao).status == SolicitacaoProvidenciaStatus.STATUS_CIENTE
        assert _reload(manifestacao).status == ManifestacaoStatus.ANALISADA

    def test_apply_isola_falha_por_item(self, cenario_atendimento, monkeypatch):
        """Uma travada que falha ao corrigir não pode abortar as demais: o comando
        reporta o erro daquele item e segue corrigindo o restante do lote."""
        _, solic_falha, pos_falha = self._criar_caso_travado_legado(cenario_atendimento)
        _, solic_ok, _ = self._criar_caso_travado_legado(cenario_atendimento)

        original = Posicionamento.handle_post_transition

        def handle_com_falha(self):
            if self.pk == pos_falha.pk:
                raise RuntimeError('falha simulada na pós-transição')
            return original(self)

        monkeypatch.setattr(Posicionamento, 'handle_post_transition', handle_com_falha)

        call_command('corrigir_solicitacoes_travadas', '--apply')

        # O item com falha permanece travado; o item saudável é destravado.
        assert _reload(solic_falha).status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO
        assert _reload(solic_ok).status == SolicitacaoProvidenciaStatus.STATUS_CIENTE
