"""Consulta da API de Pessoa Física (``comum/services/pessoa_fisica.py``).

O service normaliza o CPF, consulta em lote (``listaCpf``) e decide sucesso pela chave
``mensagem`` nos itens do JSON devolvido, não por substring do corpo (#17413). Payload medido
(dados fictícios aqui): sucesso é uma lista de dicts com os dados (``CPF``, ``Nome``, ...);
falha é ``[{"CPF": "...", "mensagem": "CPF Inválido."}]``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from requests import Response
from requests.exceptions import ConnectionError as RequestsConnectionError

from comum.services.pessoa_fisica import ApiPessoaFisicaService


@pytest.fixture
def service_pf(montar_service: Callable[..., Any]) -> Any:
    service = montar_service(
        ApiPessoaFisicaService,
        tipo_autenticacao='DATAPREV',
        endpoint='/v1/pessoas',
        url_base='https://api.exemplo.gov.br',
        dias_para_expirar=30,
    )
    service.get_token = Mock(return_value='token-falso')
    return service


def _resposta(texto: str = '[]', status_code: int = 200) -> Response:
    resposta = Response()
    resposta.status_code = status_code
    resposta._content = texto.encode()
    resposta.encoding = 'utf-8'
    return resposta


class TestGetDataExpiracao:
    def test_projeta_a_expiracao_pelos_dias_cadastrados(self, service_pf: Any) -> None:
        esperado = datetime.now() + timedelta(days=30)
        assert abs((service_pf.get_data_expiracao() - esperado).total_seconds()) < 5


class TestGetDadosPessoais:
    @pytest.mark.parametrize('cpf', ['123.456.789-01', '12345678901', 12345678901])
    @patch('comum.services.pessoa_fisica.requests.post')
    def test_normaliza_o_cpf_antes_de_consultar(self, mock_post: Mock, service_pf: Any, cpf: str | int) -> None:
        mock_post.return_value = _resposta('[{"CPF": "12345678901", "Nome": "ADA LOVELACE"}]')

        sucesso, dados = service_pf.get_dados_pessoais(cpf)

        assert sucesso
        assert dados == [{'CPF': '12345678901', 'Nome': 'ADA LOVELACE'}]
        assert mock_post.call_args.kwargs['json'] == {'listaCpf': ['12345678901']}

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_status_de_erro_devolve_o_corpo_como_texto(self, mock_post: Mock, service_pf: Any) -> None:
        mock_post.return_value = _resposta('Unauthorized', status_code=401)

        assert service_pf.get_dados_pessoais('12345678901') == (False, ['Unauthorized'])

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_falha_de_rede_vira_par_negativo_com_o_motivo(self, mock_post: Mock, service_pf: Any) -> None:
        # Diferente do pcd.py, aqui o motivo chega ao chamador.
        mock_post.side_effect = RequestsConnectionError('conexão recusada')

        sucesso, dados = service_pf.get_dados_pessoais('12345678901')

        assert not sucesso
        assert 'conexão recusada' in dados[0]

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_falha_ao_obter_o_token_vira_par_negativo_logado(self, mock_post: Mock, service_pf: Any, caplog: pytest.LogCaptureFixture) -> None:
        service_pf.get_token.side_effect = ValidationError('credenciais recusadas')

        with caplog.at_level('WARNING', logger='comum.services.pessoa_fisica'):
            sucesso, dados = service_pf.get_dados_pessoais('12345678901')

        assert not sucesso
        assert 'credenciais recusadas' in dados[0]
        assert 'credenciais recusadas' in caplog.text
        mock_post.assert_not_called()

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_a_palavra_mensagem_num_campo_de_dado_nao_reprova_a_resposta(self, mock_post: Mock, service_pf: Any) -> None:
        corpo = '[{"CPF": "12345678901", "Nome": "ADA LOVELACE", "Complemento": "sala da mensagem 12"}]'
        mock_post.return_value = _resposta(corpo)

        sucesso, dados = service_pf.get_dados_pessoais('12345678901')

        assert sucesso
        assert dados[0]['Complemento'] == 'sala da mensagem 12'

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_item_com_a_chave_mensagem_devolve_a_mensagem_legivel(self, mock_post: Mock, service_pf: Any, caplog: pytest.LogCaptureFixture) -> None:
        mock_post.return_value = _resposta('[{"CPF": "12345678901", "mensagem": "CPF Inválido."}]')

        with caplog.at_level('WARNING', logger='comum.services.pessoa_fisica'):
            assert service_pf.get_dados_pessoais('12345678901') == (False, ['CPF Inválido.'])

        assert 'CPF Inválido.' in caplog.text

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_corpo_que_nao_e_json_vira_falha_sem_excecao(self, mock_post: Mock, service_pf: Any) -> None:
        mock_post.return_value = _resposta('<html>manutenção</html>')

        assert service_pf.get_dados_pessoais('12345678901') == (False, ['<html>manutenção</html>'])


class TestEstahAcessivel:
    @patch('comum.services.pessoa_fisica.requests.post')
    def test_sonda_a_api_com_um_cpf_sentinela(self, mock_post: Mock, service_pf: Any) -> None:
        mock_post.return_value = _resposta('[]')

        assert service_pf.estah_acessivel() is True
        assert mock_post.call_args.kwargs['json'] == {'listaCpf': ['11111111111']}

    @patch('comum.services.pessoa_fisica.requests.post')
    def test_api_fora_do_ar_e_reportada_como_inacessivel(self, mock_post: Mock, service_pf: Any) -> None:
        mock_post.side_effect = RequestsConnectionError('conexão recusada')

        assert service_pf.estah_acessivel() is False
