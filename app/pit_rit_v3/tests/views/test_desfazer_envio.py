from __future__ import annotations

from unittest.mock import MagicMock, patch
from django.test import RequestFactory

from pit_rit_v3.views import desfazer_envio_plano, desfazer_envio_relatorio


class TestDesfazerEnvioPlanoView:
    def setup_method(self) -> None:
        self.factory = RequestFactory()
        self.request = self.factory.get('/pit_rit_v3/desfazer_envio_plano/1/')
        self.request.user = MagicMock()
        self.request.user.is_authenticated = True
        self.request.session = {}
        self.request._messages = MagicMock()

    @patch('djtools.middleware.threadlocals.get_request')
    @patch('pit_rit_v3.views.get_object_or_404')
    def test_bloqueia_quando_sem_permissao(self, mock_get_object, mock_get_request) -> None:
        mock_get_request.return_value = self.request
        pit = MagicMock()
        pit.pode_desfazer_envio_plano.return_value = False
        mock_get_object.return_value = pit

        response = desfazer_envio_plano(self.request, pk=1)

        assert response.status_code == 302
        assert response['Location'] == '/'
        pit.desfazer_envio_plano.assert_not_called()

    @patch('djtools.middleware.threadlocals.get_request')
    @patch('pit_rit_v3.views.get_object_or_404')
    def test_desfaz_envio_com_sucesso(self, mock_get_object, mock_get_request) -> None:
        mock_get_request.return_value = self.request
        pit = MagicMock()
        pit.pode_desfazer_envio_plano.return_value = True
        pit.get_absolute_url.return_value = '/edu/professor/1/?tab=planoatividades'
        mock_get_object.return_value = pit

        response = desfazer_envio_plano(self.request, pk=1)

        pit.desfazer_envio_plano.assert_called_once_with(self.request.user)
        assert response.status_code == 302
        assert response['Location'] == '/edu/professor/1/?tab=planoatividades'


class TestDesfazerEnvioRelatorioView:
    def setup_method(self) -> None:
        self.factory = RequestFactory()
        self.request = self.factory.get('/pit_rit_v3/desfazer_envio_relatorio/1/')
        self.request.user = MagicMock()
        self.request.user.is_authenticated = True
        self.request.session = {}
        self.request._messages = MagicMock()

    @patch('djtools.middleware.threadlocals.get_request')
    @patch('pit_rit_v3.views.get_object_or_404')
    def test_bloqueia_quando_sem_permissao(self, mock_get_object, mock_get_request) -> None:
        mock_get_request.return_value = self.request
        pit = MagicMock()
        pit.pode_desfazer_envio_relatorio.return_value = False
        mock_get_object.return_value = pit

        response = desfazer_envio_relatorio(self.request, pk=1)

        assert response.status_code == 302
        assert response['Location'] == '/'
        pit.desfazer_envio_relatorio.assert_not_called()

    @patch('djtools.middleware.threadlocals.get_request')
    @patch('pit_rit_v3.views.get_object_or_404')
    def test_desfaz_envio_com_sucesso(self, mock_get_object, mock_get_request) -> None:
        mock_get_request.return_value = self.request
        pit = MagicMock()
        pit.pode_desfazer_envio_relatorio.return_value = True
        pit.get_absolute_url.return_value = '/edu/professor/1/?tab=planoatividades'
        mock_get_object.return_value = pit

        response = desfazer_envio_relatorio(self.request, pk=1)

        pit.desfazer_envio_relatorio.assert_called_once_with(self.request.user)
        assert response.status_code == 302
        assert response['Location'] == '/edu/professor/1/?tab=planoatividades'
