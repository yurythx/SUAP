from unittest.mock import MagicMock, patch

from edu.models.historico import MatriculaDiario, MatriculaPeriodo


def test_get_horarios_aula_atividade_por_turno_ignora_transferidos() -> None:
    """Valida que diários com situação Transferido, Trancado ou Cancelado são ignorados na grade."""
    matricula_periodo = MatriculaPeriodo()

    mock_md_set = MagicMock()
    mock_filter_situacao = MagicMock()
    mock_values_list = MagicMock()
    # Simula que o diário 100 está transferido e o 200 trancado
    mock_values_list.return_value = [100, 200]
    mock_filter_situacao.values_list = mock_values_list
    mock_md_set.filter.return_value = mock_filter_situacao

    mock_diario = MagicMock()
    mock_diario.objects.filter.return_value.values_list.return_value = [1]

    mock_horario_campus = MagicMock()
    mock_horario_campus.objects.filter.return_value.values_list.return_value = [1]

    mock_turno = MagicMock()
    mock_turno_instance = MagicMock()
    mock_turno_instance.horarios_aula = []
    mock_turno_instance.horarioaula_set.filter.return_value.order_by.return_value.order_by.return_value = []

    mock_turnos_qs = MagicMock()
    mock_turnos_qs.__iter__.return_value = [mock_turno_instance]
    mock_turno.objects.filter.return_value.order_by.return_value = mock_turnos_qs

    mock_horario_aula_diario = MagicMock()
    mock_horario_aula_diario.DIA_SEMANA_CHOICES = [(1, 'Segunda')]

    with (
        patch.object(MatriculaPeriodo, 'matriculadiario_set', mock_md_set),
        patch('edu.models.Diario', mock_diario),
        patch('edu.models.HorarioCampus', mock_horario_campus),
        patch('edu.models.Turno', mock_turno),
        patch('edu.models.HorarioAulaDiario', mock_horario_aula_diario),
        patch('edu.models.HorarioAtividadeExtra', MagicMock()),
    ):
        result = matricula_periodo.get_horarios_aula_atividade_por_turno()

    # Confirma que a query de diários ignorados busca TRANCADO, CANCELADO e TRANSFERIDO
    mock_md_set.filter.assert_called_once_with(
        situacao__in=[
            MatriculaDiario.SITUACAO_TRANCADO,
            MatriculaDiario.SITUACAO_CANCELADO,
            MatriculaDiario.SITUACAO_TRANSFERIDO,
        ]
    )
    assert result.vazio is True


def test_get_horarios_aula_atividade_por_turno_exclui_diarios_transferidos_da_busca_de_horarios() -> None:
    """Verifica que a query de horários de aula aplica exclude com os IDs dos diários ignorados."""
    matricula_periodo = MatriculaPeriodo()

    mock_md_set = MagicMock()
    mock_filter_situacao = MagicMock()
    mock_values_list = MagicMock()
    # Diário transferido com ID 999
    mock_values_list.return_value = [999]
    mock_filter_situacao.values_list = mock_values_list
    mock_md_set.filter.return_value = mock_filter_situacao

    mock_diario = MagicMock()
    mock_diario.objects.filter.return_value.values_list.return_value = [1]

    mock_horario_campus = MagicMock()
    mock_horario_campus.objects.filter.return_value.values_list.return_value = [1]

    mock_horario_aula = MagicMock()
    mock_horario_aula.dias_semana = []

    mock_turno_instance = MagicMock()
    mock_turno_instance.horarios_aula = []
    mock_turno_instance.horarioaula_set.filter.return_value.order_by.return_value.order_by.return_value = [mock_horario_aula]

    mock_turnos_qs = MagicMock()
    mock_turnos_qs.__iter__.return_value = [mock_turno_instance]

    mock_turno = MagicMock()
    mock_turno.objects.filter.return_value.order_by.return_value = mock_turnos_qs

    mock_horario_aula_diario = MagicMock()
    mock_horario_aula_diario.DIA_SEMANA_CHOICES = [(1, 'Segunda')]
    mock_qs_had = MagicMock()
    mock_qs_had.exists.return_value = False
    mock_horario_aula_diario.objects.filter.return_value.exclude.return_value = mock_qs_had

    with (
        patch.object(MatriculaPeriodo, 'matriculadiario_set', mock_md_set),
        patch('edu.models.Diario', mock_diario),
        patch('edu.models.HorarioCampus', mock_horario_campus),
        patch('edu.models.Turno', mock_turno),
        patch('edu.models.HorarioAulaDiario', mock_horario_aula_diario),
        patch('edu.models.HorarioAtividadeExtra', MagicMock()),
    ):
        matricula_periodo.get_horarios_aula_atividade_por_turno()

    # Confirma que o exclude foi chamado com os diários ignorados (incluindo o transferido 999)
    mock_horario_aula_diario.objects.filter.return_value.exclude.assert_called_with(diario__in=[999])
