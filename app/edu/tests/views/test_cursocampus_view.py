from __future__ import annotations

from unittest.mock import Mock, PropertyMock, patch

from django.http import HttpResponseRedirect
from django.test import RequestFactory

from edu.models.cadastros_gerais import Modalidade
from edu.models.cursos import CursoCampus
from edu.views.cursos import cursocampus


def test_cursocampus_is_minicurso():
    minicurso = CursoCampus(modalidade_id=Modalidade.FIC_MENOS)
    assert minicurso.is_minicurso() is True

    curso_fic = CursoCampus(modalidade_id=Modalidade.FIC)
    assert curso_fic.is_minicurso() is False

    curso_regular = CursoCampus(modalidade_id=Modalidade.LICENCIATURA)
    assert curso_regular.is_minicurso() is False


def test_cursocampus_get_absolute_url():
    minicurso = CursoCampus(id=15, modalidade_id=Modalidade.FIC_MENOS)
    assert minicurso.get_absolute_url() == '/edu/minicurso/15/'

    curso_regular = CursoCampus(id=30, modalidade_id=Modalidade.LICENCIATURA)
    assert curso_regular.get_absolute_url() == '/edu/cursocampus/30/'


def test_cursocampus_view_redireciona_para_minicurso():
    curso_minicurso = CursoCampus(id=99, modalidade_id=Modalidade.FIC_MENOS)

    request = RequestFactory().get('/edu/cursocampus/99/')
    request.user = Mock()
    request.user.is_authenticated = True
    request.user.has_perm.return_value = True

    with (
        patch('djtools.middleware.threadlocals.get_request', return_value=request),
        patch('edu.views.cursos.get_object_or_404', return_value=curso_minicurso),
    ):
        response = cursocampus(request, 99)

    assert response.status_code == 302
    assert response['Location'] == '/edu/minicurso/99/'


def test_cursocampus_view_renderiza_quando_curso_regular():
    curso_regular = CursoCampus(id=101, modalidade_id=Modalidade.LICENCIATURA, suspenso=False)

    request = RequestFactory().get('/edu/cursocampus/101/')
    request.user = Mock()
    request.user.is_authenticated = True
    request.user.has_perm.return_value = True
    request.user.has_group_cached.return_value = False

    mock_manager = Mock()
    mock_manager.filter.return_value.exists.return_value = False

    with (
        patch('djtools.middleware.threadlocals.get_request', return_value=request),
        patch.object(CursoCampus, 'atoregulatoriocurso_set', new_callable=PropertyMock, return_value=mock_manager),
        patch('edu.views.cursos.get_object_or_404', return_value=curso_regular),
        patch('djtools.utils.response.render') as mock_render,
    ):
        mock_render.return_value = Mock(status_code=200)
        response = cursocampus(request, 101)

    assert response.status_code == 200
    mock_render.assert_called_once()


def test_adicionar_matriz_curso_view_rejeita_minicurso() -> None:
    from edu.views.cursos import adicionar_matriz_curso

    curso_minicurso = CursoCampus(id=99, modalidade_id=Modalidade.FIC_MENOS)

    request = RequestFactory().get('/edu/cursocampus/99/adicionar_matriz_curso/')
    request.user = Mock()
    request.user.is_authenticated = True
    request.user.has_perm.return_value = True

    with (
        patch('djtools.middleware.threadlocals.get_request', return_value=request),
        patch('edu.views.cursos.get_object_or_404', return_value=curso_minicurso),
        patch('edu.views.cursos.httprr') as mock_httprr,
    ):
        mock_httprr.return_value = HttpResponseRedirect('..')
        response = adicionar_matriz_curso(request, 99)

    assert response.status_code == 302
    mock_httprr.assert_called_once_with('..', 'Cursos da modalidade FIC- (Minicurso) não possuem matriz curricular.', 'error')
