"""Cliente e utilitários para integração com a API do CKAN.

Fornece uma classe ``CKANClient`` com métodos convenientes para executar
ações da API do CKAN (organizações, grupos, datasets e recursos), com
tratamento simples de erros e suporte a uploads multipart.

O estilo de docstrings segue o padrão Google para facilitar a geração
automática de documentação.
"""

import os

from django.conf import settings
from django.db.models.fields.files import FieldFile
from requests.exceptions import RequestException

from djtools.utils import requests


class CKANError(Exception):
    """Erro genérico de operações contra a API do CKAN.

    É levantado quando a API retorna ``success=False``, quando há erros
    de rede (via ``requests``) ou quando ocorre algum problema de
    parsing/validação do retorno.
    """


def nome_do_upload(arquivo: FieldFile) -> str:
    """Nome do arquivo a declarar no multipart, sem o diretório do ``upload_to``."""
    return os.path.basename(arquivo.name)


class CKANClient:
    """Cliente HTTP para a API do CKAN (v3 action API).

    Attributes:
        base_url: URL base do CKAN (sem barra ao final).
        api_key: Chave de API usada para autenticação.
        timeout: Tempo máximo (segundos) para cada requisição.
        headers: Cabeçalhos padrão enviados nas requisições.
    """

    def __init__(self, base_url: str, api_key: str | None, timeout: int = 30):
        """Inicializa o cliente.

        Args:
            base_url: URL base do CKAN (ex.: ``https://ckan.example.org``).
            api_key: Chave da API; pode ser ``None`` para operações públicas.
            timeout: Tempo máximo (em segundos) para cada requisição.
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or ''
        self.timeout = timeout
        self.headers = {
            'Authorization': self.api_key,
        }

    def _request(self, action: str, *, data: dict | None = None, files=None, method: str | None = None) -> dict:
        """Executa uma action da API do CKAN e retorna o ``result``.

        Por padrão, utiliza ``POST`` (recomendado para a action API). Para
        operações que exijam leitura explícita, pode utilizar ``GET`` com
        envio via ``params``.

        Args:
            action: Nome da action (ex.: ``organization_show``).
            data: Dicionário com parâmetros a serem enviados.
            files: Arquivos para upload como dict compatível com
                ``requests`` (ex.: ``{"image_upload": (nome, fileobj)}``).
            method: Método HTTP explícito (``GET`` ou ``POST``). Se omitido,
                assume ``POST``.

        Returns:
            dict: O campo ``result`` do payload retornado pela API.

        Raises:
            CKANError: Em caso de erro HTTP, resposta inválida ou
                ``success=False`` na resposta da API.
        """
        url = f'{self.base_url}/api/3/action/{action}'
        method = method or 'POST'
        data = data or {}
        # Desabilita verificação SSL em ambiente de desenvolvimento
        verify_ssl = not settings.DEBUG

        try:
            if method.upper() == 'GET':
                # Envia parâmetros corretamente
                resp = requests.get(url, headers=self.headers, params=data, timeout=self.timeout, verify=verify_ssl)
            else:
                if files:
                    # Upload multipart
                    resp = requests.post(url, headers=self.headers, data=data, files=files, timeout=self.timeout, verify=verify_ssl)
                else:
                    # Para CKAN actions sem upload pode enviar JSON
                    resp = requests.post(
                        url, headers={**self.headers, 'Content-Type': 'application/json'}, json=data, timeout=self.timeout, verify=verify_ssl
                    )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get('success'):
                raise CKANError(str(payload))
            return payload['result']
        except RequestException as e:
            raise CKANError(f'{resp.status_code if "resp" in locals() else ""} {e}')

    # ---------- Organization ----------
    def organization_show(self, id_or_name: str) -> dict:
        """Obtém os dados de uma organização por ID ou nome.

        Args:
            id_or_name: Identificador único (UUID) ou ``name`` da organização.

        Returns:
            dict: Representação da organização no CKAN.

        Raises:
            CKANError: Se houver falha na requisição.
        """
        return self._request('organization_show', data={'id': id_or_name})

    def organization_create(self, data: dict, *, imagem: FieldFile | None = None) -> dict:
        """Cria uma organização.

        Args:
            data: Payload com os campos da organização.
            imagem: Arquivo de imagem para upload (opcional), lido pelo storage.

        Returns:
            dict: Representação criada da organização.

        Raises:
            CKANError: Em caso de erro na API/validação.
        """
        if imagem:
            with imagem.open('rb') as f:
                return self._request('organization_create', data=data, files={'image_upload': (nome_do_upload(imagem), f)})
        return self._request('organization_create', data=data)

    def organization_update(self, data: dict, *, imagem: FieldFile | None = None) -> dict:
        """Atualiza parcialmente uma organização (patch).

        Args:
            data: Payload com os campos a atualizar (deve incluir ``id``).
            imagem: Arquivo de nova imagem para upload (opcional), lido pelo storage.

        Returns:
            dict: Representação atualizada da organização.

        Raises:
            CKANError: Em caso de erro na API/validação.
        """
        if imagem:
            with imagem.open('rb') as f:
                return self._request('organization_patch', data=data, files={'image_upload': (nome_do_upload(imagem), f)})
        return self._request('organization_patch', data=data)

    # ---------- Group ----------
    def group_show(self, id_or_name: str) -> dict:
        """Obtém os dados de um grupo por ID ou nome.

        Args:
            id_or_name: Identificador único (UUID) ou ``name`` do grupo.

        Returns:
            dict: Representação do grupo no CKAN.

        Raises:
            CKANError: Se houver falha na requisição.
        """
        return self._request('group_show', data={'id': id_or_name})

    def group_create(self, data: dict) -> dict:
        """Cria um grupo.

        Args:
            data: Payload com os campos do grupo.

        Returns:
            dict: Representação criada do grupo.
        """
        return self._request('group_create', data=data)

    def group_update(self, data: dict) -> dict:
        """Atualiza parcialmente um grupo (patch).

        Args:
            data: Payload com os campos a atualizar (deve incluir ``id``).

        Returns:
            dict: Representação atualizada do grupo.
        """
        return self._request('group_patch', data=data)

    # ---------- Dataset (package) ----------
    def package_show(self, id_or_name: str) -> dict:
        """Obtém um dataset (package) por ID ou nome.

        Args:
            id_or_name: Identificador único (UUID) ou ``name`` do dataset.

        Returns:
            dict: Representação do dataset no CKAN.
        """
        return self._request('package_show', data={'id': id_or_name})

    def package_create(self, data: dict) -> dict:
        """Cria um dataset (package)."""
        return self._request('package_create', data=data)

    def package_update(self, data: dict) -> dict:
        """Atualiza parcialmente um dataset (patch)."""
        return self._request('package_patch', data=data)

    # ---------- Resource ----------
    def resource_show(self, id_or_name: str) -> dict:
        """Obtém um resource por ID.

        Args:
            id_or_name: Identificador único (UUID) do resource.

        Returns:
            dict: Representação do resource no CKAN.
        """
        return self._request('resource_show', data={'id': id_or_name})

    def resource_create(self, data: dict, file_field: str | None = None, arquivo: FieldFile | None = None):
        """Cria um resource (link ou upload).

        Args:
            data: Payload com os campos do resource.
            file_field: Nome do campo de arquivo (ex.: ``upload`` ou ``image_upload``).
            arquivo: Arquivo a enviar (se upload), lido pelo storage.

        Returns:
            dict: Representação criada do resource.
        """
        if file_field and arquivo:
            with arquivo.open('rb') as f:
                return self._request('resource_create', data=data, files={file_field: (nome_do_upload(arquivo), f)})
        return self._request('resource_create', data=data)

    def resource_update(self, data: dict, file_field: str | None = None, arquivo: FieldFile | None = None):
        """Atualiza parcialmente um resource (patch), com ou sem upload.

        Args:
            data: Payload com os campos a atualizar (deve incluir ``id``).
            file_field: Nome do campo de arquivo (ex.: ``upload``).
            arquivo: Arquivo a enviar (se upload), lido pelo storage.

        Returns:
            dict: Representação atualizada do resource.
        """
        if file_field and arquivo:
            with arquivo.open('rb') as f:
                return self._request('resource_patch', data=data, files={file_field: (nome_do_upload(arquivo), f)})
        return self._request('resource_patch', data=data)

    # ---------- Helpers adicionais ----------
    def package_resources(self, id_or_name: str) -> list[dict]:
        """Retorna a lista de resources de um dataset.

        Usa internamente a action ``package_show`` e retorna o campo
        ``resources``.

        Args:
            id_or_name: Identificador ou ``name`` do dataset.

        Returns:
            list[dict]: Lista de objetos de resource retornados pelo CKAN.
        """
        pkg = self.package_show(id_or_name)
        return pkg.get('resources', [])
