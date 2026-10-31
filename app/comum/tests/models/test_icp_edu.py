"""Assinatura digital via ICP-EDU (``comum/services/icp_edu.py``).

O service monta um JWT com os dados do signatário, assina com a chave privada cadastrada
e envia o hash do PDF para o servidor de assinatura. O que importa testar é: quais dados
do signatário são exigidos, o que entra no token e como uma resposta fora do formato
PKCS7 é tratada.

A chave RSA é gerada em memória — não há chave de verdade em teste, e a geração é a única
operação cara aqui, por isso fica em fixture de módulo.
"""

from __future__ import annotations

import base64
import datetime
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from jwcrypto import jwk, jwt

from comum.services.icp_edu import ApiICPEDUService

PKCS7 = 'assinatura-em-pkcs7'


@pytest.fixture(scope='module')
def chave_rsa() -> str:
    return jwk.JWK.generate(kty='RSA', size=2048).export_private()


@pytest.fixture
def signatario() -> SimpleNamespace:
    return SimpleNamespace(
        nome='Ada Lovelace',
        nome_social='',
        cpf='123.456.789-01',
        nascimento_data=datetime.date(1815, 12, 10),
    )


@pytest.fixture
def service_icp(montar_service: Callable[..., Any], chave_rsa: str, signatario: SimpleNamespace) -> Any:
    service = montar_service(
        ApiICPEDUService,
        tipo_autenticacao='TOKEN_AUTH',
        url_base='https://icpedu.exemplo.gov.br',
        secret=chave_rsa,
        headers={'ISS': 'suap-ifrn'},
    )
    service.signer = None
    service.signer_email = ''
    service.set_signer(signatario, email='ada@ifrn.edu.br')
    return service


def _corpo_pkcs7(conteudo: str = PKCS7) -> bytes:
    codificado = base64.b64encode(conteudo.encode()).decode()
    return f'-----BEGIN PKCS7-----\n{codificado}\n-----END PKCS7-----\n'.encode()


class TestGetPayload:
    def test_reune_os_dados_do_signatario_no_token(self, service_icp: Any) -> None:
        payload = service_icp.get_payload()

        assert payload['iss'] == 'suap-ifrn'
        assert payload['name'] == 'Ada Lovelace'
        assert payload['email'] == 'ada@ifrn.edu.br'
        assert payload['cpf'] == payload['sub'] == '123.456.789-01'
        assert payload['birthdate'] == '1815-12-10'

    def test_nome_social_prevalece_como_nome_escolhido(self, service_icp: Any, signatario: SimpleNamespace) -> None:
        signatario.nome_social = 'Ada Byron'
        assert service_icp.get_payload()['chosen_name'] == 'Ada Byron'

    def test_sem_nome_social_o_nome_de_registro_e_o_escolhido(self, service_icp: Any) -> None:
        assert service_icp.get_payload()['chosen_name'] == 'Ada Lovelace'

    def test_token_vale_por_trinta_segundos(self, service_icp: Any) -> None:
        payload = service_icp.get_payload()
        assert 0 < payload['exp'] - datetime.datetime.now().timestamp() <= 30
        assert payload['iat'] < datetime.datetime.now().timestamp()

    @pytest.mark.parametrize(
        ('campo', 'mensagem'),
        [
            ('cpf', 'CPF do signer não definido'),
            ('nascimento_data', 'Data de nascimento do signer não definida'),
            ('nome', 'Nome do signer não definido'),
        ],
    )
    def test_cada_dado_faltante_do_signatario_e_recusado_por_nome(
        self, service_icp: Any, signatario: SimpleNamespace, campo: str, mensagem: str
    ) -> None:
        setattr(signatario, campo, None)
        with pytest.raises(Exception, match=mensagem):
            service_icp.get_payload()

    def test_sem_iss_cadastrado_a_configuracao_e_recusada(self, service_icp: Any) -> None:
        service_icp.api_externa.headers = {}
        with pytest.raises(Exception, match='ISS não definido nos headers da API Externa'):
            service_icp.get_payload()

    def test_sem_signatario_definido_a_chamada_e_recusada(self, service_icp: Any) -> None:
        service_icp.set_signer(None)
        with pytest.raises(Exception, match='Signer não definido'):
            service_icp.get_payload()

    def test_sem_email_do_signatario_a_chamada_e_recusada(self, service_icp: Any, signatario: SimpleNamespace) -> None:
        service_icp.set_signer(signatario, email='')
        with pytest.raises(Exception, match='Email do signer não definido'):
            service_icp.get_payload()


class TestGetToken:
    def test_emite_jwt_assinado_verificavel_pela_chave_cadastrada(self, service_icp: Any, chave_rsa: str) -> None:
        token = service_icp.get_token()

        verificado = jwt.JWT(key=jwk.JWK.from_json(chave_rsa), jwt=token)
        assert '"cpf":"123.456.789-01"' in verificado.claims.replace(' ', '')
        assert jwt.JWT(jwt=token).token.jose_header == {'alg': 'RS256', 'kid': 'suap'}


class TestSignHash:
    @patch('comum.services.icp_edu.requests.post')
    def test_resposta_em_pkcs7_vira_assinatura_hexadecimal(self, mock_post: Mock, service_icp: Any) -> None:
        mock_post.return_value = Mock(content=_corpo_pkcs7())

        assinatura = service_icp.sign_hash('abc123')

        assert assinatura == PKCS7.encode().hex()
        assert mock_post.call_args.args[0].endswith('/api/signer/pdf/1/sign/hash/sha256/abc123')

    @patch('comum.services.icp_edu.requests.post')
    def test_resposta_fora_do_formato_devolve_false(self, mock_post: Mock, service_icp: Any) -> None:
        # Achado: o retorno é ``False``, não uma exceção — quem chama precisa lembrar de
        # testar o valor, já que o motivo só aparece em log sob ``verbosity``.
        mock_post.return_value = Mock(content=b'<html>Servico indisponivel</html>')

        assert service_icp.sign_hash('abc123') is False

    @patch('comum.services.icp_edu.requests.post')
    def test_com_verbosity_a_resposta_inesperada_vai_para_o_log(self, mock_post: Mock, service_icp: Any, caplog: pytest.LogCaptureFixture) -> None:
        mock_post.return_value = Mock(content=b'<html>Servico indisponivel</html>')

        with caplog.at_level('INFO', logger='comum.services.icp_edu'):
            service_icp.sign_hash('abc123', verbosity=True)

        assert 'Resposta inesperada da API de ICPEDU' in caplog.text


class TestEstahAcessivel:
    @patch('comum.services.icp_edu.requests.post')
    def test_assina_um_hash_sentinela_com_o_usuario_responsavel(self, mock_post: Mock, service_icp: Any, signatario: SimpleNamespace) -> None:
        mock_post.return_value = Mock(content=_corpo_pkcs7())
        service_icp.api_externa.usuario_responsavel = Mock(
            **{'get_vinculo.return_value': SimpleNamespace(email_notificacao='ada@ifrn.edu.br'), 'get_profile.return_value': signatario}
        )

        assert service_icp.estah_acessivel() is True

    def test_sem_usuario_responsavel_a_api_e_dada_como_inacessivel(self, service_icp: Any, caplog: pytest.LogCaptureFixture) -> None:
        service_icp.api_externa.usuario_responsavel = None

        with caplog.at_level('ERROR', logger='comum.services.icp_edu'):
            assert service_icp.estah_acessivel() is False

        assert 'Usuário responsável não configurado' in caplog.text

    @patch('comum.services.icp_edu.requests.post')
    def test_falha_na_assinatura_e_reportada_como_inacessivel(self, mock_post: Mock, service_icp: Any, signatario: SimpleNamespace) -> None:
        mock_post.side_effect = RuntimeError('servidor fora do ar')
        service_icp.api_externa.usuario_responsavel = Mock(**{'get_vinculo.return_value': None, 'get_profile.return_value': signatario})

        assert service_icp.estah_acessivel() is False
