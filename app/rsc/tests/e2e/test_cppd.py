"""CPPD: valida os documentos preliminares, rejeita, monta a banca e acompanha os prazos dos avaliadores.

A validação é a tela de seleções e rádios que liberam o botão "Aceitar" e gravam por AJAX; o teste a preenche
como o membro da CPPD faz e confere a ``ValidacaoCPPD`` e a nova situação do processo. A banca é escolhida
pelo autocomplete de docentes: o primeiro interno nasce convidado, e o processo passa a aguardar o aceite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VALIDAR = '/rsc/validar_processorsc/{}/'
REJEITAR = '/rsc/rejeitar_processo_cppd/{}/'
SELECIONAR = '/rsc/selecionar_avaliadores/{}/'
ACOMPANHAR = '/rsc/acompanhar_avaliacao/{}/'
REENVIAR = '/rsc/reenviar_email_avaliador/{}/'
SEM_RESERVA = '/rsc/processos_sem_avaliador_reserva/'
REVISAR_PRAZOS = '/rsc/revisar_datas_limite/'


def test_cppd_valida_e_aceita(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    from rsc.models import ProcessoRSC, ValidacaoCPPD

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD)
    pagina = logado_rsc('membro')
    Tela(pagina).ir(VALIDAR.format(processo.pk))
    for nome in ('processo_titulacao', 'processo_exercicio_ebtt', 'processo_ultima_rt'):
        pagina.locator(f'select[name="{nome}"]').select_option('1')
    pagina.locator('#formulario_pontuacao1').check()
    pagina.locator('#relatorio_descritivo1').check()
    with pagina.expect_navigation(url='**/admin/rsc/processorsc/**'):
        pagina.locator('#btn_aceitar').click()

    processo.refresh_from_db()
    assert processo.status == ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES
    assert ValidacaoCPPD.objects.filter(processo=processo, acao=ValidacaoCPPD.ACAO_ACEITAR, validador=rsc_seed['membro']).exists()


def test_cppd_rejeita(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    from rsc.models import ProcessoRSC, ValidacaoCPPD

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD)
    tela = Tela(logado_rsc('membro')).ir(REJEITAR.format(processo.pk))
    tela.preencher('Motivo da Recusa', 'textarea', 'Documentação incompleta.')
    tela.clicar_botao('Enviar')
    tela.sucesso('Processo rejeitado com sucesso.')
    processo.refresh_from_db()
    assert processo.status == ProcessoRSC.STATUS_REJEITADO
    assert ValidacaoCPPD.objects.filter(processo=processo, acao=ValidacaoCPPD.ACAO_REJEITAR, motivo_rejeicao='Documentação incompleta.').exists()


def test_cppd_monta_a_banca_e_acompanha(logado_rsc: Callable[[str], Page], rsc_seed: dict, processo_rsc: Callable[..., Any]) -> None:
    """Só um interno e nenhum externo: o processo entra na lista dos que estão sem avaliador reserva."""
    from rsc.models import ProcessoAvaliador, ProcessoRSC

    processo = processo_rsc(ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES)
    avaliadora = rsc_seed['avaliador']
    tela = Tela(logado_rsc('membro')).ir(SELECIONAR.format(processo.pk))
    tela.preencher('Avaliador interno', 'autocomplete multiplo', avaliadora.matricula)
    tela.clicar_botao('Enviar')
    tela.sucesso('Avaliadores selecionados com sucesso.')
    processo.refresh_from_db()
    convite = ProcessoAvaliador.objects.get(processo=processo, avaliador__vinculo=avaliadora.get_vinculo())
    assert (processo.status, convite.status) == (ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoAvaliador.AGUARDANDO_ACEITE)

    tela.ir(ACOMPANHAR.format(processo.pk)).ver_texto(avaliadora.nome)
    tela.ir(SEM_RESERVA).ver_texto(processo.servidor.nome)
    tela.ir(REENVIAR.format(convite.pk)).sucesso('E-mail reenviado com sucesso para')
    tela.ir(REVISAR_PRAZOS).sucesso('Avaliadores atualizados.')
    convite.refresh_from_db()
    assert convite.status == ProcessoAvaliador.AGUARDANDO_ACEITE, 'convite de hoje não pode vencer na revisão de prazos'
