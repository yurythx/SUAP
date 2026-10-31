import logging

from djtools.utils import requests

from .api_externa import APIExternaService

logger = logging.getLogger(__name__)


class ApiCadUnicoService(APIExternaService):
    def __init__(self):
        from comum.models import APIExterna

        super().__init__(APIExterna.CADUNICO)

    def get_dados_pessoais(self, cpf, verbosity=False):
        headers = self.get_headers(verbosity=verbosity)
        cpf = cpf.replace('.', '').replace('-', '')
        url = self.api_externa.url_base + self.api_externa.endpoint.replace('{cpf}', cpf)
        req = requests.get(url, headers=headers, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)
        if req.ok:
            content_type = req.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return True, req.json()
            return False, f'Resposta inválida da API CADÚnico (Content-Type: {content_type}). Detalhes: {req.text[:500]}'
        else:
            return False, f'Erro ao obter informações do CADÚnico (HTTP {req.status_code}). Detalhes: {req.content[:500]}'

    def estah_acessivel(self, verbosity=False):
        try:
            return self.get_dados_pessoais(self.cpf_operador, verbosity=verbosity)[0]
        except Exception as e:
            if verbosity:
                logger.info(f'API CADÚnico não está acessível. Exception: {e}')
            return False
