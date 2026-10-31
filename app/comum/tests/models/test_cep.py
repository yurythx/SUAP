"""Consulta de CEP (``comum/services/cep.py``).

O service nunca propaga exceção: qualquer falha vira ``(False, {'erro': ...})``. Os
testes cobrem o caminho feliz e cada família de falha, porque o par devolvido é o que os
formulários de endereço consomem.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock, patch

import pytest
from requests.exceptions import HTTPError, Timeout

from comum.services.cep import ApiCEPService


@pytest.fixture
def service_cep(montar_service: Callable[..., Any]) -> Any:
    service = montar_service(ApiCEPService, tipo_autenticacao='TOKEN_AUTH', endpoint='/ws/', url_base='https://viacep.com.br')
    service.get_token = Mock(return_value='token-falso')
    return service


class TestConsultaCep:
    @patch('comum.services.cep.requests.get')
    def test_cep_encontrado_devolve_o_endereco(self, mock_get: Mock, service_cep: Any) -> None:
        endereco = {'cep': '59300-000', 'localidade': 'Currais Novos', 'uf': 'RN'}
        mock_get.return_value = Mock(ok=True, **{'json.return_value': endereco})

        sucesso, resposta = service_cep.consulta_cep('59300000')

        assert sucesso
        assert resposta == endereco
        assert mock_get.call_args.args[0] == 'https://viacep.com.br/ws/59300000'

    @pytest.mark.parametrize('falha', [Timeout('tempo esgotado'), HTTPError('500 Server Error')])
    @patch('comum.services.cep.requests.get')
    def test_falha_de_rede_vira_par_negativo_com_o_detalhe(self, mock_get: Mock, service_cep: Any, falha: Exception) -> None:
        mock_get.side_effect = falha

        sucesso, resposta = service_cep.consulta_cep('59300000')

        assert not sucesso
        assert 'Erro de comunicação com a API de CEP' in resposta['erro']
        assert str(falha) in resposta['erro']

    @patch('comum.services.cep.requests.get')
    def test_status_de_erro_e_convertido_por_raise_for_status(self, mock_get: Mock, service_cep: Any) -> None:
        resposta_http = Mock(ok=False)
        resposta_http.raise_for_status.side_effect = HTTPError('404 Not Found')
        mock_get.return_value = resposta_http

        sucesso, resposta = service_cep.consulta_cep('00000000')

        assert not sucesso
        assert '404 Not Found' in resposta['erro']

    @patch('comum.services.cep.requests.get')
    def test_json_malformado_e_reportado_como_erro_de_decodificacao(self, mock_get: Mock, service_cep: Any) -> None:
        """Corpo quebrado é diagnosticado como falha de decodificação, não de comunicação.

        ``requests.exceptions.JSONDecodeError`` herda de ``RequestException``; por isso a
        cláusula do JSON vem antes no service.
        """
        from requests.exceptions import JSONDecodeError

        resposta_http = Mock(ok=True)
        resposta_http.json.side_effect = JSONDecodeError('Expecting value', '<html>', 0)
        mock_get.return_value = resposta_http

        sucesso, resposta = service_cep.consulta_cep('59300000')

        assert not sucesso
        assert 'Erro ao decodificar resposta JSON da API de CEP' in resposta['erro']

    @patch('comum.services.cep.requests.get')
    def test_erro_inesperado_tambem_e_contido(self, mock_get: Mock, service_cep: Any) -> None:
        mock_get.side_effect = RuntimeError('estourou')

        sucesso, resposta = service_cep.consulta_cep('59300000')

        assert not sucesso
        assert 'Erro inesperado ao consultar API de CEP' in resposta['erro']


class TestEstahAcessivel:
    @patch('comum.services.cep.requests.get')
    def test_sonda_a_api_com_um_cep_conhecido(self, mock_get: Mock, service_cep: Any) -> None:
        mock_get.return_value = Mock(ok=True, **{'json.return_value': {'cep': '59300-000'}})

        assert service_cep.estah_acessivel() is True
        assert mock_get.call_args.args[0].endswith('59300000')

    @patch('comum.services.cep.requests.get')
    def test_api_fora_do_ar_e_reportada_como_inacessivel(self, mock_get: Mock, service_cep: Any) -> None:
        mock_get.side_effect = Timeout('tempo esgotado')

        assert service_cep.estah_acessivel() is False
