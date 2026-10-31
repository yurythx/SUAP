import logging

from django.core.exceptions import ValidationError
from requests.exceptions import RequestException, Timeout

from comum.models import APIExterna
from comum.services import APIExternaService
from contratos.models import Contrato
from djtools.utils import requests

TIMEOUT = 30
logger = logging.getLogger(__name__)


class ApiContratosGovBRService(APIExternaService):
    """
    Classe que possuem funções para consumir informações da API: https://contratos.comprasnet.gov.br/api/docs
    """

    def __init__(self):
        super().__init__(APIExterna.CONTRATOSGOVBR)

    def obter_itens_contrato_comprasgov(self, contrato_id_comprasgov, verbosity=False):
        """
        Realiza requisição para a API do ComprasGov para buscar itens de um contrato pelo id
        """
        url = self.api_externa.url_base + f'contrato/{contrato_id_comprasgov}/itens'
        headers = self.get_headers(verbosity=verbosity)
        try:
            response = requests.get(url, headers=headers, timeout=TIMEOUT, verbosity=verbosity, API=self.api_externa.nome)
            return response.json()
        except Timeout:
            raise ValidationError('A API do ComprasGov está com instabilidade, tente novamente mais tarde.')
        except RequestException:
            raise ValidationError('Ocorreu um erro ao obter informações do ComprasGov, tente novamente mais tarde.')

    def estah_acessivel(self, verbosity=False):
        try:
            contrato = Contrato.objects.filter(id_comprasgov__isnull=False).first()
            id_comprasgov = contrato and contrato.id_comprasgov or '000001'
            return bool(self.obter_itens_contrato_comprasgov(id_comprasgov, verbosity=verbosity))
        except Exception as e:
            if verbosity:
                logger.info(f'Erro ao verificar acessibilidade da API do ComprasGov. Exception: {e}')
            return False

    def obter_contrato_comprasgov(self, contrato_id_comprasgov):
        """
        Realiza requisição para a API do ComprasGov para buscar Contrato pelo número de processo ou número de contrato
        """
        url = self.api_externa.url_base + f'contrato/id/{contrato_id_comprasgov}'
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=TIMEOUT)
            if response.ok:
                return response.json()[0]
        except Timeout:
            raise ValidationError('A API do ComprasGov está com instabilidade, tente novamente mais tarde.')
        except RequestException:
            raise ValidationError('Ocorreu um erro ao obter informações do ComprasGov, tente novamente mais tarde.')
