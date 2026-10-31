import logging
from typing import Any

from django.core.exceptions import ValidationError
from requests.exceptions import RequestException

from djtools.utils import requests

from .api_externa import APIExternaService

logger = logging.getLogger(__name__)


class ApiPCDService(APIExternaService):
    def __init__(self):
        from comum.models import APIExterna

        super().__init__(APIExterna.PESSOACOMDEFICIENCIA)

    def get_dados_pessoais(self, cpf: str, verbosity: bool = False) -> tuple[bool, Any]:
        try:
            url = self.api_externa.url_base
            url += f'{self.api_externa.endpoint}{cpf}'
            headers = self.get_headers(verbosity=verbosity)
            req = requests.get(url, headers=headers, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)
            if req.ok:
                return True, req.json() if req.content else None
            logger.warning(f'API {self.api_externa.nome} recusou a consulta (HTTP {req.status_code}).')
            return False, [req.content]
        except (RequestException, ValidationError) as e:
            # RequestException cobre rede, timeout e o JSONDecodeError do requests; ValidationError vem do token (get_headers).
            logger.warning(f'API {self.api_externa.nome} não está acessível: {e}')
            return False, []

    def estah_acessivel(self, verbosity: bool = False) -> bool:
        return self.get_dados_pessoais(self.cpf_operador, verbosity=verbosity)[0]
