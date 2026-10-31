import logging

from django.core.exceptions import ValidationError
from requests.exceptions import RequestException, Timeout

from comum.services import APIExternaService
from djtools.utils import requests

logger = logging.getLogger(__name__)


class ApiCNPJService(APIExternaService):
    """
    Classe que possuem funções para consumir informações da API: https://www.gov.br/conecta/catalogo/apis/consulta-cnpj
    """

    def __init__(self):
        from comum.models import APIExterna

        super().__init__(APIExterna.CNPJ)

    def estah_acessivel(self, verbosity=False):
        try:
            self.get_token()
            return self.consulta_empresa('00000000000191', verbosity=verbosity)[0]
        except Exception as e:
            if verbosity:
                logger.info(f'API CNPJ não está acessível. Exception: {e}')
            return False

    def consulta_empresa(self, cnpj, cpf_operador=None, basico=False, socios=False, verbosity=False):
        """
        Básico: https://apigateway.conectagov.estaleiro.serpro.gov.br/api-cnpj-basica/v2/basica/{CNPJbasica}
        Completa: https://apigateway.conectagov.estaleiro.serpro.gov.br/api-cnpj-empresa/v2/empresa/{CNPJempresa}
        Sócios: https://apigateway.conectagov.estaleiro.serpro.gov.br/api-cnpj-qsa/v2/qsa/{CNPJqsa}

        Retorno padrão do endpoint da resposta Completa, se somente dados básicos então basica==True e se sócios enviar socios==True
        """
        try:
            cnpj = cnpj.replace('.', '').replace('/', '').replace('-', '')
            url = self.api_externa.url_base + f'/api-cnpj-empresa/v2/empresa/{cnpj}'
            if basico:
                url = self.api_externa.url_base + f'/api-cnpj-basica/v2/basica/{cnpj}'
            elif socios:
                url = self.api_externa.url_base + f'/api-cnpj-qsa/v2/qsa/{cnpj}'
            cpf_operador = cpf_operador or self.cpf_operador
            headers = self.get_headers(cpf_operador, verbosity=verbosity)
            req = requests.get(url, headers=headers, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)
            if req.ok:
                return True, req.json()
            return False, {}
        except Timeout:
            raise ValidationError('A API da Receita Federal está com instabilidade, tente novamente mais tarde.')
        except RequestException:
            raise ValidationError('Ocorreu um erro ao obter informações da empresa na Receita Federal, tente novamente mais tarde.')
