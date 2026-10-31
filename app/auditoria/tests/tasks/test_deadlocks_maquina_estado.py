"""Regressões de máquina de estado (candidatos do spec maquinas-de-estado.md).

4.1 — Cancelar um monitoramento cuja solicitação está em AGUARDANDO_POSICIONAMENTO
      não pode quebrar (a origem de SolicitacaoProvidencia.cancelar precisa aceitar
      AGUARDANDO_POSICIONAMENTO, já que Monitoramento.cancelar a chama quando `ativa`).

4.2 — Recomendação em PARCIALMENTE_ATENDIDA que tem o último monitoramento finalizado
      (não atendido) deve ir para NAO_ATENDIDA (a origem de marcar_como_nao_atendida
      precisa aceitar PARCIALMENTE_ATENDIDA, pois handle_status_monitoramentos a dispara
      nesse estado).
"""

from __future__ import annotations

from django.core.management import call_command

from auditoria.models import Monitoramento
from auditoria.models.manifestacao import TipoManifestacao
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.models.posicionamento import ParecerChoices, Posicionamento, PosicionamentoStatus, RevisaoPosicionamento, TipoPosicionamento
from auditoria.models.providencia import SolicitacaoProvidenciaStatus
from auditoria.models.recomendacao import RecomendacaoStatus
from auditoria.tests import factories as f
from rh.tests.factories import ServidorFactory, SetorFactory


def _reload(obj):
    return type(obj).objects.get(pk=obj.pk)


def montar_em_revisao(c):
    """Leva o fluxo até: posicionamento EM_REVISAO (com uma revisão), monitoramento EM_REVISAO.

    Retorna ``(monitoramento, posicionamento, revisao, revisor_vinculo, revisor_user)``.

    Seguro para ser chamado mais de uma vez sobre o mesmo cenário (reaproveita o
    monitoramento já iniciado), permitindo montar múltiplos posicionamentos travados.
    """
    mon = _reload(c.monitoramento)
    solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=c.setor)
    if mon.status == MonitoramentoStatus.REGISTRADO:
        mon.iniciar_monitoramento()
        mon.save()
    solicitacao = _reload(solicitacao)
    solicitacao.informar_ciencia(c.gestor_user)
    solicitacao.save()
    manifestacao = f.ManifestacaoFactory(
        monitoramento=mon, solicitacao_providencia=solicitacao, incluido_por=c.gestor_user, tipo=TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS
    )
    manifestacao.enviar(c.gestor_user)
    manifestacao.save()
    manifestacao.receber(c.auditor_user)
    manifestacao.save()

    posicionamento = f.PosicionamentoFactory(
        manifestacao=manifestacao, incluido_por=c.auditor_user, tipo=TipoPosicionamento.ATENDIMENTO, motivacao=c.motivacao
    )
    revisor = ServidorFactory()
    revisor_vinculo = revisor.get_vinculo()
    posicionamento.atribuir_revisor(revisor_vinculo)
    posicionamento.solicitar_revisao()
    posicionamento.save()
    revisao = RevisaoPosicionamento.objects.create(
        posicionamento=posicionamento, tipo=TipoPosicionamento.ATENDIMENTO, parecer=ParecerChoices.CONCORDO, comentario='ok', revisor=revisor_vinculo
    )
    return mon, posicionamento, revisao, revisor_vinculo, revisor.get_user()


class TestCancelarMonitoramentoComSolicitacaoAguardando:
    def test_cancelar_nao_quebra_com_solicitacao_aguardando(self, cenario_atendimento):
        c = cenario_atendimento
        mon = c.monitoramento

        solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=c.setor)
        mon.iniciar_monitoramento()
        mon.save()
        solicitacao = _reload(solicitacao)
        solicitacao.informar_ciencia(c.gestor_user)
        solicitacao.save()
        solicitacao.aguardar_posicionamento()
        solicitacao.save()
        assert _reload(solicitacao).status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO

        # Cancelar o monitoramento (que tenta cancelar a solicitação ativa) não pode quebrar.
        mon = _reload(mon)
        mon.cancelar(c.auditor_user)
        mon.save()

        assert _reload(mon).status == MonitoramentoStatus.CANCELADO
        assert _reload(solicitacao).status == SolicitacaoProvidenciaStatus.STATUS_CANCELADA


class TestRecomendacaoParcialParaNaoAtendida:
    def test_finalizar_ultimo_monitoramento_de_recomendacao_parcial(self, cenario_atendimento):
        c = cenario_atendimento
        rec = c.recomendacao

        # Segunda unidade -> segundo monitoramento (criado pelo signal m2m_changed).
        outra_unidade = SetorFactory()
        rec.unidades.add(outra_unidade)
        mon_a = Monitoramento.objects.get(recomendacao=rec, unidade=c.setor)
        mon_b = Monitoramento.objects.get(recomendacao=rec, unidade=outra_unidade)
        for monitoramento in (mon_a, mon_b):
            monitoramento.iniciar_monitoramento()
            monitoramento.save()

        # Conclui A -> recomendação fica PARCIALMENTE_ATENDIDA.
        mon_a = _reload(mon_a)
        mon_a.concluir(c.auditor_user)
        mon_a.save()
        assert _reload(rec).status == RecomendacaoStatus.PARCIALMENTE_ATENDIDA

        # Finaliza B (não atendido): a agregação dispara marcar_como_nao_atendida e não pode quebrar.
        mon_b = _reload(mon_b)
        mon_b.finalizar(c.auditor_user)
        mon_b.save()

        assert _reload(rec).status == RecomendacaoStatus.NAO_ATENDIDA


class TestRemoverRevisaoReabreParaNovaRevisao:
    """4.3 — Remover a revisão em andamento deve reabrir o posicionamento para nova
    revisão (REVISAO_PENDENTE) e devolver o monitoramento a AGUARDANDO_REVISAO, em vez
    de travar ambos em revisão."""

    def test_remover_revisao_reabre_e_permite_nova(self, cenario_atendimento):
        c = cenario_atendimento
        mon, posicionamento, revisao, revisor_vinculo, revisor_user = montar_em_revisao(c)
        assert _reload(posicionamento).status == PosicionamentoStatus.EM_REVISAO
        assert _reload(mon).status == MonitoramentoStatus.EM_REVISAO

        revisao.delete()

        posicionamento = _reload(posicionamento)
        assert posicionamento.status == PosicionamentoStatus.REVISAO_PENDENTE
        assert _reload(mon).status == MonitoramentoStatus.AGUARDANDO_REVISAO
        assert posicionamento.pode_revisar(revisor_user) is True

        # E uma nova revisão volta a fazer o fluxo andar.
        RevisaoPosicionamento.objects.create(
            posicionamento=posicionamento,
            tipo=TipoPosicionamento.ATENDIMENTO,
            parecer=ParecerChoices.CONCORDO,
            comentario='2',
            revisor=revisor_vinculo,
        )
        assert _reload(posicionamento).status == PosicionamentoStatus.EM_REVISAO
        assert _reload(mon).status == MonitoramentoStatus.EM_REVISAO


class TestComandoCorrigeRevisoesTravadas:
    def _criar_caso_travado_legado(self, c):
        """Dado legado: posicionamento EM_REVISAO sem revisão (remoção via queryset,
        que NÃO passa pelo delete do modelo — que já reabriria)."""
        mon, posicionamento, revisao, _, _ = montar_em_revisao(c)
        RevisaoPosicionamento.objects.filter(pk=revisao.pk).delete()
        return mon, posicionamento

    def test_dry_run_nao_altera(self, cenario_atendimento):
        mon, posicionamento = self._criar_caso_travado_legado(cenario_atendimento)
        call_command('corrigir_revisoes_travadas')
        assert _reload(posicionamento).status == PosicionamentoStatus.EM_REVISAO
        assert _reload(mon).status == MonitoramentoStatus.EM_REVISAO

    def test_apply_destrava(self, cenario_atendimento):
        mon, posicionamento = self._criar_caso_travado_legado(cenario_atendimento)
        call_command('corrigir_revisoes_travadas', '--apply')
        assert _reload(posicionamento).status == PosicionamentoStatus.REVISAO_PENDENTE
        assert _reload(mon).status == MonitoramentoStatus.AGUARDANDO_REVISAO

    def test_apply_isola_falha_por_item(self, cenario_atendimento, monkeypatch):
        """Um posicionamento que falha ao reabrir não pode abortar a correção dos demais:
        o comando reporta o erro daquele item e segue corrigindo o restante do lote."""
        _, pos_falha = self._criar_caso_travado_legado(cenario_atendimento)
        _, pos_ok = self._criar_caso_travado_legado(cenario_atendimento)

        original = Posicionamento.reabrir_revisao

        def reabrir_com_falha(self):
            if self.pk == pos_falha.pk:
                raise RuntimeError('falha simulada ao reabrir revisão')
            return original(self)

        monkeypatch.setattr(Posicionamento, 'reabrir_revisao', reabrir_com_falha)

        call_command('corrigir_revisoes_travadas', '--apply')

        # O item com falha permanece travado; o item saudável é reaberto para nova revisão.
        assert _reload(pos_falha).status == PosicionamentoStatus.EM_REVISAO
        assert _reload(pos_ok).status == PosicionamentoStatus.REVISAO_PENDENTE
