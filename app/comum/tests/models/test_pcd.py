"""Consulta da API de Pessoa com Deficiência (``comum/services/pcd.py``).

O service devolve sempre um par ``(sucesso, dados)``. Falha de rede ou de obtenção do token
vira ``(False, [])`` e o motivo vai sempre para o log (#17413).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from requests.exceptions import Timeout

from comum.services.pcd import ApiPCDService


@pytest.fixture
def service_pcd(montar_service: Callable[..., Any]) -> Any:
    service = montar_service(ApiPCDService, tipo_autenticacao='API KEY', endpoint='/pcd/', url_base='https://api.exemplo.gov.br')
    service.get_token = Mock(return_value='token-falso')
    return service


class TestGetDadosPessoais:
    @patch('comum.services.pcd.requests.get')
    def test_consulta_bem_sucedida_devolve_o_json(self, mock_get: Mock, service_pcd: Any) -> None:
        mock_get.return_value = Mock(ok=True, content=b'{"pcd": true}', **{'json.return_value': {'pcd': True}})

        sucesso, dados = service_pcd.get_dados_pessoais('12345678901')

        assert sucesso
        assert dados == {'pcd': True}
        assert mock_get.call_args.args[0] == 'https://api.exemplo.gov.br/pcd/12345678901'
        assert mock_get.call_args.kwargs['headers']['X-API-KEY'] == 'token-falso'

    @patch('comum.services.pcd.requests.get')
    def test_corpo_vazio_e_sucesso_sem_dados(self, mock_get: Mock, service_pcd: Any) -> None:
        # 200 sem corpo significa "consultei e não há registro", não erro.
        mock_get.return_value = Mock(ok=True, content=b'')

        assert service_pcd.get_dados_pessoais('12345678901') == (True, None)

    @patch('comum.services.pcd.requests.get')
    def test_status_de_erro_devolve_o_corpo_bruto_e_loga(self, mock_get: Mock, service_pcd: Any, caplog: pytest.LogCaptureFixture) -> None:
        mock_get.return_value = Mock(ok=False, status_code=403, content=b'Forbidden')

        with caplog.at_level('WARNING', logger='comum.services.pcd'):
            assert service_pcd.get_dados_pessoais('12345678901') == (False, [b'Forbidden'])

        assert 'HTTP 403' in caplog.text

    @patch('comum.services.pcd.requests.get')
    def test_falha_de_rede_vai_para_o_log_mesmo_sem_verbosity(self, mock_get: Mock, service_pcd: Any, caplog: pytest.LogCaptureFixture) -> None:
        mock_get.side_effect = Timeout('tempo esgotado')

        with caplog.at_level('WARNING', logger='comum.services.pcd'):
            assert service_pcd.get_dados_pessoais('12345678901') == (False, [])

        assert 'tempo esgotado' in caplog.text

    @patch('comum.services.pcd.requests.get')
    def test_falha_ao_obter_o_token_vai_para_o_log(self, mock_get: Mock, service_pcd: Any, caplog: pytest.LogCaptureFixture) -> None:
        service_pcd.get_token.side_effect = ValidationError('credenciais recusadas')

        with caplog.at_level('WARNING', logger='comum.services.pcd'):
            assert service_pcd.get_dados_pessoais('12345678901') == (False, [])

        assert 'credenciais recusadas' in caplog.text
        mock_get.assert_not_called()

    @patch('comum.services.pcd.requests.get')
    def test_erro_de_programacao_nao_e_engolido(self, mock_get: Mock, service_pcd: Any) -> None:
        mock_get.side_effect = TypeError('argumento inesperado')

        with pytest.raises(TypeError):
            service_pcd.get_dados_pessoais('12345678901')


class TestEstahAcessivel:
    @patch('comum.services.pcd.requests.get')
    def test_sonda_a_api_com_o_cpf_do_operador(self, mock_get: Mock, service_pcd: Any) -> None:
        mock_get.return_value = Mock(ok=True, content=b'{}', **{'json.return_value': {}})

        assert service_pcd.estah_acessivel() is True
        assert mock_get.call_args.args[0].endswith(service_pcd.cpf_operador)

    @patch('comum.services.pcd.requests.get')
    def test_api_fora_do_ar_e_reportada_como_inacessivel(self, mock_get: Mock, service_pcd: Any) -> None:
        mock_get.side_effect = Timeout('tempo esgotado')

        assert service_pcd.estah_acessivel() is False
