import base64
import logging
from datetime import datetime, timedelta

from jwcrypto import jwk, jwt

from djtools.utils import requests

from .api_externa import APIExternaService

logger = logging.getLogger(__name__)


class ApiICPEDUService(APIExternaService):
    def __init__(self):
        from comum.models import APIExterna

        self.signer = None
        self.signer_email: str = ''
        super().__init__(APIExterna.ICPEDU)

    def set_signer(self, signer, email: str = '') -> None:
        self.signer = signer
        self.signer_email = email

    def get_payload(self) -> dict:
        iss = self.api_externa.headers.get('ISS')
        if not iss:
            raise Exception('ISS não definido nos headers da API Externa')
        if not self.signer:
            raise Exception('Signer não definido')
        if not self.signer.cpf:
            raise Exception('CPF do signer não definido')
        if not self.signer.nascimento_data:
            raise Exception('Data de nascimento do signer não definida')
        if not self.signer_email:
            raise Exception('Email do signer não definido')
        if not self.signer.nome:
            raise Exception('Nome do signer não definido')
        return {
            'iss': iss,
            'exp': (datetime.now() + timedelta(seconds=30)).timestamp(),
            'name': self.signer.nome,
            'email': self.signer_email,
            'birthdate': self.signer.nascimento_data.isoformat(),
            'cpf': self.signer.cpf,
            'sub': self.signer.cpf,
            'chosen_name': self.signer.nome_social or self.signer.nome,
            'iat': (datetime.now() + timedelta(seconds=-30)).timestamp(),
        }

    def get_token(self, verbosity=False):
        private_key = self.api_externa.secret
        key = jwk.JWK.from_json(private_key)
        header = {'alg': 'RS256', 'kid': 'suap'}
        payload = self.get_payload()
        logger.info(f'Header: {header}')
        logger.info(f'Payload: {payload}')
        token = jwt.JWT(header=header, claims=payload, algs=['RS256'])
        token.make_signed_token(key)
        access_token = token.serialize()
        return access_token

    def sign_hash(self, hash, verbosity=False):
        headers = self.get_headers()
        url = f'{self.api_externa.url_base}/api/signer/pdf/1/sign/hash/sha256/{hash}'
        content = requests.post(
            url,
            headers=headers,
            timeout=self.get_timeout(),
            verbosity=verbosity,
            API=self.api_externa.nome,
        ).content
        text = content.decode()
        if text.startswith('-----BEGIN PKCS7-----') and text.endswith('-----END PKCS7-----\n'):
            signature = base64.b64decode(
                text.replace('-----BEGIN PKCS7-----\n', '').replace('\n-----END PKCS7-----\n', '').replace('\n', '').strip()
            ).hex()
            if verbosity:
                logger.info(f'Signature obtida da API de ICPEDU: {signature}')
            return signature
        else:
            msg = f'Resposta inesperada da API de ICPEDU: {text}'
            if verbosity:
                logger.info(msg)
            return False

    def estah_acessivel(self, verbosity=False):
        usuario = self.api_externa.usuario_responsavel
        if not usuario:
            logger.error(f'Usuário responsável não configurado para API Externa "{self.api_externa.nome}"')
            return False

        v = usuario.get_vinculo()
        self.set_signer(usuario.get_profile(), email=v.email_notificacao if v else '')
        try:
            return bool(self.sign_hash('ccf9fd6a61701aa3f85c8888254d6b4689249630226b5567cdd3fea8c627cb4a', verbosity=verbosity))
        except Exception as e:
            msg = f'Erro inesperado ao verificar acessibilidade da API de ICPEDU: Detalhe: {e}'
            if verbosity:
                logger.info(msg)
            return False
