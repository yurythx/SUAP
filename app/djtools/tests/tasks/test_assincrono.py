import sys
import uuid
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from djtools.assincrono import execute_task, task


def _decorar_para_fila(func: Callable[..., object]) -> Callable[..., object]:
    with override_settings(USE_CELERY=True):
        return task('Teste assíncrono')(func)


def test_worker_executa_tarefa_sem_referencia_para_task() -> None:
    executada = False

    def tarefa() -> None:
        nonlocal executada
        executada = True

    _decorar_para_fila(tarefa).executar_de_dentro_da_fila(__path='/', __request='null')

    assert executada


def test_worker_preserva_excecao_original_sem_referencia_para_task() -> None:
    def tarefa() -> None:
        raise ValueError('falha original')

    with patch('djtools.assincrono.set_context') as set_context, pytest.raises(ValueError, match='falha original'):
        _decorar_para_fila(tarefa).executar_de_dentro_da_fila(__path='/teste/', __request='null')

    set_context.assert_called_once_with('request', {'user': 'None', 'task_id': None, 'path': '/teste/'})


@pytest.mark.django_db
def test_chamada_direta_dentro_do_worker_enfileira_em_vez_de_desserializar() -> None:
    """
    Reproduz o SUAP-VXS: um signal disparado dentro de um worker Celery (ex.:
    `centralservicos.signals.servico_atualizar_estatisticas`, chamado a partir do
    `on_finish` de outra task) invoca uma função `@task` como uma chamada Python comum,
    passando o objeto vivo diretamente — não os argumentos já serializados que só
    `execute_task` entrega. Essa chamada direta precisa enfileirar (`decorate_suap`),
    nunca cair na desserialização (`decorate_celery`), senão explode com TypeError.
    """
    from djtools.models import Task as TaskModel

    def tarefa(instancia, task=None) -> None:
        raise AssertionError('não deveria executar em processo: a chamada direta deve enfileirar')

    decorada = _decorar_para_fila(tarefa)
    instancia_viva = TaskModel.objects.create(type='instancia-de-teste')

    with patch('djtools.assincrono.execute_task.apply_async') as apply_async:
        apply_async.return_value = MagicMock(id=str(uuid.uuid4()))
        resultado = decorada(instancia_viva)

    apply_async.assert_called_once()
    assert resultado.status_code == 302


@pytest.mark.django_db
def test_execute_task_invoca_a_versao_desserializada_da_fila() -> None:
    from djtools.utils import serialization

    chamadas = []

    def tarefa(valor: int, task=None) -> None:
        chamadas.append(valor)

    decorada = _decorar_para_fila(tarefa)
    modulo_atual = sys.modules[tarefa.__module__]
    modulo_atual.tarefa_registrada_para_teste = decorada
    try:
        execute_task(modulo_atual.__name__, 'tarefa_registrada_para_teste', serialization.serialize(7), __path='/', __request='null')
    finally:
        del modulo_atual.tarefa_registrada_para_teste

    assert chamadas == [7]
