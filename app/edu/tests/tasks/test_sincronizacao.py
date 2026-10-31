"""Teste DB-free da task ``sincronizar_turma_moodle`` (``edu/tasks.py:91``).

Exercita os dois ramos (sucesso e erro de comunicação com o Moodle) com a API externa
e o objeto Task mockados. Sem banco: sob pytest o decorator ``@task`` executa síncrono
inline e ``patch_task_model`` (em ``conftest.py``) injeta o ``task_mock``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from edu.moodle import ApiMoodleService
from edu.tasks import sincronizar_turma_moodle


def _api_externa_moodle(headers: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        headers=headers,
        url_base='https://ava.local',
        tipo_autenticacao='sem_autenticacao',
        CONECTA_AUTH='conecta',
        CLIENT_CREDENTIALS_AUTH='client_credentials',
        CPF_AUTH='cpf',
        BASIC_AUTH='basic',
        TOKEN_AUTH='token',
        API_KEY_AUTH='api_key',
        DATAPREV_AUTH='dataprev',
    )


@pytest.mark.usefixtures('patch_task_model')
class TestSincronizarTurmaMoodle:
    def _turma_com_diario(self, diario):
        turma = MagicMock()
        turma.diario_set.filter.return_value = [diario]
        return turma

    def test_sincroniza_e_grava_url_no_diario(self, task_mock):
        diario = MagicMock(url_moodle=None)
        turma = self._turma_com_diario(diario)
        service = MagicMock()
        service.sincronizar.return_value = 'http://moodle.local/course/1'

        with patch('edu.tasks.APIExterna') as mock_api:
            mock_api.MOODLE.get_service.return_value = service
            sincronizar_turma_moodle(turma)

        assert diario.url_moodle == 'http://moodle.local/course/1'
        diario.save.assert_called_once()
        task_mock.finalize.assert_called_once_with('Turma sincronizada com sucesso.')

    def test_finaliza_com_erro_quando_moodle_falha(self, task_mock):
        diario = MagicMock()
        turma = self._turma_com_diario(diario)
        service = MagicMock()
        service.sincronizar.side_effect = Exception('timeout')

        with (
            patch('edu.tasks.APIExterna') as mock_api,
            patch('edu.tasks.capture_exception') as mock_capture,
        ):
            mock_api.MOODLE.get_service.return_value = service
            sincronizar_turma_moodle(turma)

        mock_capture.assert_called_once()
        diario.save.assert_not_called()
        assert task_mock.finalize.call_args.kwargs.get('error') is True


class TestApiMoodleService:
    def test_get_headers_nao_remove_paths_cadastrados(self) -> None:
        headers = {
            'enviar_diarios_path': '/api/enviar_diarios/',
            'baixar_notas_path': '/api/baixar_notas/',
            'turma_minicurso_id': 0,
        }
        service = object.__new__(ApiMoodleService)
        service.api_externa = _api_externa_moodle(headers)

        service.get_headers()
        assert service.moodle_export_url == 'https://ava.local/api/enviar_diarios/'

        service.get_headers()
        assert service.moodle_export_url == 'https://ava.local/api/enviar_diarios/'
        assert headers['enviar_diarios_path'] == '/api/enviar_diarios/'
