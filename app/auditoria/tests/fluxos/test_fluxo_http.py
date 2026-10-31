"""Caminho feliz do fluxo de monitoramento via HTTP (cliente de teste).

Percorre, em sequência e com troca de usuário (auditor x gestor), os endpoints
clássicos do app até o posicionamento de *Atendimento* concluir o monitoramento:

1. Auditor inicia o monitoramento da unidade (cria a solicitação de providência).
2. Gestor toma ciência (ao acessar o monitoramento).
3. Gestor adiciona uma manifestação de encaminhamento de providências.
4. Gestor envia a manifestação (solicitação passa a aguardar posicionamento).
5. Auditor recebe a manifestação.
6. Auditor registra um posicionamento de Atendimento.
7. Auditor publica o posicionamento -> monitoramento CONCLUÍDO.
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse

from auditoria.models.manifestacao import ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.models.posicionamento import TipoPosicionamento
from auditoria.models.providencia import SolicitacaoProvidenciaStatus
from djtools.utils import get_datetime_now


def _data(d):
    return d.strftime('%d/%m/%Y')


def _reload(obj):
    """Recarrega a instância do banco.

    Não usamos ``refresh_from_db`` porque os modelos têm ``FSMField`` protegido,
    cujo ``__set__`` proíbe atribuição direta de status (o que ``refresh_from_db``
    faz). Recriar a instância via ``get`` passa pelo caminho ``from_db``, permitido.
    """
    return type(obj).objects.get(pk=obj.pk)


class TestFluxoMonitoramentoAtendimento:
    def test_caminho_feliz_ate_atendimento(self, cenario_atendimento):
        c = cenario_atendimento
        client = c.client
        prazo = get_datetime_now().date() + timedelta(days=15)

        # 1. Auditor inicia o monitoramento da unidade.
        client.force_login(c.auditor_user)
        resp = client.post(
            reverse('auditoria:monitorar_recomendacao', kwargs={'recomendacao_id': c.recomendacao.id}),
            {
                'recomendacao': c.recomendacao.id,
                'unidades': [c.setor.id],
                'motivacao': 'Favor adotar as providências recomendadas.',
                'prazo': _data(prazo),
            },
        )
        assert resp.status_code in (200, 302)
        monitoramento = _reload(c.monitoramento)
        assert monitoramento.status == MonitoramentoStatus.EM_MONITORAMENTO
        solicitacao = monitoramento.ultima_solicitacao
        assert solicitacao is not None
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_ESPERANDO

        # 2. Gestor toma ciência ao acessar o monitoramento.
        client.force_login(c.gestor_user)
        client.get(reverse('auditoria:visualizar_monitoramento', kwargs={'monitoramento_id': c.monitoramento.id}))
        solicitacao = _reload(solicitacao)
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_CIENTE

        # 3. Gestor adiciona uma manifestação.
        resp = client.post(
            reverse('auditoria:adicionar_manifestacao_monitoramento', kwargs={'monitoramento_id': c.monitoramento.id}),
            {
                'tipo': TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS.value,
                'texto': 'Providências adotadas conforme recomendado.',
            },
        )
        assert resp.status_code in (200, 302)
        manifestacao = monitoramento.manifestacoes.order_by('-id').first()
        assert manifestacao is not None
        assert manifestacao.status == ManifestacaoStatus.REGISTRADA

        # 4. Gestor envia a manifestação.
        resp = client.post(reverse('auditoria:entregar_manifestacao', kwargs={'manifestacao_id': manifestacao.id}))
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.ENVIADA
        solicitacao = _reload(solicitacao)
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_AGUARDANDO_POSICIONAMENTO

        # 5. Auditor recebe a manifestação.
        client.force_login(c.auditor_user)
        resp = client.post(reverse('auditoria:receber_manifestacao', kwargs={'manifestacao_id': manifestacao.id}))
        assert resp.status_code in (200, 302)
        manifestacao = _reload(manifestacao)
        assert manifestacao.status == ManifestacaoStatus.RECEBIDA

        # 6. Auditor registra o posicionamento de Atendimento.
        resp = client.post(
            reverse('auditoria:adicionar_posicionamento', kwargs={'manifestacao_id': manifestacao.id}),
            {
                'manifestacao': manifestacao.id,
                'tipo': TipoPosicionamento.ATENDIMENTO.value,
                'motivacao': c.motivacao.id,
                'outros': '',
                'parecer': 'Parecer favorável: providências atendidas.',
            },
        )
        assert resp.status_code in (200, 302)
        posicionamento = manifestacao.posicionamentos.order_by('-id').first()
        assert posicionamento is not None

        # 7. Auditor publica o posicionamento -> conclui o monitoramento.
        resp = client.post(reverse('auditoria:publicar_posicionamento', kwargs={'posicionamento_id': posicionamento.id}))
        assert resp.status_code in (200, 302)

        # Estado final do fluxo.
        monitoramento = _reload(monitoramento)
        manifestacao = _reload(manifestacao)
        solicitacao = _reload(solicitacao)
        assert monitoramento.status == MonitoramentoStatus.CONCLUIDO
        assert monitoramento.concluido is True
        assert manifestacao.status == ManifestacaoStatus.ANALISADA
        assert solicitacao.status == SolicitacaoProvidenciaStatus.STATUS_FINALIZAR
