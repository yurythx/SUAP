"""Serviço de integração com CKAN usando APIExternaService.

Este módulo implementa a integração com o CKAN seguindo o padrão
de APIs Externas do SUAP, centralizando as credenciais no cadastro
de APIExterna.
"""

import json
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.fields.files import FieldFile
from requests.exceptions import RequestException, Timeout

from comum.models import APIExterna
from comum.services import APIExternaService
from dados_abertos.ckan_client import nome_do_upload
from djtools.utils import requests

logger = logging.getLogger(__name__)


class CKANAPIService(APIExternaService):
    """Serviço para integração com a API do CKAN.

    Implementa as operações de sincronização de organizações, datasets
    e resources com uma instância CKAN remota.

    A API do CKAN utiliza autenticação via API Key no header Authorization.
    """

    def __init__(self):
        super().__init__(APIExterna.CKAN)

    def get_headers(self, verbosity=False):
        """Retorna os headers para requisições ao CKAN.

        O CKAN usa o header Authorization com a API Key diretamente.
        """
        raw_headers = self.api_externa.headers
        if isinstance(raw_headers, str):
            headers = json.loads(raw_headers) if raw_headers else {}
        else:
            headers = raw_headers.copy() if raw_headers else {}
        headers['Authorization'] = self.api_externa.secret
        return headers

    @property
    def base_url(self):
        """URL base do CKAN (sem barra final)."""
        return self.api_externa.url_base.rstrip('/')

    @property
    def api_key(self):
        """Chave de API do CKAN."""
        return self.api_externa.secret

    def _request(self, action: str, *, data: dict | None = None, files=None, method: str = 'POST', verbosity=False):
        """Executa uma action da API do CKAN.

        Args:
            action: Nome da action (ex.: ``organization_show``).
            data: Dicionário com parâmetros a serem enviados.
            files: Arquivos para upload como dict compatível com requests.
            method: Método HTTP (GET ou POST).
            verbosity: Se True, loga detalhes da requisição.

        Returns:
            dict: O campo ``result`` do payload retornado pela API.

        Raises:
            ValidationError: Em caso de erro HTTP, resposta inválida ou
                ``success=False`` na resposta da API.
        """

        url = f'{self.base_url}/api/3/action/{action}'
        headers = self.get_headers(verbosity=verbosity)
        data = data or {}
        # Desabilita verificação SSL em ambiente de desenvolvimento
        verify_ssl = not settings.DEBUG

        try:
            if method.upper() == 'GET':
                kwargs = {'headers': headers, 'timeout': self.timeout, 'verbosity': verbosity, 'API': self.api_externa.nome, 'verify': verify_ssl}
                if data:
                    kwargs['params'] = data
                resp = requests.get(url, **kwargs)
            else:
                if files:
                    resp = requests.post(
                        url,
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=self.timeout,
                        verbosity=verbosity,
                        API=self.api_externa.nome,
                        verify=verify_ssl,
                    )
                else:
                    headers['Content-Type'] = 'application/json'
                    resp = requests.post(
                        url, headers=headers, json=data, timeout=self.timeout, verbosity=verbosity, API=self.api_externa.nome, verify=verify_ssl
                    )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get('success'):
                raise ValidationError(f'Erro CKAN: {payload}')
            return payload['result']
        except Timeout:
            raise ValidationError('A API do CKAN está com instabilidade, tente novamente mais tarde.')
        except RequestException as e:
            status = resp.status_code if 'resp' in dir() and hasattr(resp, 'status_code') else ''
            raise ValidationError(f'Erro ao comunicar com CKAN: {status} {e}')

    def estah_acessivel(self, verbosity=False):
        """Verifica se a API do CKAN está acessível."""
        try:
            self._request('status_show', method='GET', verbosity=verbosity)
            return True
        except Exception as e:
            if verbosity:
                logger.info(f'Erro ao verificar acessibilidade do CKAN: {e}')
            return False

    # ---------- Organization ----------
    def organization_show(self, id_or_name: str, verbosity=False):
        """Obtém os dados de uma organização por ID ou nome."""
        return self._request('organization_show', data={'id': id_or_name}, verbosity=verbosity)

    def organization_create(self, data: dict, *, imagem: FieldFile | None = None, verbosity=False):
        """Cria uma organização no CKAN."""
        if imagem:
            with imagem.open('rb') as f:
                return self._request('organization_create', data=data, files={'image_upload': (nome_do_upload(imagem), f)}, verbosity=verbosity)
        return self._request('organization_create', data=data, verbosity=verbosity)

    def organization_update(self, data: dict, *, imagem: FieldFile | None = None, verbosity=False):
        """Atualiza uma organização no CKAN (patch)."""
        if imagem:
            with imagem.open('rb') as f:
                return self._request('organization_patch', data=data, files={'image_upload': (nome_do_upload(imagem), f)}, verbosity=verbosity)
        return self._request('organization_patch', data=data, verbosity=verbosity)

    # ---------- Dataset/Package ----------
    def package_show(self, id_or_name: str, verbosity=False):
        """Obtém os dados de um dataset por ID ou nome."""
        return self._request('package_show', data={'id': id_or_name}, verbosity=verbosity)

    def package_create(self, data: dict, verbosity=False):
        """Cria um dataset no CKAN."""
        return self._request('package_create', data=data, verbosity=verbosity)

    def package_update(self, data: dict, verbosity=False):
        """Atualiza um dataset no CKAN (patch)."""
        return self._request('package_patch', data=data, verbosity=verbosity)

    def package_resources(self, dataset_key: str, verbosity=False):
        """Retorna lista de resources de um dataset."""
        pkg = self.package_show(dataset_key, verbosity=verbosity)
        return pkg.get('resources', [])

    # ---------- Resource ----------
    def resource_show(self, resource_id: str, verbosity=False):
        """Obtém os dados de um resource por ID."""
        return self._request('resource_show', data={'id': resource_id}, verbosity=verbosity)

    def resource_create(self, data: dict, *, file_field: str | None = None, arquivo: FieldFile | None = None, verbosity=False):
        """Cria um resource no CKAN."""
        if arquivo and file_field:
            with arquivo.open('rb') as f:
                return self._request('resource_create', data=data, files={file_field: (nome_do_upload(arquivo), f)}, verbosity=verbosity)
        return self._request('resource_create', data=data, verbosity=verbosity)

    def resource_update(self, data: dict, *, file_field: str | None = None, arquivo: FieldFile | None = None, verbosity=False):
        """Atualiza um resource no CKAN (patch)."""
        if arquivo and file_field:
            with arquivo.open('rb') as f:
                return self._request('resource_patch', data=data, files={file_field: (nome_do_upload(arquivo), f)}, verbosity=verbosity)
        return self._request('resource_patch', data=data, verbosity=verbosity)


def get_ckan_service():
    """Obtém o serviço CKAN configurado.

    Returns:
        CKANAPIService | None: Instância do serviço ou None se não configurado.
    """
    try:
        api = APIExterna.CKAN
        if api and api.ativo:
            return api.get_service()
    except Exception:
        pass
    return None


def is_ckan_configured():
    """Verifica se a API CKAN está configurada e ativa.

    Returns:
        bool: True se configurada e ativa.
    """
    try:
        api = APIExterna.CKAN
        return api and api.ativo
    except Exception:
        return False
