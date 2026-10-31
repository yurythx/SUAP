from __future__ import annotations

from inspect import unwrap
from unittest.mock import MagicMock, patch

from edu.models import Aluno
from estagios import views


def test_ofertas_pratica_profissional_busca_aluno_pela_matricula(rf) -> None:
    request = rf.get('/estagios/ofertas_pratica_profissional/')
    request.user = MagicMock(is_authenticated=True, eh_aluno=True, username='20261012090004')

    with (
        patch('estagios.views.get_object_or_404') as mock_get_object_or_404,
        patch('estagios.views.OfertaPraticaProfissional') as mock_oferta,
    ):
        mock_aluno = MagicMock()
        mock_aluno.curso_campus.campus = MagicMock()
        mock_aluno.curso_campus.curso = MagicMock()
        mock_get_object_or_404.return_value = mock_aluno
        mock_oferta.objects.filter.return_value.distinct.return_value.order_by.return_value = []

        contexto = unwrap(views.ofertas_pratica_profissional)(request)

        mock_get_object_or_404.assert_called_once_with(Aluno, matricula='20261012090004')
        assert contexto['aluno'] == mock_aluno
