"""`disciplina` (visão do aluno) acha o aluno pelo usuário logado, não pela pessoa física.

Depois da deduplicação uma pessoa pode ter vários alunos; buscar `Aluno` por `pessoa_fisica` dava
`MultipleObjectsReturned` (500). O `Diario` é mockado na fronteira (não há factory e o grafo é enorme):
o que se verifica é para qual aluno a view consulta a matrícula.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client

from edu.tests.factories import AlunoFactory
from edu.views import diarios
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_disciplina_usa_o_aluno_do_usuario_quando_a_pessoa_tem_dois(client: Client, sync_permissions: None) -> None:
    # sync_permissions: o login do aluno põe o usuário no grupo 'Aluno' (user_post_save), que só ele cria
    aluno = AlunoFactory()
    outro = AlunoFactory(pessoa_fisica=aluno.pessoa_fisica)  # mesma pessoa, outra matrícula
    diario = MagicMock()
    diario.matriculadiario_set.filter.return_value.exists.return_value = False
    client.force_login(outro.get_user())

    with patch.object(diarios, 'get_object_or_404', return_value=diario):
        resposta = client.get('/edu/disciplina/1/')

    diario.matriculadiario_set.filter.assert_called_once_with(matricula_periodo__aluno=outro)
    assert resposta.status_code == 302  # "Você não tem permissão para isso", sem 500


def test_disciplina_recusa_usuario_que_nao_e_aluno(client: Client, sync_permissions) -> None:
    client.force_login(ServidorFactory().get_user())

    with patch.object(diarios, 'get_object_or_404', return_value=MagicMock()):
        resposta = client.get('/edu/disciplina/1/')

    assert resposta.status_code == 302
