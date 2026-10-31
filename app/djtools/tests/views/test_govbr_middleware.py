from datetime import date
from unittest.mock import Mock, patch

import pytest

from django.test import RequestFactory

from djtools.middleware.govbr import destino_pos_autenticacao, user_confiability_level


def _request_com_cookie(valor=None):
    request = RequestFactory().get('/accounts/login/')
    if valor is not None:
        request.COOKIES['auth_redirect_url'] = valor
    return request


def test_destino_pos_autenticacao_preserva_a_url_de_origem():
    url = '/o/authorize/?response_type=code&client_id=ABC&redirect_uri=https://ava.ifrn.edu.br/authenticate/'

    assert destino_pos_autenticacao(_request_com_cookie(url)) == url


def test_destino_pos_autenticacao_sem_cookie_vai_para_a_raiz():
    assert destino_pos_autenticacao(_request_com_cookie()) == '/'


def test_destino_pos_autenticacao_recusa_redirecionamento_para_outro_host():
    assert destino_pos_autenticacao(_request_com_cookie('https://exemplo.invalido/phishing/')) == '/'


@patch('djtools.middleware.govbr.requests.get')
def test_returns_zero_when_response_json_is_invalid(mock_get, settings):
    settings.GOVBR = {'API_URL': 'https://api.gov.br'}
    settings.REQUESTS_TIMEOUT = 13
    mock_response = Mock(status_code=200, text='')
    mock_response.json.side_effect = ValueError('Invalid JSON')
    mock_get.return_value = mock_response

    level = user_confiability_level('12345678900', 'token-abc')

    assert level == '0'
    mock_get.assert_called_once_with(
        'https://api.gov.br/confiabilidades/v3/contas/12345678900/niveis?response-type=ids',
        headers={'Authorization': 'Bearer token-abc'},
        timeout=13,
    )


@patch('djtools.middleware.govbr.requests.get')
def test_returns_highest_level_when_response_is_valid(mock_get, settings):
    settings.GOVBR = {'API_URL': 'https://api.gov.br'}
    settings.REQUESTS_TIMEOUT = 13
    mock_response = Mock()
    mock_response.json.return_value = [{'id': '1'}, {'id': '3'}, {'id': '2'}]
    mock_get.return_value = mock_response

    level = user_confiability_level('12345678900', 'token-abc')

    assert level == '3'


@patch('djtools.middleware.govbr.requests.get')
def test_returns_zero_when_payload_shape_is_unexpected(mock_get, settings):
    settings.GOVBR = {'API_URL': 'https://api.gov.br'}
    settings.REQUESTS_TIMEOUT = 13
    mock_response = Mock()
    mock_response.json.return_value = {'foo': 'bar'}
    mock_get.return_value = mock_response

    level = user_confiability_level('12345678900', 'token-abc')

    assert level == '0'


@pytest.mark.django_db
def test_update_user_nao_apaga_dados_civis_com_vazios_do_governo() -> None:
    from comum.models import APIExterna, PessoaFisica
    from comum.tests.factories import PrestadorServicoFactory
    from djtools.middleware.govbr import Middleware

    prestador = PrestadorServicoFactory(
        matricula='52998224725',
        pessoa_fisica__cpf='529.982.247-25',
        pessoa_fisica__nome_mae='Maria',
        pessoa_fisica__nome_pai='José',
        pessoa_fisica__sexo='F',
        pessoa_fisica__nascimento_data=date(1990, 1, 1),
    )
    # fronteira externa: os dados pessoais consultados na API do governo
    dados_governo = [{'Nome': 'ANA SOUZA', 'NomeMae': '', 'NomePai': None, 'Sexo': 3, 'DataNascimento': 'invalida', 'UF': 'RN', 'Municipio': 'NATAL'}]
    with (
        patch.object(APIExterna, 'PESSOAFISICA', Mock()),
        patch('djtools.middleware.govbr.PessoaInfoComplementar.get_instance', return_value=Mock(informacoes=dados_governo)),
    ):
        Middleware(Mock()).update_user(prestador.get_user(), {'photo': None})

    pessoa = PessoaFisica.objects.get(pk=prestador.pessoa_fisica_id)
    assert (pessoa.nome_mae, pessoa.nome_pai, pessoa.sexo, pessoa.nascimento_data) == ('Maria', 'José', 'F', date(1990, 1, 1))
    assert pessoa.nome_registro == 'ANA SOUZA'
