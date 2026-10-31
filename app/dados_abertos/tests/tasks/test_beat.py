"""Testes do agendamento Celery Beat do módulo de dados abertos."""

import json

import pytest

from beat.models import Agendamento, Crontab
from django.core.management import get_commands
from dados_abertos.beat import load_tasks_schedule

NOME_ATUALIZACAO = '[dados_abertos] Atualizar Bases de Dados Abertos'
NOME_NOTIFICACAO = '[dados_abertos] Notificar Pendências do PDA'


@pytest.mark.django_db
def test_agenda_atualizacao_diaria_e_notificacao_semanal():
    load_tasks_schedule()

    tarefas = {tarefa.name: tarefa for tarefa in Agendamento.objects.filter(name__in=[NOME_ATUALIZACAO, NOME_NOTIFICACAO])}

    assert set(tarefas) == {NOME_ATUALIZACAO, NOME_NOTIFICACAO}
    assert json.loads(tarefas[NOME_ATUALIZACAO].args) == ['atualizar_bases_dados_abertos']
    assert json.loads(tarefas[NOME_NOTIFICACAO].args) == ['notificar_pendencias_dados_abertos']
    assert {'atualizar_bases_dados_abertos', 'notificar_pendencias_dados_abertos'} <= set(get_commands())

    crontab_atualizacao = tarefas[NOME_ATUALIZACAO].crontab
    assert (crontab_atualizacao.minute, crontab_atualizacao.hour, crontab_atualizacao.day_of_week) == ('47', '2', '*')
    assert tarefas[NOME_ATUALIZACAO].expire_seconds == 23 * 3600

    crontab_notificacao = tarefas[NOME_NOTIFICACAO].crontab
    assert (crontab_notificacao.minute, crontab_notificacao.hour, crontab_notificacao.day_of_week) == ('47', '7', '1')
    assert tarefas[NOME_NOTIFICACAO].expire_seconds == 72 * 3600


@pytest.mark.django_db
def test_importacao_repetida_nao_duplica_agendamentos():
    load_tasks_schedule()
    load_tasks_schedule()

    assert Agendamento.objects.filter(name__in=[NOME_ATUALIZACAO, NOME_NOTIFICACAO]).count() == 2


@pytest.mark.django_db
def test_reimportacao_preserva_cadencia_ajustada_no_admin():
    load_tasks_schedule()
    ajustado = Crontab.objects.create(minute='13', hour='4', day_of_month='*', month_of_year='*', day_of_week='*')
    Agendamento.objects.filter(name=NOME_ATUALIZACAO).update(crontab=ajustado)

    load_tasks_schedule()

    assert Agendamento.objects.get(name=NOME_ATUALIZACAO).crontab_id == ajustado.pk
