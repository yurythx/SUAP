# ruff: noqa: UP032
"""Agenda de saúde e alteração de jornada: persistência dos horários e decisão do RH por UI.

Estado novo por teste impede vagas e processos consumidos entre rodadas com --reuse-db.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela
from rh.tests.factories import AcaoSaudeFactory, CargaHorariaReduzidaFactory, HorarioSemanalFactory

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_agenda_saude(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('saude'))
    from rh.models import AgendaAtendimentoHorario, HorarioAgendado

    acao = AcaoSaudeFactory()
    gestor = rh_seed['saude']
    dia = date.today() + timedelta(days=1)
    tela.ir('/rh/adicionar_horario/{}/'.format(acao.pk))
    tela.preencher_formulario(
        [
            ('Profissional', 'autocomplete', gestor.matricula),
            ('Início do Atendimento', 'hora', '08:00'),
            ('Fim do Atendimento', 'hora', '09:00'),
            ('Quantidade de Vagas', 'número', '1'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Horário cadastrado com sucesso.')
    assert AgendaAtendimentoHorario.objects.filter(acao_saude=acao, profissional=gestor, quantidade_vaga=1).exists()
    horario = AgendaAtendimentoHorario.objects.get(acao_saude=acao)
    tela.ir('/rh/agendar_horario/{}/'.format(horario.pk))
    tela.preencher('Solicitante', 'autocomplete', gestor.matricula)
    tela.preencher('Data da Consulta', 'data', dia.strftime('%d/%m/%Y'))
    tela.clicar_botao('Salvar')
    tela.sucesso('Agendamento cadastrado com sucesso.')
    assert HorarioAgendado.objects.filter(horario=horario, solicitante=gestor.get_vinculo(), data_consulta=dia, cancelado=False).exists()
    agendamento = HorarioAgendado.objects.get(horario=horario)
    tela.ir('/rh/acao_saude/{}/'.format(acao.pk)).ver_titulo('Visualizar Ação de Saúde')
    tela.clicar_aba('Agendados')
    url_cancelar = '/rh/cancelar_agendamento/{}/'.format(agendamento.pk)
    assert tela.loc(f'//a[@href="{url_cancelar}"]').count() == 1
    tela.clicar_link('Cancelar')
    tela.sucesso('Agendamento cancelado com sucesso.')
    assert HorarioAgendado.objects.filter(pk=agendamento.pk, cancelado=True, data_cancelamento__isnull=False).exists()


def test_horario_excepcional_e_indeferimento(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import CargaHorariaReduzida, HorarioSemanal

    processo = CargaHorariaReduzidaFactory(servidor=rh_seed['servidor'])
    tela.ir('/rh/abrir_processo_afastamento_parcial/{}/'.format(processo.pk)).ver_titulo('Processo de Alteração de Carga Horária')
    tela.ir('/rh/adicionar_horario_afastamento_parcial/{}/'.format(processo.pk))
    tela.preencher_formulario(
        [
            ('Data inicial', 'data', processo.data_inicio.strftime('%d/%m/%Y')),
            ('Data final', 'data', processo.data_termino.strftime('%d/%m/%Y')),
            ('Jornada pretendida', 'lista', '30:00 SEMANAL'),
        ]
    )
    for dia in ('SEG', 'TER', 'QUA', 'QUI', 'SEX'):
        tela.preencher(dia, 'lista', '6:00 SEMANAL')
    tela.clicar_botao('Salvar')
    tela.sucesso('Horário salvo com sucesso.')
    assert HorarioSemanal.objects.filter(processo_reducao_ch=processo, jornada_semanal='30.0', seg=6).exists()
    horario = HorarioSemanal.objects.get(processo_reducao_ch=processo)
    tela.ir('/rh/editar_horario_afastamento/{}/'.format(horario.pk))
    tela.clicar_botao('Salvar')
    tela.sucesso('Horário atualizado com sucesso.')
    assert HorarioSemanal.objects.filter(pk=horario.pk, jornada_semanal='30.0', seg=6).exists()
    tela.ir('/rh/abrir_processo_afastamento_parcial/{}/'.format(processo.pk))
    tela.preencher('Motivo do Indeferimento', 'textarea', 'Documentação incompatível com a jornada solicitada.')
    tela.clicar_botao('Indeferir')
    tela.sucesso('Carga horária excepcional indeferida com sucesso.')
    assert CargaHorariaReduzida.objects.filter(
        pk=processo.pk, status=CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH, servidor_rh_validador=rh_seed['sistemico']
    ).exists()


def test_rh_defere_e_indefere_afastamento_parcial(logado_rh: Callable[[str], Page], rh_seed: dict) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import CargaHorariaReduzida

    def _afastamento(inicio: date) -> CargaHorariaReduzida:
        return HorarioSemanalFactory(
            processo_reducao_ch__servidor=rh_seed['servidor'],
            processo_reducao_ch__tipo=CargaHorariaReduzida.TIPO_AFASTAMENTO_PARCIAL,
            processo_reducao_ch__status=CargaHorariaReduzida.STATUS_AGUARDANDO_VALIDACAO_RH,
            processo_reducao_ch__data_inicio=inicio,
            processo_reducao_ch__data_termino=inicio + timedelta(days=29),
        ).processo_reducao_ch

    # Períodos consecutivos: o mesmo servidor não tem duas reduções simultâneas.
    deferido = _afastamento(date.today() + timedelta(days=1))
    indeferido = _afastamento(date.today() + timedelta(days=31))
    situacao = '/rh/alterar_situacao_afastamento_parcial_rh/{}/{}/'
    tela.ir('/rh/abrir_processo_afastamento_parcial/{}/'.format(deferido.pk))
    tela.clicar_botao('Atualizar Situação')
    tela.loc('//a[@href="{}"]'.format(situacao.format(deferido.pk, 'deferir'))).click()
    tela.sucesso('Processo de alteração de carga horária deferido com sucesso.')
    assert CargaHorariaReduzida.objects.filter(
        pk=deferido.pk, status=CargaHorariaReduzida.STATUS_DEFERIDO_PELO_RH, servidor_rh_validador=rh_seed['sistemico']
    ).exists()

    tela.ir('/rh/abrir_processo_afastamento_parcial/{}/'.format(indeferido.pk))
    tela.clicar_botao('Atualizar Situação')
    tela.loc('//a[@href="{}"]'.format(situacao.format(indeferido.pk, 'indeferir'))).click()
    popup = tela.popup()
    popup.preencher('Motivo do Indeferimento', 'textarea', 'Horário incompatível com o setor.')
    popup.salvar_no_popup('Salvar').sucesso('Processo de alteração de carga horária indeferido com sucesso.')
    assert CargaHorariaReduzida.objects.filter(
        pk=indeferido.pk, status=CargaHorariaReduzida.STATUS_INDEFERIDO_PELO_RH, motivo_indeferimento_rh='Horário incompatível com o setor.'
    ).exists()
