"""Comportamento do service base de APIs externas (``comum/services/api_externa.py``).

``APIExternaService`` é a fronteira do SUAP com serviços de terceiros (Conecta GovBR,
Dataprev, Serpro): decide o esquema de autenticação, busca o token, cacheia por uma hora
e monta os cabeçalhos. Só a chamada HTTP é mockada — a lógica de decisão é o alvo.

Os testes afirmam também **qual** ``ValidationError`` sai de cada falha: a mensagem é o
que o operador lê na tela de diagnóstico das APIs externas.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock, patch

import pytest
import requests as requests_lib
from django.conf import settings
from django.core.exceptions import ValidationError

from comum.services.api_externa import APIExternaService


@pytest.fixture
def cache_de_token():
    """Substitui o cache do módulo por um dicionário, isolando os tokens entre testes."""
    armazem: dict[str, Any] = {}
    falso = Mock()
    falso.get.side_effect = lambda chave, *args, **kwargs: armazem.get(chave)
    falso.set.side_effect = lambda chave, valor, *args, **kwargs: armazem.__setitem__(chave, valor)
    with patch('comum.services.api_externa.cache', falso):
        yield armazem


def _resposta(ok: bool = True, payload: dict | None = None) -> Mock:
    resposta = Mock()
    resposta.ok = ok
    resposta.json.return_value = payload if payload is not None else {}
    return resposta


class TestGetTimeout:
    def test_usa_o_timeout_configurado_no_settings(self, montar_service: Callable[..., Any]) -> None:
        assert montar_service(APIExternaService).get_timeout() == settings.REQUESTS_TIMEOUT


class TestBasicAuthToken:
    def test_codifica_client_id_e_secret_em_base64(self, montar_service: Callable[..., Any]) -> None:
        service = montar_service(APIExternaService, client_id='usuario', secret='senha')
        assert base64.b64decode(service.basic_auth_token()).decode() == 'usuario:senha'


class TestGetToken:
    def test_token_em_cache_dispensa_ida_a_rede(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService)
        cache_de_token[service.cache_name] = 'token-cacheado'
        with patch('comum.services.api_externa.requests.post') as mock_post:
            assert service.get_token() == 'token-cacheado'
        mock_post.assert_not_called()

    @pytest.mark.parametrize('tipo', ['TOKEN_AUTH', 'API KEY'])
    def test_autenticacao_por_chave_fixa_devolve_o_secret(self, montar_service: Callable[..., Any], cache_de_token: dict, tipo: str) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao=tipo, secret='chave-fixa')
        assert service.get_token() == 'chave-fixa'

    def test_autenticacao_basica_devolve_as_credenciais_codificadas(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='BASIC AUTH', client_id='u', secret='s')
        assert base64.b64decode(service.get_token()).decode() == 'u:s'

    def test_tipo_de_autenticacao_desconhecido_devolve_none(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        # Achado: um cadastro com tipo inválido não reclama — sai um token None que só
        # vai falhar depois, no cabeçalho 'Bearer None'.
        service = montar_service(APIExternaService, tipo_autenticacao='INEXISTENTE')
        assert service.get_token() is None


class TestClientCredentials:
    @pytest.mark.parametrize('chave', ['access_token', 'accessToken'])
    @patch('comum.services.api_externa.requests.post')
    def test_aceita_as_duas_grafias_do_token_na_resposta(
        self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict, chave: str
    ) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS')
        mock_post.return_value = _resposta(payload={chave: 'token-novo'})

        assert service.get_token() == 'token-novo'

    @patch('comum.services.api_externa.requests.post')
    def test_token_obtido_e_guardado_em_cache(self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS')
        mock_post.return_value = _resposta(payload={'access_token': 'token-novo'})

        service.get_token()

        assert cache_de_token[service.cache_name] == 'token-novo'

    @patch('comum.services.api_externa.requests.get')
    @patch('comum.services.api_externa.requests.post')
    def test_post_recusado_faz_o_servico_tentar_de_novo_por_get(
        self, mock_post: Mock, mock_get: Mock, montar_service: Callable[..., Any], cache_de_token: dict
    ) -> None:
        # Alguns servidores de autorização só respondem ao GET; o service tolera isso.
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS')
        mock_post.return_value = _resposta(ok=False)
        mock_get.return_value = _resposta(payload={'access_token': 'token-por-get'})

        assert service.get_token() == 'token-por-get'
        mock_get.assert_called_once()

    @patch('comum.services.api_externa.requests.post')
    def test_conecta_usa_o_fluxo_com_client_id_no_corpo(self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CONECTA', client_id='cli', secret='seg')
        mock_post.return_value = _resposta(payload={'access_token': 'token-conecta'})

        assert service.get_token() == 'token-conecta'
        assert mock_post.call_args.kwargs['auth'] == ('cli', 'seg')
        assert mock_post.call_args.kwargs['data']['client_id'] == 'cli'

    def test_sem_url_de_token_a_configuracao_e_recusada(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS', url_token=None)
        with pytest.raises(ValidationError, match='URL do servidor de autenticação não configurado'):
            service.get_token()

    @patch('comum.services.api_externa.requests.post')
    def test_resposta_sem_token_e_erro_explicito(self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS')
        mock_post.return_value = _resposta(payload={'erro': 'sem token aqui'})

        with pytest.raises(ValidationError, match='Token de acesso não encontrado na resposta'):
            service.get_token()

    @patch('comum.services.api_externa.requests.get')
    @patch('comum.services.api_externa.requests.post')
    def test_credenciais_recusadas_nas_duas_tentativas_viram_erro(
        self, mock_post: Mock, mock_get: Mock, montar_service: Callable[..., Any], cache_de_token: dict
    ) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='OAUTH2_CLIENT_CREDENTIALS')
        mock_post.return_value = _resposta(ok=False)
        mock_get.return_value = _resposta(ok=False)

        with pytest.raises(ValidationError, match='Verifique as credenciais fornecidas'):
            service.get_token()

    @pytest.mark.parametrize('tipo', ['OAUTH2_CLIENT_CREDENTIALS', 'CPF AUTH'])
    @patch('comum.services.api_externa.requests.post')
    def test_falha_de_rede_vira_validation_error_de_conexao(
        self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict, tipo: str
    ) -> None:
        """Falha de rede do ``requests`` sai como ``ValidationError``, o contrato dos demais ramos.

        ``requests.exceptions.ConnectionError`` não é subclasse do ``ConnectionError``
        embutido (são irmãos sob ``OSError``); o service captura ``RequestException``.
        """
        service = montar_service(APIExternaService, tipo_autenticacao=tipo)
        mock_post.side_effect = requests_lib.exceptions.ConnectionError('conexão recusada')

        with pytest.raises(ValidationError, match=r'Ocorreu um erro na conexão com o servidor de autenticação\. conexão recusada'):
            service.get_token()

    @pytest.mark.parametrize('tipo', ['OAUTH2_CLIENT_CREDENTIALS', 'CPF AUTH'])
    @patch('comum.services.api_externa.requests.post')
    def test_corpo_que_nao_e_json_nao_e_diagnosticado_como_falha_de_conexao(
        self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict, tipo: str
    ) -> None:
        # O JSONDecodeError do requests herda de RequestException: sem cláusula própria
        # antes, um corpo HTML viraria 'erro na conexão'.
        service = montar_service(APIExternaService, tipo_autenticacao=tipo)
        resposta = _resposta()
        resposta.json.side_effect = requests_lib.exceptions.JSONDecodeError('Expecting value', '<html>', 0)
        mock_post.return_value = resposta

        with pytest.raises(ValidationError, match='resposta que não é JSON válido'):
            service.get_token()


class TestCpfAuthToken:
    @pytest.mark.parametrize('chave', ['token', 'accessToken', 'access_token'])
    @patch('comum.services.api_externa.requests.post')
    def test_aceita_as_grafias_do_token_na_resposta(
        self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict, chave: str
    ) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CPF AUTH')
        mock_post.return_value = _resposta(payload={chave: 'token-cpf'})

        assert service.get_token() == 'token-cpf'
        assert mock_post.call_args.kwargs['json'] == {'cpf': 'cliente', 'password': 'segredo'}

    def test_sem_url_de_token_a_configuracao_e_recusada(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CPF AUTH', url_token='')
        with pytest.raises(ValidationError, match='URL do servidor de autenticação não configurado'):
            service.get_token()

    @patch('comum.services.api_externa.requests.post')
    def test_resposta_sem_token_mostra_o_corpo_recebido(self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CPF AUTH')
        mock_post.return_value = _resposta(payload={'detalhe': 'cpf desconhecido'})

        with pytest.raises(ValidationError, match='cpf desconhecido'):
            service.get_token()

    @patch('comum.services.api_externa.requests.post')
    def test_credenciais_recusadas_viram_erro(self, mock_post: Mock, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CPF AUTH')
        mock_post.return_value = _resposta(ok=False)

        with pytest.raises(ValidationError, match='Não foi possível obter o token de autenticação básica'):
            service.get_token()


class TestGetHeaders:
    def test_conecta_envia_o_cpf_do_operador_sem_pontuacao(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CONECTA', cpf_operador='123.456.789-01')
        service.cpf_operador = '123.456.789-01'
        cache_de_token[service.cache_name] = 'tk'

        headers = service.get_headers()

        assert headers['x-cpf-usuario'] == '12345678901'
        assert headers['authorization'] == 'Bearer tk'

    def test_cabecalhos_cadastrados_sao_preservados(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='CONECTA', headers={'X-Consumer-Id': 'IFRN'})
        cache_de_token[service.cache_name] = 'tk'

        assert service.get_headers()['X-Consumer-Id'] == 'IFRN'

    def test_nao_altera_os_cabecalhos_cadastrados_no_modelo(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        cadastrados = {'X-Consumer-Id': 'IFRN'}
        service = montar_service(APIExternaService, tipo_autenticacao='CONECTA', headers=cadastrados)
        cache_de_token[service.cache_name] = 'tk'

        service.get_headers()

        assert cadastrados == {'X-Consumer-Id': 'IFRN'}

    @pytest.mark.parametrize(
        ('tipo', 'cabecalho', 'valor'),
        [
            ('DATAPREV', 'Authorization', 'Bearer tk'),
            ('OAUTH2_CLIENT_CREDENTIALS', 'Authorization', 'Bearer tk'),
            ('CPF AUTH', 'Authorization', 'Bearer tk'),
            ('TOKEN_AUTH', 'Authentication', 'Token tk'),
            ('API KEY', 'X-API-KEY', 'tk'),
        ],
    )
    def test_cada_tipo_de_autenticacao_tem_seu_cabecalho(
        self, montar_service: Callable[..., Any], cache_de_token: dict, tipo: str, cabecalho: str, valor: str
    ) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao=tipo)
        cache_de_token[service.cache_name] = 'tk'

        assert service.get_headers()[cabecalho] == valor

    def test_autenticacao_basica_monta_o_cabecalho_sem_consultar_token(self, montar_service: Callable[..., Any], cache_de_token: dict) -> None:
        service = montar_service(APIExternaService, tipo_autenticacao='BASIC AUTH', client_id='u', secret='s')
        esperado = base64.b64encode(b'u:s').decode()

        assert service.get_headers()['Authorization'] == f'Basic {esperado}'


class TestEstahAcessivel:
    def test_service_base_obriga_a_subclasse_a_implementar(self, montar_service: Callable[..., Any]) -> None:
        with pytest.raises(NotImplementedError):
            montar_service(APIExternaService).estah_acessivel()
