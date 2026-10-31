"""Regressão de ``gestao.tasks.detalhar_variavel_am_xls`` (Sentry SUAP-WYR).

Sem matrículas a lista de linhas ficava vazia (a task não monta cabeçalho) e ``XlsResponse``
estourava ``ValueError``: a task morria e o usuário ficava sem retorno. Agora ela termina
com a mensagem de que não há registros.
"""

import pytest

from djtools.models import Task
from edu.models import MatriculaPeriodo
from edu.tests.factories import MatriculaPeriodoFactory
from gestao import tasks

pytestmark = pytest.mark.django_db


def _tarefa_criada_pela_chamada(resposta) -> Task:
    """A task roda inline sob pytest e devolve o redirect para ``/djtools/process/<uuid>/``."""
    uuid = resposta.url.rstrip('/').rsplit('/', 1)[-1]
    return Task.objects.get(uuid=uuid)


def test_sem_matriculas_finaliza_com_aviso_em_vez_de_estourar_value_error():
    resposta = tasks.detalhar_variavel_am_xls(MatriculaPeriodo.objects.none())

    tarefa = _tarefa_criada_pela_chamada(resposta)
    assert tarefa.end is not None
    assert not tarefa.error
    assert not tarefa.file
    assert tarefa.message == 'Nenhum registro para exportar.'


def test_com_matriculas_gera_o_arquivo():
    matricula = MatriculaPeriodoFactory()

    resposta = tasks.detalhar_variavel_am_xls(MatriculaPeriodo.objects.filter(pk=matricula.pk))

    tarefa = _tarefa_criada_pela_chamada(resposta)
    assert not tarefa.error
    assert tarefa.file
