"""Tests for beat.beat — load_tasks_schedule."""

import json

import pytest

from beat.beat import load_tasks_schedule
from beat.models import Agendamento


AGENDAMENTO_NOME = '[beat] Limpar Resultados de Execução'


@pytest.mark.django_db
def test_creates_limpar_resultado_agendamento():
    load_tasks_schedule()
    agendamento = Agendamento.objects.filter(name=AGENDAMENTO_NOME).first()
    assert agendamento is not None
    assert agendamento.task == 'beat.tasks.call_command'
    assert agendamento.queue == 'beat'
    assert json.loads(agendamento.args) == ['limpar_resultado_execucao']
    assert json.loads(agendamento.kwargs) == {'days': 30}
    assert agendamento.crontab is not None
    assert agendamento.crontab.hour == '10'
    assert agendamento.crontab.minute == '0'


@pytest.mark.django_db
def test_idempotent():
    load_tasks_schedule()
    load_tasks_schedule()
    assert Agendamento.objects.filter(name=AGENDAMENTO_NOME).count() == 1
