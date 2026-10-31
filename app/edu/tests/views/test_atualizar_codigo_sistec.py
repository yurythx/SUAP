from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseRedirect
from django.test import RequestFactory

from edu.views.censos import atualizar_codigo_sistec


def test_atualizar_codigo_sistec_get() -> None:
    rf = RequestFactory()
    request = rf.get('/edu/atualizar_codigo_sistec/')
    request.user = MagicMock(is_authenticated=True)
    request.user.has_perm.return_value = True

    with patch('djtools.utils.response.render') as mock_render:
        atualizar_codigo_sistec(request)
        mock_render.assert_called_once()
        _, ctx, _, _ = mock_render.call_args[0]
        assert 'form' in ctx
        assert 'atualizar_data_fim' in ctx['form'].fields


@patch('edu.views.censos.tasks.atualizar_sistec_aluno')
@patch('edu.views.censos.get_temp_storage')
def test_atualizar_codigo_sistec_post(mock_storage, mock_task) -> None:
    rf = RequestFactory()

    mock_storage_inst = MagicMock()
    mock_file = MagicMock()
    mock_file.name = 'temp_planilha.csv'
    mock_storage_inst.open.return_value = mock_file
    mock_storage.return_value = mock_storage_inst

    mock_task.return_value = HttpResponseRedirect('/edu/auditoria_ensino/')

    csv_content = b'MATRICULA;CO_MATRICULA\n2023101;123456\n'
    uploaded = SimpleUploadedFile('planilha.csv', csv_content, content_type='text/csv')

    data = {
        'planilha': uploaded,
        'sobrescrever': 'on',
        'atualizar': 'on',
        'atualizar_data_fim': 'on',
    }

    request = rf.post('/edu/atualizar_codigo_sistec/', data)
    request.user = MagicMock(is_authenticated=True)
    request.user.has_perm.return_value = True

    resp = atualizar_codigo_sistec(request)

    mock_task.assert_called_once()
    assert resp.status_code == 302
    _, kwargs = mock_task.call_args
    assert kwargs['sobrescrever_codigo'] is True
    assert kwargs['atualizar_data_inicio'] is True
    assert kwargs['atualizar_data_fim'] is True
