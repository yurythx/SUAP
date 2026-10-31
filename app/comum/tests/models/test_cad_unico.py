from types import SimpleNamespace
from unittest.mock import Mock, patch

from requests.exceptions import Timeout

from comum.services.cad_unico import ApiCadUnicoService


import pytest


@pytest.fixture
def cad_unico_service():
    service = ApiCadUnicoService.__new__(ApiCadUnicoService)
    service.api_externa = SimpleNamespace(
        CONECTA_AUTH='CONECTA',
        DATAPREV_AUTH='DATAPREV',
        CLIENT_CREDENTIALS_AUTH='OAUTH2_CLIENT_CREDENTIALS',
        CPF_AUTH='CPF AUTH',
        TOKEN_AUTH='TOKEN_AUTH',
        API_KEY_AUTH='API KEY',
        BASIC_AUTH='BASIC AUTH',
        ativo=False,
        cpf_operador='12345678901',
        endpoint='/v1/dp/dadosFamiliar/{cpf}',
        headers={
            'X-Consumer-Id': 'Instituicao',
            'X-Consumer-Id-Type': 'Sigla',
            'X-Authorization-Id': 'AuthorizationID',
            'X-Authorization-Id-Type': 'Processo',
            'X-Subject-Id-Type': 'CPF',
        },
        nome='CADUNICO',
        tipo_autenticacao='CONECTA',
        url_base='https://apigateway.conectagov.estaleiro.serpro.gov.br/api-cadunico-servicos-dados',
    )
    service.cpf_operador = service.api_externa.cpf_operador
    service.get_token = Mock(return_value='fake-token')
    service.timeout = 30
    return service


class TestApiCadUnicoService:
    @patch('comum.services.cad_unico.requests.get')
    def test_get_dados_pessoais_sucesso_com_json_valido(self, mock_get, cad_unico_service):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json.return_value = {'nome': 'Teste', 'cpf': '12345678901'}
        mock_get.return_value = mock_response

        sucesso, resposta = cad_unico_service.get_dados_pessoais('123.456.789-01')

        assert sucesso
        assert resposta == {'nome': 'Teste', 'cpf': '12345678901'}
        mock_get.assert_called_once()
        assert mock_get.call_args.kwargs['headers']['authorization'] == 'Bearer fake-token'

    @patch('comum.services.cad_unico.requests.get')
    def test_get_dados_pessoais_resposta_vazia(self, mock_get, cad_unico_service):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json.return_value = {}
        mock_response.content = b''
        mock_response.text = ''
        mock_get.return_value = mock_response

        sucesso, resposta = cad_unico_service.get_dados_pessoais('123.456.789-01')

        assert sucesso
        assert resposta == {}

    @patch('comum.services.cad_unico.requests.get')
    def test_get_dados_pessoais_content_type_html(self, mock_get, cad_unico_service):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.text = '<!DOCTYPE html><html>Erro</html>'
        mock_get.return_value = mock_response

        sucesso, resposta = cad_unico_service.get_dados_pessoais('123.456.789-01')

        assert not sucesso
        assert 'Content-Type' in resposta
        assert 'text/html' in resposta

    @pytest.mark.parametrize(
        ('status_code', 'content'),
        [
            (500, b'Internal Server Error'),
            (401, b'Unauthorized'),
        ],
    )
    @patch('comum.services.cad_unico.requests.get')
    def test_get_dados_pessoais_erro_http(self, mock_get, status_code, content, cad_unico_service):
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = status_code
        mock_response.content = content
        mock_get.return_value = mock_response

        sucesso, resposta = cad_unico_service.get_dados_pessoais('123.456.789-01')

        assert not sucesso
        assert str(status_code) in resposta


class TestEstahAcessivelCadUnico:
    @patch('comum.services.cad_unico.requests.get')
    def test_sonda_a_api_com_o_cpf_do_operador(self, mock_get, cad_unico_service):
        mock_response = Mock()
        mock_response.ok = True
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        assert cad_unico_service.estah_acessivel() is True
        assert mock_get.call_args.args[0].endswith(cad_unico_service.cpf_operador)

    @patch('comum.services.cad_unico.requests.get')
    def test_api_fora_do_ar_e_reportada_como_inacessivel(self, mock_get, cad_unico_service):
        # `get_dados_pessoais` não trata exceção: quem contém a falha é o `estah_acessivel`.
        mock_get.side_effect = Timeout('tempo esgotado')

        assert cad_unico_service.estah_acessivel() is False

    @patch('comum.services.cad_unico.requests.get')
    def test_com_verbosity_o_motivo_da_indisponibilidade_vai_para_o_log(self, mock_get, cad_unico_service, caplog):
        mock_get.side_effect = Timeout('tempo esgotado')

        with caplog.at_level('INFO', logger='comum.services.cad_unico'):
            cad_unico_service.estah_acessivel(verbosity=True)

        assert 'API CADÚnico não está acessível' in caplog.text
