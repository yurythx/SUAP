from __future__ import annotations

from unittest.mock import MagicMock, patch
from django.test import RequestFactory
from pit_rit_v3.models import PlanoIndividualTrabalhoV3
from pit_rit_v3.views import criar_plano


class TestCriarPlanoView:
    @patch('djtools.middleware.threadlocals.get_request')
    @patch.object(PlanoIndividualTrabalhoV3, 'modulo_ativo', return_value=False)
    def test_bloqueia_acesso_quando_modulo_nao_ativo(self, mock_modulo_ativo, mock_get_request) -> None:
        factory = RequestFactory()
        request = factory.get('/pit_rit_v3/criar_plano/1/')
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.session = {}
        request._messages = MagicMock()
        mock_get_request.return_value = request

        response = criar_plano(request, professor_id=1)
        # Deve redirecionar para a raiz com mensagem de erro
        assert response.status_code == 302
        assert response['Location'] == '/'
