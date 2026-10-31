"""Fluxo da agenda de atendimentos: geração de horários, reserva, bloqueio e cancelamento.

A agenda é a porta de entrada do paciente no Saúde: o profissional publica horários, o aluno
reserva pelo próprio login, o profissional bloqueia quem falta e cancela com justificativa —
individualmente ou em lote. O calendário é a visão consolidada do mesmo período. A regra de
12 horas (`dentro_prazo_agendamento`) é o que mantém a agenda coerente com o relógio da
sessão, congelado em 21/01/2019.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import HorarioAtendimento

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AGENDA = '/saude/agenda_atendimentos/'
ADICIONAR_HORARIO = '/saude/adicionar_horario_atendimento_saude/'
RESERVAR_HORARIO = '/saude/reservar_horario_atendimento/{}/'
CANCELAR_HORARIO = '/saude/cancelar_horario_atendimento/{}/'
BLOQUEAR_ALUNO = '/saude/bloquear_aluno_atendimento/{}/'
DESBLOQUEAR_ALUNO = '/saude/desbloquear_aluno_atendimento/{}/'
CANCELAR_HORARIOS = '/saude/cancelar_horarios_atendimentos/'
INFORMAR_MOTIVO = '/saude/informar_motivo_cancelamento_horario/'
VER_CALENDARIO = '/saude/ver_calendario_agendamento/'

DATA_ATENDIMENTO = '22/01/2019'


def _horarios_do_medico() -> list[HorarioAtendimento]:
    """Os horários publicados pelo médico para a data do teste, em ordem de início."""
    from saude.models import HorarioAtendimento

    return list(HorarioAtendimento.objects.filter(data='2019-01-22', especialidade='Médico').order_by('hora_inicio'))


def _abrir_agenda(tela: Tela) -> Tela:
    """Abre a agenda e remove o filtro `disponivel` que o produto aplica por padrão.

    Sem isso os horários já reservados (que é justamente onde vivem os botões de bloquear e
    cancelar) não aparecem na tabela.
    """
    tela.ir(AGENDA).ver_titulo('Agenda de Atendimentos')
    tela.filtros().preencher('Somente Disponíveis', 'Checkbox', 'desmarcar')
    tela.clicar_botao('Enviar')
    return tela


def test_agenda_gera_horarios_reserva_bloqueia_e_cancela(logado_saude: Callable[[str], Page]) -> None:
    """O médico publica dois horários; aluno e coordenador reservam; a agenda se encerra limpa."""
    medico = Tela(logado_saude('medico'))

    from saude.models import BloqueioAtendimentoSaude, HorarioAtendimento

    medico.ir(AGENDA).ver_titulo('Agenda de Atendimentos').clicar_botao('Adicionar Data de Atendimento')
    expect(medico.pagina).to_have_url(re.compile(rf'{ADICIONAR_HORARIO}$'))
    medico.preencher_formulario(
        [
            ('Campus do Atendimento', 'Lista', 'CZN'),
            ('Especialidade', 'Lista', 'Médico'),
            ('Data Inicial', 'Data', DATA_ATENDIMENTO),
            ('Modalidade', 'Radio', 'Presencial'),
            ('Horário de Início', 'Hora', '08:00'),
            ('Horário de Término', 'Hora', '09:00'),
            ('Duração de cada atendimento (em minutos)', 'Número', '30'),
        ]
    )
    medico.clicar_botao('Gerar Horários')
    # O formulário é um GET que só pré-visualiza: os horários nascem no clique do link
    # "Salvar", que reenvia a mesma query com `confirmado=True`.
    medico.clicar_link('Salvar').sucesso('Horário(s) de atendimento(s) registrado(s) com sucesso.')
    horarios = _horarios_do_medico()
    assert len(horarios) == 2, f'a tela deveria gerar dois horários de 30 minutos, gerou {len(horarios)}'
    primeiro, segundo = horarios
    assert primeiro.disponivel, 'o horário publicado deve nascer disponível'
    assert primeiro.vinculo_paciente is None, 'o horário publicado não pode nascer com paciente'

    # O aluno reserva pelo próprio login: a view de reserva confirma direto quando quem
    # reserva é o próprio paciente.
    aluno = Tela(logado_saude('aluno'))
    aluno.ir(AGENDA).ver_titulo('Agenda de Atendimentos')
    aluno.linha('08:00').clicar_botao('Agendar')
    aluno.sucesso('Horário de atendimento agendado com sucesso.')
    primeiro.refresh_from_db()
    assert primeiro.vinculo_paciente is not None, 'a UI disse que agendou, mas o horário continua livre'
    assert not primeiro.disponivel, 'o horário agendado deveria sair da lista de disponíveis'

    # O aluno já chega bloqueado pelo seed (bloqueio futuro do coordenador, da feature 0002),
    # e o produto oferece um botão só: "Desbloquear" enquanto houver bloqueio vigente.
    _abrir_agenda(medico)
    medico.linha('08:00').clicar_botao('Desbloquear Paciente')
    medico.sucesso('está desbloqueado(a).')
    assert not BloqueioAtendimentoSaude.objects.filter(vinculo_paciente=primeiro.vinculo_paciente, data__gte='2019-01-21').exists(), (
        'a UI disse que desbloqueou, mas o bloqueio vigente permanece'
    )

    # O bloqueio de 21 dias é oferecido ao profissional que publicou o horário, e só faz
    # sentido com um paciente marcado.
    _abrir_agenda(medico)
    medico.linha('08:00').clicar_botao('Bloquear Paciente')
    medico.sucesso('está bloqueado(a) até o dia')
    assert BloqueioAtendimentoSaude.objects.filter(vinculo_paciente=primeiro.vinculo_paciente, data='2019-02-11').exists(), (
        'a UI disse que bloqueou, mas o bloqueio de 21 dias não persistiu'
    )

    _abrir_agenda(medico)
    medico.linha('08:00').clicar_botao('Desbloquear Paciente')
    medico.sucesso('está desbloqueado(a).')
    assert not BloqueioAtendimentoSaude.objects.filter(vinculo_paciente=primeiro.vinculo_paciente, data__gte='2019-01-21').exists(), (
        'a UI disse que desbloqueou, mas o bloqueio de 21 dias permanece'
    )

    # O aluno cancela o próprio agendamento: o horário volta a ficar livre.
    _abrir_agenda(aluno)
    aluno.linha('08:00').clicar_botao('Cancelar')
    aluno.sucesso('Horário de atendimento cancelado com sucesso.')
    primeiro.refresh_from_db()
    assert primeiro.vinculo_paciente is None, 'a UI disse que cancelou, mas o paciente continua no horário'
    assert primeiro.disponivel, 'a UI disse que cancelou, mas o horário não voltou a ficar disponível'

    # O profissional agenda para outro paciente pelo formulário de reserva (o único caminho
    # em que a tela é renderizada, já que o paciente reserva direto).
    _abrir_agenda(medico)
    # A linha é ancorada pelo término: a linha do primeiro horário contém "08:30" no intervalo.
    medico.linha('09:00').clicar_botao('Agendar')
    expect(medico.pagina).to_have_url(re.compile(rf'{RESERVAR_HORARIO.format(segundo.pk)}$'))
    medico.preencher('Paciente', 'Autocomplete', '111001')
    medico.clicar_botao('Enviar').sucesso('Horário de atendimento agendado com sucesso.')
    segundo.refresh_from_db()
    assert segundo.vinculo_paciente is not None, 'a UI disse que agendou para o paciente, mas o horário continua livre'

    # Cancelamento em lote: como o horário tem paciente, o produto exige a justificativa
    # antes de cancelar (é o `informar_motivo_cancelamento_horario`).
    _abrir_agenda(medico)
    medico.selecionar_item('09:00')
    medico.clicar_botao('Aplicar').sucesso('Informe a justificativa de cancelamento')
    expect(medico.pagina).to_have_url(re.compile(rf'{INFORMAR_MOTIVO}\?ids={segundo.pk}$'))
    medico.preencher('Justificativa', 'TextArea', 'Justificativa do cancelamento E2E')
    medico.clicar_botao('Enviar').sucesso('Horários de atendimentos cancelados com sucesso.')
    segundo.refresh_from_db()
    assert segundo.cancelado, 'a UI disse que cancelou em lote, mas o horário continua ativo'
    assert segundo.motivo_cancelamento == 'Justificativa do cancelamento E2E', 'a justificativa do cancelamento em lote não persistiu'

    # O calendário consolida o período: com horários no intervalo, os meses são renderizados.
    _abrir_agenda(medico)
    medico.clicar_botao('Ver Calendário')
    expect(medico.pagina).to_have_url(re.compile(rf'{VER_CALENDARIO}\?'))
    medico.ver_texto('Legenda').ver_texto('Horário cancelado')

    assert HorarioAtendimento.objects.filter(pk__in=[primeiro.pk, segundo.pk]).count() == 2, 'os horários da agenda não podem desaparecer'


def test_cancelamento_de_horario_livre_pelo_profissional(logado_saude: Callable[[str], Page]) -> None:
    """O profissional cancela um horário sem paciente: o produto não pede justificativa."""
    medico = Tela(logado_saude('medico'))

    from saude.models import HorarioAtendimento

    medico.ir(AGENDA).ver_titulo('Agenda de Atendimentos').clicar_botao('Adicionar Data de Atendimento')
    medico.preencher_formulario(
        [
            ('Campus do Atendimento', 'Lista', 'CZN'),
            ('Especialidade', 'Lista', 'Médico'),
            ('Data Inicial', 'Data', DATA_ATENDIMENTO),
            ('Modalidade', 'Radio', 'Presencial'),
            ('Horário de Início', 'Hora', '10:00'),
            ('Horário de Término', 'Hora', '10:30'),
            ('Duração de cada atendimento (em minutos)', 'Número', '30'),
        ]
    )
    medico.clicar_botao('Gerar Horários')
    medico.clicar_link('Salvar').sucesso('Horário(s) de atendimento(s) registrado(s) com sucesso.')
    horario = HorarioAtendimento.objects.get(data='2019-01-22', hora_inicio='10:00:00', especialidade='Médico')

    _abrir_agenda(medico)
    expect(medico.linha('10:00').botao('Cancelar')).to_have_attribute('href', CANCELAR_HORARIO.format(horario.pk))
    medico.linha('10:00').clicar_botao('Cancelar')
    medico.sucesso('Horário de atendimento cancelado com sucesso.')
    horario.refresh_from_db()
    assert horario.cancelado, 'a UI disse que cancelou, mas o horário continua ativo'
    assert not horario.disponivel, 'o horário cancelado não pode continuar disponível'
    assert horario.motivo_cancelamento is None, 'horário sem paciente não deveria exigir justificativa'
