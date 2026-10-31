"""Banca: o avaliador aceita ou recusa o convite, avalia os comprovantes e finaliza ou desiste.

O aceite exige telefone e dados bancários do avaliador (o seed os dá); a recusa promove o reserva. Na
avaliação, cada item abre num popup que grava por AJAX, e a finalização confere que todo item foi validado:
os comprovantes somam menos de 25 pontos, então a avaliação fecha indeferida.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROCESSOS = '/rsc/processo_avaliacao/'
TERMO = '/rsc/termo_aceite/{}/'
ACEITAR = '/rsc/aceitar_rejeitar_processo/{}/'
RECUSAR = '/rsc/recusar_avaliacao/{}/'
AVALIAR = '/rsc/avaliar_processo/{}/{}/'
AVALIAR_ITEM = '/rsc/avaliar_item/{}/'
SALVAR_ITEM = '/rsc/salvar_avaliacao/{}/'
FINALIZAR = '/rsc/finalizar_avaliacao/{}/'
DESISTIR = '/rsc/desistir_avaliacao/{}/'
QUADRO_RESUMO = '/rsc/quadro_resumo_avaliacao/{}/'


def test_avaliador_aceita_o_convite(
    logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]
) -> None:
    from rsc.models import ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR)
    convite, _ = banca(processo, status=ProcessoAvaliador.AGUARDANDO_ACEITE)
    pagina = logado_rsc('avaliador')
    tela = Tela(pagina).ir(PROCESSOS)
    tela.loc(f'//a[@href="{TERMO.format(convite.pk)}"]').click()
    popup = tela.popup()
    popup.loc('//input[@id="li_aceito_termo"]').check()
    with pagina.expect_response(lambda r: ACEITAR.format(convite.pk) in r.url):
        popup.loc('//input[@value="Aceitar Avaliação"]').click()

    convite.refresh_from_db()
    processo.refresh_from_db()
    assert (convite.status, processo.status) == (ProcessoAvaliador.EM_AVALIACAO, ProcessoRSC.STATUS_EM_AVALIACAO)


def test_avaliador_recusa_e_o_reserva_assume(
    logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]
) -> None:
    from rsc.models import ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR)
    convite, _ = banca(processo, status=ProcessoAvaliador.AGUARDANDO_ACEITE)
    reserva, _ = banca(processo, papel='reserva', status=ProcessoAvaliador.EM_ESPERA)
    tela = Tela(logado_rsc('avaliador')).ir(PROCESSOS)
    tela.loc(f'//a[@href="{RECUSAR.format(convite.pk)}"]').click()
    popup = tela.popup()
    popup.preencher('Motivo da Recusa', 'textarea', 'Conflito de interesse.')
    popup.salvar_no_popup('Enviar').sucesso('Processo recusado com sucesso.')

    convite.refresh_from_db()
    reserva.refresh_from_db()
    assert (convite.status, convite.motivo_recusa) == (ProcessoAvaliador.REJEITADO_PELO_AVALIADOR, 'Conflito de interesse.')
    assert reserva.status == ProcessoAvaliador.AGUARDANDO_ACEITE, 'a recusa não promoveu o avaliador reserva'


def test_avaliador_avalia_e_finaliza(
    logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]
) -> None:
    from rsc.models import Avaliacao, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_EM_AVALIACAO)
    convite, avaliacao = banca(processo)
    item, *demais = avaliacao.avaliacaoitem_set.order_by('pk')
    for outro in demais:
        outro.qtd_itens_validado = outro.arquivo.qtd_itens
        outro.data_referencia = outro.arquivo.data_referencia
        outro.save()
    pagina = logado_rsc('avaliador')
    tela = Tela(pagina)
    with pagina.expect_response(lambda r: QUADRO_RESUMO.format(avaliacao.pk) in r.url):
        tela.ir(AVALIAR.format(processo.pk, convite.avaliador_id))
    tela.ver_titulo(f'Avaliar Processo {processo}')

    tela.clicar_aba('Avaliação')
    tela.loc(f'//a[@href="{AVALIAR_ITEM.format(item.pk).rstrip("/")}"]').first.click()
    popup = tela.popup()
    # A justificativa antes: alterar a quantidade dispara o autossalvamento, que a recusa sem justificativa.
    popup.loc(f'//textarea[@name="justificativa_avaliacao_{item.pk}"]').fill('Comprovante não corresponde ao critério.')
    popup.loc(f'//input[@name="qtd_itens_validado_{item.pk}"]').fill('0')
    with pagina.expect_request(lambda r: SALVAR_ITEM.format(item.pk) in r.url):
        popup.loc('//input[@value="Salvar"]').click()
    # O popup só fecha no sucesso do POST do "Salvar" (`salvar_avaliacao`), o último dos autossalvamentos.
    expect(pagina.locator('iframe.fancybox-iframe')).to_have_count(0)
    item.refresh_from_db()
    assert (item.qtd_itens_validado, item.justificativa) == (0, 'Comprovante não corresponde ao critério.')

    tela.ir(AVALIAR.format(processo.pk, convite.avaliador_id))
    with pagina.expect_navigation(url=f'**{PROCESSOS}'), pagina.expect_response(lambda r: FINALIZAR.format(avaliacao.pk) in r.url):
        tela.clicar_link('Finalizar Avaliação')
    avaliacao.refresh_from_db()
    assert avaliacao.status == Avaliacao.INDEFERIDA


def test_avaliador_desiste(logado_rsc: Callable[[str], Page], processo_rsc: Callable[..., Any], banca: Callable[..., tuple[Any, Any]]) -> None:
    from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_EM_AVALIACAO)
    convite, avaliacao = banca(processo)
    pagina = logado_rsc('avaliador')
    tela = Tela(pagina).ir(AVALIAR.format(processo.pk, convite.avaliador_id))
    tela.loc(f'//a[@href="{DESISTIR.format(avaliacao.pk).rstrip("/")}"]').click()
    popup = tela.popup()
    popup.loc('//textarea[@id="id_justificativa"]').fill('Indisponibilidade de agenda.')
    with pagina.expect_response(lambda r: DESISTIR.format(avaliacao.pk) in r.url and r.request.method == 'POST') as desistencia:
        popup.loc('//a[contains(., "Desistir da Avaliação")]').click()
    assert desistencia.value.json()['ok'], desistencia.value.text()

    avaliacao.refresh_from_db()
    convite.refresh_from_db()
    assert (avaliacao.status, avaliacao.motivo_desistencia) == (Avaliacao.DESISTENCIA, 'Indisponibilidade de agenda.')
    assert convite.status == ProcessoAvaliador.REJEITADO_PELO_AVALIADOR
