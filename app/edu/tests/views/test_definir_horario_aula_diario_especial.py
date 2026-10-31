"""Testes da view e template de definir_horario_aula_diario_especial."""

from inspect import unwrap
from typing import Any
from unittest.mock import MagicMock, patch

from django.template.loader import render_to_string

from edu.views import diarios_especiais


def test_definir_horario_aula_diario_especial_sem_permissao_redireciona_com_erro(make_request: Any) -> None:
    user = MagicMock(is_authenticated=True)
    request = make_request(user=user)
    diario_especial = MagicMock(pk=1)

    with (
        patch.object(diarios_especiais, 'get_object_or_404', return_value=diario_especial),
        patch.object(diarios_especiais.perms, 'realizar_procedimentos_diarios_especiais', return_value=False),
        patch.object(diarios_especiais, 'httprr', return_value='REDIRECT_ERRO') as mock_httprr,
    ):
        resposta = unwrap(diarios_especiais.definir_horario_aula_diario_especial)(request, diario_especial_pk=1)

    mock_httprr.assert_called_once_with('..', 'Você não tem permissão para realizar isso.', 'error')
    assert resposta == 'REDIRECT_ERRO'


def test_definir_horario_aula_diario_especial_get_retorna_turnos_as_form(make_request: Any) -> None:
    user = MagicMock(is_authenticated=True)
    request = make_request(user=user)
    diario_especial = MagicMock(pk=1, horario_campus_id=10)
    diario_especial.get_horario_aulas.return_value = ''
    turnos_mock = MagicMock()
    diario_especial.get_horarios_aula_por_turno.return_value = turnos_mock

    with (
        patch.object(diarios_especiais, 'get_object_or_404', return_value=diario_especial),
        patch.object(diarios_especiais.perms, 'realizar_procedimentos_diarios_especiais', return_value=True),
        patch.object(diarios_especiais.HorarioAula.objects, 'filter') as mock_ha_filter,
    ):
        mock_ha_filter.return_value.exists.return_value = True
        contexto = unwrap(diarios_especiais.definir_horario_aula_diario_especial)(request, diario_especial_pk=1)

    assert contexto['turnos'] == turnos_mock
    assert turnos_mock.as_form is True
    assert 'Definir Horário de Aula' in contexto['title']


class TurnosList(list):
    as_form: bool = False


class TurnoMock:
    def __init__(self, pk: int, nome: str, vazio: bool, dias_semana: list, horarios_aula: list) -> None:
        self.pk = pk
        self.nome = nome
        self.vazio = vazio
        self.dias_semana = dias_semana
        self.horarios_aula = horarios_aula

    def __str__(self) -> str:
        return self.nome


class HorarioAulaMock:
    def __init__(self, pk: int, descricao: str, dias_semana: list, vazio: bool = False) -> None:
        self.pk = pk
        self.descricao = descricao
        self.dias_semana = dias_semana
        self.vazio = vazio

    def __str__(self) -> str:
        return self.descricao


def test_tabela_horarios_diario_especial_template_sem_horario_marcado_com_as_form() -> None:
    """Quando nenhum horário está marcado (turno.vazio é True), mas turnos.as_form é True,

    os horários disponíveis devem ser exibidos com checkbox para seleção.
    """
    obj = MagicMock(pk=42)
    horario_aula = HorarioAulaMock(
        pk=101,
        descricao='07:00 - 07:45',
        dias_semana=[{'numero': 1, 'nome': 'Segunda', 'marcado': 0, 'horario_aula_diario': None}],
    )
    turno = TurnoMock(
        pk=1,
        nome='Matutino',
        vazio=True,
        dias_semana=[[1, 'Segunda']],
        horarios_aula=[horario_aula],
    )

    turnos = TurnosList([turno])
    turnos.as_form = True

    rendered = render_to_string('includes/tabela_horarios_diario_especial.html', {'turnos': turnos, 'obj': obj})

    assert '<table' in rendered
    assert 'Matutino' in rendered
    assert '07:00 - 07:45' in rendered
    assert 'value="101;1"' in rendered
    assert 'checked="checked"' not in rendered


def test_tabela_horarios_diario_especial_template_sem_horario_marcado_sem_as_form() -> None:
    """Quando nenhum horário está marcado e turnos.as_form é False,

    o turno vazio não deve ser exibido.
    """
    obj = MagicMock(pk=42)
    turno = TurnoMock(
        pk=1,
        nome='Matutino',
        vazio=True,
        dias_semana=[[1, 'Segunda']],
        horarios_aula=[],
    )

    turnos = TurnosList([turno])
    turnos.as_form = False

    rendered = render_to_string('includes/tabela_horarios_diario_especial.html', {'turnos': turnos, 'obj': obj})

    assert '<table' not in rendered
    assert 'Matutino' not in rendered
