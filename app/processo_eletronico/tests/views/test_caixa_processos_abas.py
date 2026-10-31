"""Conteúdo das abas e das contagens da caixa de processos (#17797).

Teste de caracterização: fixa, por ids, o que cada aba da ``caixa_processos`` devolve num cenário
com trâmites em várias situações, para que a reescrita das consultas (``EXISTS`` no lugar de
``IN (SELECT DISTINCT ...)`` e ``NOT IN``) não mude o resultado.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from comum.models import Vinculo
from documento_eletronico.status import SolicitacaoStatus
from processo_eletronico import views
from processo_eletronico.models import Processo, Tramite
from processo_eletronico.status import ProcessoStatus
from processo_eletronico.tests.factories import (
    ApensamentoFactory,
    ApensamentoProcessoFactory,
    CompartilhamentoPoderChefeFactory,
    ProcessoFactory,
    SolicitacaoCienciaFactory,
    SolicitacaoDespachoFactory,
    TramiteFactory,
)
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

ABAS_DE_TRAMITE = ('cx_entrada_nao_recebidos', 'cx_entrada_recebidos', 'cx_com_ciencia_a_encaminhar', 'cx_sigilosos', 'cx_saida')


def _tramitar(processo: Processo, origem: SimpleNamespace, recebido_por: Vinculo | None = None, **destino: object) -> Tramite:
    return TramiteFactory(
        processo=processo,
        remetente_setor=origem.setor,
        remetente_vinculo=origem.vinculo,
        data_hora_recebimento=timezone.now() if recebido_por else None,
        recebido_por=recebido_por,
        **destino,
    )


@pytest.fixture
def cenario(db: None, sync_permissions: None, setor_com_siorg: Setor) -> SimpleNamespace:
    cache.clear()
    setor, outro_setor = setor_com_siorg, SetorFactory()
    eu = ServidorFactory(setor=setor)
    outro = ServidorFactory(setor=outro_setor)
    v_eu, v_outro = eu.get_vinculo(), outro.get_vinculo()
    CompartilhamentoPoderChefeFactory(setor_dono=setor, vinculo_permitido=v_eu)
    de_fora = SimpleNamespace(setor=outro_setor, vinculo=v_outro)
    daqui = SimpleNamespace(setor=setor, vinculo=v_eu)

    def processo(**kwargs: object) -> Processo:
        p = ProcessoFactory(setor_criacao=setor, usuario_gerador=eu.get_user(), **kwargs)
        p.interessados.add(v_outro)  # o post_save do NUP 17 exige um interessado
        return p

    def chega(recebido: bool = True, **kwargs: object) -> tuple[Processo, Tramite]:
        p = processo(**kwargs)
        return p, _tramitar(p, de_fora, recebido_por=v_eu if recebido else None, destinatario_setor=setor)

    t = SimpleNamespace()
    _, t.a_receber = chega(recebido=False)
    _, t.a_encaminhar = chega()
    p_despacho, t.despacho_pendente = chega()
    desp_pendente = SolicitacaoDespachoFactory(processo=p_despacho, remetente_setor=setor, remetente_vinculo=v_eu, solicitado=v_outro)
    p_deferido, t.despacho_deferido = chega()
    SolicitacaoDespachoFactory(
        processo=p_deferido, remetente_setor=setor, remetente_vinculo=v_eu, solicitado=v_outro, status=SolicitacaoStatus.STATUS_DEFERIDA
    )
    p_ciencia, t.ciencia = chega()
    SolicitacaoCienciaFactory(processo=p_ciencia, tramite=t.ciencia, solicitado=v_outro)
    p_duas, t.duas_ciencias = chega()
    for _ in range(2):
        SolicitacaoCienciaFactory(processo=p_duas, tramite=t.duas_ciencias, solicitado=v_outro)
    p_ap1, t.apensado_1 = chega(assunto='Processo zebrafiltro apensado')
    p_ap1.interessados.add(v_eu)
    p_ap2, t.apensado_2 = chega()
    apensamento = ApensamentoFactory()
    ApensamentoProcessoFactory(apensamento=apensamento, processo=p_ap1)
    ApensamentoProcessoFactory(apensamento=apensamento, processo=p_ap2)
    t.sigiloso = _tramitar(processo(nivel_acesso=Processo.NIVEL_ACESSO_PRIVADO), de_fora, destinatario_vinculo=v_eu)
    chega(status=ProcessoStatus.STATUS_FINALIZADO)

    # Fora da caixa: trâmite de outro setor com despacho pedido a mim, e trâmite que não é o último do processo.
    p_fora = processo()
    _tramitar(p_fora, daqui, recebido_por=v_outro, destinatario_setor=outro_setor)
    desp_para_mim = SolicitacaoDespachoFactory(processo=p_fora, remetente_setor=outro_setor, remetente_vinculo=v_outro, solicitado=v_eu)
    p_antigo, _ = chega()
    t.saida = _tramitar(p_antigo, daqui, destinatario_setor=outro_setor)

    p_sem_tramite = processo()
    p_aguardando_ciencia, _ = chega(status=ProcessoStatus.STATUS_AGUARDANDO_CIENCIA)
    return SimpleNamespace(
        user=eu.get_user(),
        t=t,
        despachos=sorted([desp_pendente.pk, desp_para_mim.pk]),
        sem_tramitacao=[p_sem_tramite.pk],
        aguardando_ciencia=[p_aguardando_ciencia.pk],
    )


def _abas(client: Client, user: object, **params: str) -> dict:
    client.force_login(user)
    resposta = client.get('/processo_eletronico/caixa_processos/', params)
    assert resposta.status_code == 200
    ctx = resposta.context
    abas = {nome: sorted(obj.pk for obj in ctx[nome]) for nome in (*ABAS_DE_TRAMITE, 'cx_esperando_despachos')}
    abas |= {nome: sorted(obj.pk for obj in ctx[nome]) for nome in ('cx_entrada_sem_tramitacao', 'cx_esperando_ciencia')}
    for nome, ids in abas.items():
        assert ctx[f'{nome}_length'] == len(ids), nome
    return abas


def test_abas_e_contagens_da_caixa(client: Client, cenario: SimpleNamespace) -> None:
    t = cenario.t
    recebidos = [t.a_encaminhar, t.despacho_deferido, t.ciencia, t.duas_ciencias, t.apensado_1, t.apensado_2]
    assert _abas(client, cenario.user) == {
        'cx_entrada_nao_recebidos': [t.a_receber.pk],
        'cx_entrada_recebidos': sorted(x.pk for x in recebidos),
        # O trâmite com duas ciências aparece uma vez só (#17812).
        'cx_com_ciencia_a_encaminhar': sorted([t.ciencia.pk, t.duas_ciencias.pk]),
        'cx_sigilosos': [t.sigiloso.pk],
        'cx_saida': [t.saida.pk],
        'cx_esperando_despachos': cenario.despachos,
        'cx_entrada_sem_tramitacao': cenario.sem_tramitacao,
        'cx_esperando_ciencia': cenario.aguardando_ciencia,
    }


def test_pendencia_de_ciencia_da_pagina_inicial_conta_cada_tramite_uma_vez(cenario: SimpleNamespace) -> None:
    """O trâmite com duas ciências conta 1 na pendência "Solicitações de Ciência Finalizadas a encaminhar" (#17812)."""
    pendencias = views.index_atribuidos_a_meus_grupos(sender=None, request=SimpleNamespace(user=cenario.user))
    ciencia = [p for p in pendencias if p['url'] == '/processo_eletronico/caixa_processos/?tab=com-ciencia-finalizada']
    assert [p['qtd'] for p in ciencia] == [len({cenario.t.ciencia.pk, cenario.t.duas_ciencias.pk})]


def test_pesquisa_por_interessados_nao_repete_tramite(client: Client, cenario: SimpleNamespace) -> None:
    """A pesquisa junta os interessados (to-many): o processo com dois interessados aparece uma vez só."""
    abas = _abas(client, cenario.user, pesquisa='zebrafiltro')
    assert abas['cx_entrada_recebidos'] == [cenario.t.apensado_1.pk]
    assert abas['cx_entrada_nao_recebidos'] == []


def test_sem_aba_na_url_abre_a_primeira_aba_com_processos(client: Client, db: None, sync_permissions: None, setor_com_siorg: Setor) -> None:
    """Só há processo aguardando ciência: a caixa abre nessa aba, que existe na página."""
    cache.clear()
    eu, de_fora = ServidorFactory(setor=setor_com_siorg), ServidorFactory(setor=SetorFactory())
    CompartilhamentoPoderChefeFactory(setor_dono=setor_com_siorg, vinculo_permitido=eu.get_vinculo())
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=eu.get_user(), status=ProcessoStatus.STATUS_AGUARDANDO_CIENCIA)
    processo.interessados.add(de_fora.get_vinculo())
    origem = SimpleNamespace(setor=de_fora.setor, vinculo=de_fora.get_vinculo())
    _tramitar(processo, origem, recebido_por=eu.get_vinculo(), destinatario_setor=setor_com_siorg)

    client.force_login(eu.get_user())
    resposta = client.get('/processo_eletronico/caixa_processos/')
    assert resposta.context['tab'] == 'aguardando-ciencia'
    assert f'data-tab="{resposta.context["tab"]}"' in resposta.content.decode()
