"""Issue #17124 (Erro 10564): o botão/endpoint "Solicitar Revisão" do Posicionamento
não verificava se o usuário era o auditor responsável pelo monitoramento — qualquer
usuário com a permissão genérica ``comum.is_auditor`` via visualizar e acionar a ação
em um posicionamento de outra recomendação, diferente de ``Publicar``/``Editar``/
``Adicionar Revisão``, que checam ``pode_*`` amarrado ao registro.
"""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.urls import reverse

from auditoria.models.manifestacao import ManifestacaoStatus
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.models.posicionamento import PosicionamentoStatus
from auditoria.tests import factories as f
from rh.tests.factories import ServidorFactory


def _reload(obj):
    return type(obj).objects.get(pk=obj.pk)


def _montar_posicionamento_registrado(c):
    """Monta manifestação RECEBIDA + Posicionamento REGISTRADO (sem solicitar revisão).

    Usa sempre a instância ``mon`` recarregada (nunca ``c.monitoramento``) para montar as
    factories seguintes: ``SolicitacaoProvidencia.save()`` reatribui e salva
    ``self.referencia`` (o monitoramento cacheado na FK), regravando a linha inteira — se
    essa instância fosse a original, anterior a ``iniciar_monitoramento``, o save
    sobrescreveria o status de volta para REGISTRADO no banco.
    """
    mon = _reload(c.monitoramento)
    if mon.status == MonitoramentoStatus.REGISTRADO:
        mon.iniciar_monitoramento()
        mon.save()
    solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=c.setor)
    manifestacao = f.ManifestacaoFactory(
        monitoramento=mon, solicitacao_providencia=solicitacao, incluido_por=c.gestor_user, status=ManifestacaoStatus.RECEBIDA
    )
    posicionamento = f.PosicionamentoFactory(manifestacao=manifestacao, incluido_por=c.auditor_user)
    return posicionamento


class TestAutorizacaoSolicitarRevisao:
    def test_monitor_da_recomendacao_pode_solicitar_revisao(self, cenario_atendimento):
        c = cenario_atendimento
        posicionamento = _montar_posicionamento_registrado(c)
        assert posicionamento.pode_solicitar_revisao(c.auditor_user) is True

    def test_auditor_sem_vinculo_com_a_recomendacao_nao_pode_solicitar_revisao(self, cenario_atendimento):
        c = cenario_atendimento
        posicionamento = _montar_posicionamento_registrado(c)

        outro_auditor_user = ServidorFactory().get_user()
        outro_auditor_user.groups.add(Group.objects.get(name='Auditor'))

        assert posicionamento.pode_solicitar_revisao(outro_auditor_user) is False

    def test_view_nega_solicitacao_de_revisao_por_auditor_sem_vinculo(self, cenario_atendimento):
        c = cenario_atendimento
        posicionamento = _montar_posicionamento_registrado(c)

        outro_auditor_user = ServidorFactory().get_user()
        outro_auditor_user.groups.add(Group.objects.get(name='Auditor'))

        client = c.client
        client.force_login(outro_auditor_user)
        resp = client.post(
            reverse('auditoria:solicitar_revisao_posicionamento', kwargs={'posicionamento_id': posicionamento.id}),
            {
                'posicionamento': posicionamento.id,
                'manifestacao': posicionamento.manifestacao.id,
                'revisor': c.auditor_vinculo.id,
            },
        )
        assert resp.status_code in (200, 302)
        # Payload de formulário válido: se a view não barrar pela autorização, o
        # posicionamento avançaria para REVISAO_PENDENTE mesmo vindo de um auditor
        # sem vínculo com esta recomendação.
        assert _reload(posicionamento).status == PosicionamentoStatus.REGISTRADO
