import base64

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from requests.exceptions import JSONDecodeError, RequestException

from djtools.utils import requests


class APIExternaService:
    def __init__(self, api_externa):
        self.api_externa = api_externa
        self.cache_name = f'TOKEN_API_EXTERNA_{self.api_externa.nome.lower()}'
        self.timeout = self.get_timeout()
        self.cpf_operador = self.api_externa.cpf_operador

    def get_token(self, verbosity=False):
        if cache.get(self.cache_name):
            return cache.get(self.cache_name)
        elif self.api_externa.tipo_autenticacao in [
            self.api_externa.CONECTA_AUTH,
            self.api_externa.CLIENT_CREDENTIALS_AUTH,
        ]:
            return self.get_auth_token_client_credentials(verbosity=verbosity)
        elif self.api_externa.tipo_autenticacao == self.api_externa.CPF_AUTH:
            return self.cpf_auth_token(verbosity=verbosity)
        elif self.api_externa.tipo_autenticacao == self.api_externa.BASIC_AUTH:
            return self.basic_auth_token()
        elif self.api_externa.tipo_autenticacao in [
            self.api_externa.TOKEN_AUTH,
            self.api_externa.API_KEY_AUTH,
        ]:
            return self.api_externa.secret

    def set_token(self, token):
        cache.set(self.cache_name, token, 3600)  # Armazena o token na cache por 1 hora

    def basic_auth_token(self):
        credentials = f'{self.api_externa.client_id}:{self.api_externa.secret}'
        token = base64.b64encode(credentials.encode()).decode('utf-8')
        return token

    def get_auth_token_client_credentials(self, verbosity: bool = False) -> str:
        """
        Função para obter token utilizando "oauth2 client_credentials" para APIS gerenciadas pelo Conecta GovBR: https://www.gov.br/conecta/catalogo/, DATAPREV ou SERPRO
        """
        grant_type = 'client_credentials'
        try:
            if self.api_externa.url_token is None:
                raise ValidationError('URL do servidor de autenticação não configurado.')
            if self.api_externa.tipo_autenticacao in [
                self.api_externa.CLIENT_CREDENTIALS_AUTH,
                self.api_externa.DATAPREV_AUTH,
            ]:
                data = {'grant_type': 'client_credentials'}
                headers = {'Authorization': f'Basic {self.basic_auth_token()}'}
                response = requests.post(
                    self.api_externa.url_token,
                    data=data,
                    headers=headers,
                    timeout=self.timeout,
                    verbosity=verbosity,
                    API=f'{self.api_externa.nome} - OAuth Token',
                )
                if not response.ok:
                    response = requests.get(
                        self.api_externa.url_token,
                        data=data,
                        headers=headers,
                        timeout=self.timeout,
                        verbosity=verbosity,
                        API=f'{self.api_externa.nome} - OAuth Token',
                    )
            else:
                url = self.api_externa.url_token
                data = {'grant_type': grant_type, 'client_id': self.api_externa.client_id, 'client_secret': self.api_externa.secret}
                headers = {}
                response = requests.post(
                    url,
                    auth=(self.api_externa.client_id, self.api_externa.secret),
                    data=data,
                    headers=headers,
                    timeout=self.timeout,
                    verbosity=verbosity,
                    API=f'{self.api_externa.nome} - OAuth Token',
                )
            if response.ok:
                data = response.json()
                token = data.get('access_token') or data.get('accessToken')
                if not token:
                    raise ValidationError('Token de acesso não encontrado na resposta do servidor de autenticação.')
                self.set_token(token)
                return token
            else:
                raise ValidationError('Não foi possível obter o token de autenticação oauth. Verifique as credenciais fornecidas.')
        except JSONDecodeError as e:
            # Vem antes: o JSONDecodeError do requests herda de RequestException.
            raise ValidationError(f'O servidor de autenticação devolveu uma resposta que não é JSON válido. {e}')
        except RequestException as e:
            raise ValidationError(f'Ocorreu um erro na conexão com o servidor de autenticação. {e}')

    def cpf_auth_token(self, verbosity: bool = False) -> str:
        """
        Função para obter token para APIS que utilizam Autenticação Básica (Usuário e Senha)
        """
        try:
            url = self.api_externa.url_token
            if not url:
                raise ValidationError('URL do servidor de autenticação não configurado.')
            data = {'cpf': f'{self.api_externa.client_id}', 'password': f'{self.api_externa.secret}'}
            response = requests.post(url, json=data, timeout=self.timeout, verbosity=verbosity, API=f'{self.api_externa.nome} - CPF Auth Token')
            if response.ok:
                data = response.json()
                token = data.get('token') or data.get('accessToken') or data.get('access_token')
                if not token:
                    raise ValidationError('Token de acesso não encontrado na resposta do servidor de autenticação. Detalhes: ' + str(data))
                self.set_token(token)
                return token
            else:
                raise ValidationError('Não foi possível obter o token de autenticação básica. Verifique as credenciais fornecidas.')
        except JSONDecodeError as e:
            # Vem antes: o JSONDecodeError do requests herda de RequestException.
            raise ValidationError(f'O servidor de autenticação devolveu uma resposta que não é JSON válido. {e}')
        except RequestException as e:
            raise ValidationError(f'Ocorreu um erro na conexão com o servidor de autenticação. {e}')

    def get_headers(self, cpf_operador: str | None = None, verbosity: bool = False) -> dict[str, object]:
        headers = dict(self.api_externa.headers or {})

        if self.api_externa.tipo_autenticacao == self.api_externa.CONECTA_AUTH:
            cpf_operador = cpf_operador or self.cpf_operador
            headers.update(
                {'x-cpf-usuario': cpf_operador.replace('.', '').replace('-', ''), 'authorization': f'Bearer {self.get_token(verbosity=verbosity)}'}
            )
        elif self.api_externa.tipo_autenticacao in [
            self.api_externa.DATAPREV_AUTH,
            self.api_externa.CLIENT_CREDENTIALS_AUTH,
            self.api_externa.CPF_AUTH,
        ]:
            headers.update({'Authorization': f'Bearer {self.get_token(verbosity=verbosity)}'})
        elif self.api_externa.tipo_autenticacao == self.api_externa.TOKEN_AUTH:
            headers.update({'Authentication': f'Token {self.get_token(verbosity=verbosity)}'})
        elif self.api_externa.tipo_autenticacao == self.api_externa.API_KEY_AUTH:
            headers.update({'X-API-KEY': f'{self.get_token(verbosity=verbosity)}'})
        elif self.api_externa.tipo_autenticacao == self.api_externa.BASIC_AUTH:
            headers.update({'Authorization': f'Basic {self.basic_auth_token()}'})
        return headers

    def get_timeout(self):
        return settings.REQUESTS_TIMEOUT

    def estah_acessivel(self, verbosity=False):
        raise NotImplementedError('Subclasses must implement this method')
