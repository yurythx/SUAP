import logging

from requests.exceptions import JSONDecodeError, RequestException

from djtools.utils import requests

from .api_externa import APIExternaService

logger = logging.getLogger(__name__)


class ApiCEPService(APIExternaService):
    def __init__(self):
        from comum.models import APIExterna

        super().__init__(APIExterna.CEP)

    def consulta_cep(self, cep: str, verbosity: bool = False) -> tuple[bool, dict]:
        try:
            headers = self.get_headers(verbosity=verbosity)
            url = f'{self.api_externa.url_base}{self.api_externa.endpoint}{cep}'
            req = requests.get(url, headers=headers, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)
            req.raise_for_status()  # Levanta HTTPError para status de erro (4xx ou 5xx)
            return True, req.json()
        except JSONDecodeError as e:
            # Erro ao decodificar JSON; vem antes porque herda de RequestException
            msg = f'Erro ao decodificar resposta JSON da API de CEP: Detalhe: {e}'
            if verbosity:
                logger.info(msg)
            return False, {'erro': msg}
        except RequestException as e:
            # Erros de rede, timeout, ou status HTTP de erro
            msg = f'Erro de comunicação com a API de CEP: Detalhe: {e}'
            if verbosity:
                logger.info(msg)
            return False, {'erro': msg}
        except Exception as e:  # Captura outras exceções inesperadas
            msg = f'Erro inesperado ao consultar API de CEP: Detalhe: {e}'
            if verbosity:
                logger.info(msg)
            return False, {'erro': msg}

    def estah_acessivel(self, verbosity=False):
        return self.consulta_cep('59300000', verbosity=verbosity)[0]
