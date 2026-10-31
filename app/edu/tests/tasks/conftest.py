"""Fixtures compartilhadas para os testes DB-free das tasks do edu.

As tasks usam o decorator custom ``@task`` (``djtools/assincrono``), não Celery nativo.
Sob pytest, ``running_tests()`` já é True (``PYTEST_CURRENT_TEST`` no ambiente) e
``USE_CELERY`` é False, então o decorator executa a função de forma síncrona inline e
injeta um ``task`` vindo de ``Task.objects.create`` — aqui mockado por ``patch_task_model``.
Nenhuma fixture toca o banco.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def task_mock():
    """Mock do objeto Task injetado pelo decorator (``iterate`` atravessa o iterável)."""
    task = MagicMock()
    task.iterate.side_effect = lambda itens: itens
    return task


@pytest.fixture
def patch_task_model(task_mock):
    """Substitui ``Task.objects.create`` pelo ``task_mock`` (o decorator injeta esse task)."""
    with (
        patch('djtools.models.Task.objects.create', return_value=task_mock),
        patch('djtools.models.Task.objects.filter'),
    ):
        yield
