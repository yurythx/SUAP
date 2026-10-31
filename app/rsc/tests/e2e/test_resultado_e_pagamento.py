"""Depois da banca: o docente dá ciência do resultado, a CPPD encerra o processo de aposentado e paga a banca.

A ciência é um formulário de duas perguntas gravado por AJAX na tela de acompanhamento. O pagamento parte do
relatório filtrado por período: o botão marca como pagas as avaliações listadas, numa aba nova, e volta.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ACOMPANHAR = '/rsc/acompanhar_avaliacao/{}/'
CIENCIA = '/rsc/ciencia_resultado/{}/'
DEFERIR_APOSENTADO = '/rsc/deferir_processo_aposentado/{}/'
RELATORIO_PAGAMENTO = '/rsc/relatorio_pagamento/'
RELATORIO_PAGAMENTO_PDF = '/rsc/relatorio_pagamento_pdf/'
PAGAR = RELATORIO_PAGAMENTO_PDF + '?pagar=1'
RELATORIO_PROCESSOS = RELATORIO_PAGAMENTO_PDF + '?relatorio=processo'


def test_docente_da_ciencia_do_resultado(logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any]) -> None:
    from rsc.models import ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_CIENCIA)
    pagina = logado_rsc('docente')
    Tela(pagina).ir(ACOMPANHAR.format(processo.pk))
    pagina.locator('input[name="ciencia_deferimento"][value="1"]').check()
    pagina.locator('input[name="ciencia_data_retroatividade"][value="2"]').check()
    with pagina.expect_response(lambda r: CIENCIA.format(processo.pk) in r.url):
        pagina.locator('a', has_text='Registrar Ciência do Resultado').click()

    processo.refresh_from_db()
    assert (processo.status, processo.concorda_deferimento, processo.concorda_data_retroatividade) == (
        ProcessoRSC.STATUS_CIENTE_DO_RESULTADO,
        ProcessoRSC.CONCORDA_DEFERIMENTO,
        ProcessoRSC.DISCORDA_DATA_RETROATIVIDADE,
    )


def test_cppd_defere_processo_de_aposentado(logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any]) -> None:
    """Sem avaliação indeferida, a maioria é de deferimento: o processo fecha deferido e marcado como de aposentado."""
    from rsc.models import ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_CIENTE_DO_RESULTADO)
    Tela(logado_rsc('membro')).ir(DEFERIR_APOSENTADO.format(processo.pk)).sucesso('Processo deferido com sucesso.')
    processo.refresh_from_db()
    assert (processo.status, processo.tipo_processo) == (ProcessoRSC.STATUS_APROVADO, ProcessoRSC.TIPO_PROCESSO_APOSENTADO)


def test_cppd_paga_a_banca(logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]) -> None:
    from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_APROVADO)
    processo.data_finalizacao_processo = date.today()
    processo.save()
    _, avaliacao = banca(processo, status=ProcessoAvaliador.AVALIACAO_FINALIZADA)
    Avaliacao.objects.filter(pk=avaliacao.pk).update(status=Avaliacao.DEFERIDA, data_finalizacao=date.today())
    # O relatório lista uma avaliação por avaliador e interessado (`distinct` pelo nome do docente): pendências de
    # outros processos do mesmo docente, deixadas por rodadas anteriores, esconderiam esta.
    Avaliacao.objects.filter(processo__servidor=processo.servidor, avaliacao_paga=False).exclude(pk=avaliacao.pk).update(avaliacao_paga=True)

    pagina = logado_rsc('membro')
    hoje = date.today().strftime('%d/%m/%Y')
    tela = Tela(pagina).ir(RELATORIO_PAGAMENTO)
    tela.preencher_formulario([('Data de Incício', 'data', hoje), ('Data Final', 'data', hoje)])
    tela.clicar_botao('Filtrar')
    tela.ver_texto(processo.servidor.nome)

    tela.clicar_botao('Relatórios')
    with pagina.context.expect_page() as relatorio:
        pagina.locator(f'a[onclick*="{RELATORIO_PROCESSOS}"]').click()
    relatorio.value.wait_for_url(f'**{RELATORIO_PROCESSOS}')
    assert 'Docente RSC Avaliado' in relatorio.value.content()

    with pagina.context.expect_page() as pagamento:
        pagina.locator(f'a[onclick*="{PAGAR}"]').click()
    # O POST volta (httprr) ao relatório: esperar a URL dele, não o `load` do about:blank da aba recém-aberta.
    pagamento.value.wait_for_url(f'**{RELATORIO_PAGAMENTO}**')
    assert Avaliacao.objects.filter(pk=avaliacao.pk, avaliacao_paga=True).exists(), f'{PAGAR} não marcou a avaliação como paga'
