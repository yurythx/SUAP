"""Envio da manifestação registrada pela unidade auditada (issue #16415).

Só o chefe do setor envia a manifestação, e só dentro do prazo da solicitação de
providência (``Manifestacao.pode_enviar``). Quem não pode enviar via a tela da
manifestação sem o botão "Enviar manifestação" e sem nenhuma explicação; como a
manifestação REGISTRADA também bloqueia uma nova (``Monitoramento.pode_adicionar_manifestacao``),
o servidor indicado pela chefia ficava sem saber o que fazer.

Cobre a decisão registrada em #13431: a tela da manifestação registrada informa o motivo
("Somente o chefe do setor..." / "O prazo ... expirou em ...") e o alerta de
"Manifestações pendentes" do servidor indicado leva a uma página que ele pode abrir.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.urls import reverse

from auditoria.models.manifestacao import ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import MonitoramentoStatus
from auditoria.tests import factories as f
from auditoria.views.alertas import index_manifestacoes_pendentes
from djtools.utils import get_datetime_now
from rh.tests.factories import ServidorFactory

BOTAO_ENVIAR = 'Enviar manifestação'
MSG_SOMENTE_CHEFE = 'Somente o chefe do setor tem permissão para enviar essa manifestação.'


def _reload(obj):
    """Recarrega a instância do banco (ver nota em test_fluxo_http._reload)."""
    return type(obj).objects.get(pk=obj.pk)


def _iniciar_monitoramento(c, prazo):
    """Leva o monitoramento a EM_MONITORAMENTO com uma solicitação CIENTE vencendo em ``prazo``."""
    mon = _reload(c.monitoramento)
    solicitacao = f.SolicitacaoProvidenciaFactory(monitoramento=mon, setor=c.setor, prazo_atendimento=prazo)
    if mon.status == MonitoramentoStatus.REGISTRADO:
        mon.iniciar_monitoramento()
        mon.save()
    solicitacao = _reload(solicitacao)
    solicitacao.informar_ciencia(c.gestor_user)
    solicitacao.save()
    return _reload(mon), _reload(solicitacao)


@pytest.fixture
def indicado(cenario_atendimento):
    """Servidor do setor monitorado, sem chefia, indicado pelo chefe para redigir a manifestação."""
    c = cenario_atendimento
    mon, _ = _iniciar_monitoramento(c, get_datetime_now().date() + timedelta(days=15))
    servidor = ServidorFactory(setor=c.setor)
    f.IndicacaoServidorMonitoramentoFactory(monitoramento=mon, servidor=servidor.get_vinculo(), indicado_por=c.gestor_user)
    return servidor.get_user()


class TestEnvioManifestacaoPeloIndicado:
    def test_indicado_registra_e_e_informado_que_so_o_chefe_envia(self, cenario_atendimento, indicado):
        c = cenario_atendimento
        client = c.client
        client.force_login(indicado)
        client.post(
            reverse('auditoria:adicionar_manifestacao_monitoramento', kwargs={'monitoramento_id': c.monitoramento.id}),
            {'tipo': TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS.value, 'texto': 'Providências redigidas pelo indicado.'},
        )
        manifestacao = c.monitoramento.manifestacoes.order_by('-id').first()
        assert manifestacao is not None
        assert manifestacao.status == ManifestacaoStatus.REGISTRADA
        url = reverse('auditoria:visualizar_manifestacao', kwargs={'manifestacao_id': manifestacao.id})

        conteudo = client.get(url).content.decode()
        assert BOTAO_ENVIAR not in conteudo
        assert MSG_SOMENTE_CHEFE in conteudo

        client.force_login(c.gestor_user)
        conteudo = client.get(url).content.decode()
        assert BOTAO_ENVIAR in conteudo
        assert MSG_SOMENTE_CHEFE not in conteudo

    def test_alerta_de_manifestacoes_pendentes_leva_a_pagina_acessivel_ao_indicado(self, cenario_atendimento, indicado):
        c = cenario_atendimento
        mon = _reload(c.monitoramento)
        f.ManifestacaoFactory(monitoramento=mon, solicitacao_providencia=mon.ultima_solicitacao, incluido_por=indicado)
        request = RequestFactory().get('/')
        request.user = indicado

        pendencias = index_manifestacoes_pendentes(sender=None, request=request)

        assert len(pendencias) == 1
        c.client.force_login(indicado)
        resposta = c.client.get(str(pendencias[0]['url']))
        assert resposta.status_code == 200


class TestEnvioManifestacaoComPrazoVencido:
    def test_chefe_e_informado_que_o_prazo_expirou(self, cenario_atendimento):
        c = cenario_atendimento
        ontem = get_datetime_now().date() - timedelta(days=1)
        mon, solicitacao = _iniciar_monitoramento(c, ontem)
        manifestacao = f.ManifestacaoFactory(monitoramento=mon, solicitacao_providencia=solicitacao, incluido_por=c.gestor_user)
        solicitacao.expirar()
        solicitacao.save()

        c.client.force_login(c.gestor_user)
        conteudo = c.client.get(reverse('auditoria:visualizar_manifestacao', kwargs={'manifestacao_id': manifestacao.id})).content.decode()

        assert BOTAO_ENVIAR not in conteudo
        assert f'O prazo para envio dessa manifestação expirou em {ontem:%d/%m/%Y}.' in conteudo
        assert MSG_SOMENTE_CHEFE not in conteudo
