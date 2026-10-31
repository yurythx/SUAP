import logging
import re
from datetime import datetime, timedelta
from typing import Any

from django.core.exceptions import ValidationError
from requests.exceptions import RequestException

from djtools.utils import requests

from .api_externa import APIExternaService

logger = logging.getLogger(__name__)


def _mensagens_de_erro(resultado: Any) -> list[str]:
    """Mensagens dos itens de erro da API: a falha vem como ``[{"CPF": ..., "mensagem": ...}]``, sem os dados."""
    if not isinstance(resultado, list):
        return []
    return [str(item['mensagem']) for item in resultado if isinstance(item, dict) and 'mensagem' in item and 'Nome' not in item]


class ApiPessoaFisicaService(APIExternaService):
    def __init__(self):
        from comum.models import APIExterna

        super().__init__(APIExterna.PESSOAFISICA)

    def get_data_expiracao(self):
        return datetime.now() + timedelta(days=self.api_externa.dias_para_expirar)

    def get_dados_pessoais(self, cpf: str | int, verbosity: bool = False) -> tuple[bool, list]:
        cpf = re.sub(r'\D', '', str(cpf))

        json_cpf = {'listaCpf': [cpf]}

        url = f'{self.api_externa.url_base}{self.api_externa.endpoint}'

        try:
            headers = self.get_headers(verbosity=verbosity)  # levanta ValidationError se não obtiver o token
            response = requests.post(url, headers=headers, json=json_cpf, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)
        except (RequestException, ValidationError) as e:
            logger.warning(f'Falha ao consultar API {self.api_externa.nome} para o CPF informado: {e}')
            return False, [str(e)]

        try:
            resultado = response.json()
        except RequestException:  # JSONDecodeError do requests herda de RequestException
            resultado = None

        mensagens = _mensagens_de_erro(resultado)
        if response.ok and isinstance(resultado, list) and not mensagens:
            return True, resultado

        # Decide pela chave ``mensagem`` do JSON, não por substring do corpo: um dado pode conter a palavra.
        erro = mensagens or [response.text]
        logger.warning(f'API {self.api_externa.nome} recusou a consulta (HTTP {response.status_code}): {erro[0][:200]}')
        return False, erro

    def estah_acessivel(self, verbosity=False):
        try:
            return self.get_dados_pessoais('11111111111', verbosity=verbosity)[0]
        except Exception:
            return False
