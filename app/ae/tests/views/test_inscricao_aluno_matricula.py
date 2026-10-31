from __future__ import annotations

from inspect import unwrap
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import PermissionDenied

from edu.models import Aluno
from ae import views


def test_inscricao_caracterizacao_rejeita_aluno_diferente(rf) -> None:
    request = rf.get('/ae/inscricao_caracterizacao/1/2/3/')
    request.user = MagicMock(is_authenticated=True, eh_aluno=True)
    aluno_alvo = MagicMock()
    aluno_diferente = MagicMock()
    request.user.get_relacionamento.return_value = aluno_diferente

    with (
        patch('ae.views.get_object_or_404', side_effect=[aluno_alvo, MagicMock(), MagicMock()]),
        patch('ae.views.impede_se_inscrever_sendo_participante'),
        patch('ae.views._obter_dados_alimentacao_caracterizacao', return_value=(False, False, None)),
        pytest.raises(PermissionDenied),
    ):
        unwrap(views.inscricao_caracterizacao)(request, aluno_id=1, periodo_id=2, programa_id=3)


def test_inscricao_confirmacao_filtra_aluno_por_matricula(rf) -> None:
    request = rf.get('/ae/inscricao_confirmacao/GEN/1/')
    request.user = MagicMock(is_authenticated=True, eh_aluno=True, username='20261012090004')
    request.user.has_perm.return_value = False

    aluno_outro = MagicMock()
    aluno_diferente = MagicMock()
    mock_inscricao = MagicMock()
    mock_inscricao.aluno = aluno_outro
    mock_inscricao.get_respostas_inscricao.return_value = []

    with (
        patch('ae.views.get_object_or_404', return_value=mock_inscricao),
        patch('ae.views.Aluno') as mock_aluno_cls,
    ):
        mock_aluno_cls.objects.filter.return_value.first.return_value = aluno_diferente
        with pytest.raises(PermissionDenied):
            unwrap(views.inscricao_confirmacao)(request, tipo_programa='GEN', inscricao_id=1)
        mock_aluno_cls.objects.filter.assert_called_with(matricula='20261012090004')
