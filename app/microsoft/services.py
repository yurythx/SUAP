import logging
from collections.abc import Callable

import msal
from django.conf import settings
from django.core.cache import cache
from requests.exceptions import HTTPError

from comum.models import APIExterna, Configuracao
from comum.services import APIExternaService
from djtools.utils import requests
from microsoft.schemas import DriveItem, SiteInfo

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)


class MSGraphService(APIExternaService):
    """
    Classe base para o cliente da API do Microsoft Graph.

    Requer uma APIExterna cadastrada com os seguintes campos:

    - Nome: MSGRAPH
    - URL base: URL sem a versão e sem a barra final (ex: https://graph.microsoft.com)
    - Tipo: OAuth2 - Client Credentials
    - Client ID
    - Secret
    - (opcional) URL da documentação: https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0

    Além disso, é preciso ter o domínio da Microsoft no comum.Configuracao (app 'microsoft', chave 'dominio_microsoft').
    """

    def __init__(self):
        super().__init__(APIExterna.MSGRAPH)
        self.dominio_microsoft = Configuracao.get_valor_por_chave('microsoft', 'dominio_microsoft')
        if self.dominio_microsoft is None:
            raise ValueError('O domínio da organização na Microsoft não está configurado.')

        self.url_microsoft_tenant = f'https://login.microsoftonline.com/{self.dominio_microsoft}'
        self.msgraph_base_url = f'{self.api_externa.url_base}/v1.0'
        self.escopos = ['https://graph.microsoft.com/.default']
        self.cliente = msal.ConfidentialClientApplication(
            client_id=self.api_externa.client_id,
            authority=self.url_microsoft_tenant,
            client_credential=self.api_externa.secret,
        )

    def estah_acessivel(self, verbosity=False):
        try:
            return self.get_token(verbosity) != ''
        except Exception as e:
            if verbosity:
                logger.info(f'Erro ao obter token do Microsoft Graph. Detalhe: {e}')
            return False

    def get_token(self, verbosity=False) -> str:
        if verbosity:
            logger.info('Obtendo token do Microsoft Graph.')
        retorno = self.cliente.acquire_token_silent(scopes=self.escopos, account=None)
        if not retorno:
            retorno = self.cliente.acquire_token_for_client(scopes=self.escopos)
        if 'access_token' in retorno:
            if verbosity:
                logger.info(f'Token disponível na cache: {retorno["access_token"][:10]}...')
        else:
            if verbosity:
                msg_erro = f'Não foi possível obter um token do Microsoft Graph. Detalhes: {retorno.get("error_description")}.'
                logger.info(msg_erro)
            raise HTTPError(msg_erro)
        return retorno['access_token'] if retorno else ''


SP_SERVICE_SINGLETONS = {}


class SharepointService(MSGraphService):
    """
    Cliente para acesso aos endpoints do Sharepoint na API do Microsoft Graph.

    É preciso ter uma aplicação cadastrada no Microsoft Entra com os seguintes escopos:

    - Files.Read.All (do tipo Aplicativo)
    - Sites.Read.All (do tipo Aplicativo)
    """

    def __init__(self, hostname, caminho_site, diretorio_raiz):
        """
        Inicializa o cliente da API do Sharepoint.
        Ao invés de chamar este método diretamente, prefira utilizar o método get_instance(),
        que evita criar várias instâncias para a mesma configuração.
        """
        super().__init__()
        self.hostname, self.caminho_site, self.diretorio_raiz = hostname, caminho_site, diretorio_raiz

    @classmethod
    def get_instance(cls, hostname, caminho_site, diretorio_raiz):
        chave = f'{hostname};{caminho_site};{diretorio_raiz}'
        if chave in SP_SERVICE_SINGLETONS:
            return SP_SERVICE_SINGLETONS[chave]
        else:
            instance = cls(hostname, caminho_site, diretorio_raiz)
            SP_SERVICE_SINGLETONS[chave] = instance
            if not instance.api_externa.ativo:
                raise ValueError('API Externa não inativa: MSGRAPH.')
            return instance

    def get_dados_do_site(self, select: str | None = None) -> SiteInfo:
        """
        Consulta na API os dados do site configurado.

        Na prática, faz uma chamada `GET /sites/[hostname]:/[caminho_do_site]?$select=[select]`

        Mais detalhes: https://learn.microsoft.com/en-us/graph/api/site-get?view=graph-rest-1.0.

        :param select: string com os campos a serem retornados, separados por vírgula (padrão: todos os campos).
        :return: SiteInfo
        """
        endpoint_projeto = f'{self.msgraph_base_url}/sites/{self.hostname}:/{self.caminho_site}'
        if select:
            endpoint_projeto += f'?$select={select}'
        logger.info(f'Obtendo informações do site... (GET {endpoint_projeto})')
        retorno = requests.get(
            endpoint_projeto,
            headers={'Authorization': f'Bearer {self.get_token()}'},
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if retorno.status_code != 200:
            msg_erro = f'Requisição mal sucedida ({retorno.status_code} {retorno.reason}). Detalhes: {retorno.text}.'
            logger.warning(msg_erro)
            raise HTTPError(msg_erro)

        logger.debug(f'Dados do site obtidos: {str(retorno.text)[:150]}[...]')
        return retorno.json()

    def get_id_do_site(self) -> str:
        CHAVE_CACHE_ID_DO_SITE = f'MS_GRAPH_SHAREPOINT_ID_DO_SITE_{self.hostname}_{self.caminho_site}'
        logger.debug('Buscando ID do site na cache...')
        id_do_site = cache.get(CHAVE_CACHE_ID_DO_SITE)
        if id_do_site is None:
            logger.debug('ID do site não encontrado na cache. Requisitando-o da API.')
            id_do_site = self.get_dados_do_site(select='id')['id']
            cache.set(CHAVE_CACHE_ID_DO_SITE, id_do_site)
            logger.debug(f'Id do site obtido: {id_do_site[:100]}')
        return id_do_site

    def buscar_itens_no_drive(
        self, id_diretorio_pai=None, endpoint: str | None = None, func_filtro: Callable[[DriveItem], bool] = lambda x: True
    ) -> list[DriveItem]:
        """
        Percorre, em profundidade, a árvore de diretórios buscando itens que satisfaçam `func_filtro`.

        Se `id_diretorio_pai` for omitido, a varredura utilizará a informação de `self.diretorio_raiz`.
        Se esse campo também estiver vazio, o percurso terá a raiz do drive como ponto de partida.

        :param func_filtro:.
        :param id_diretorio_pai:
        :param endpoint: se `None`, o endpoint é gerado com base nas configurações. Usado internamente para paginação.
        :return: list[DriveItem]
        """
        if endpoint is None:
            if id_diretorio_pai:
                descricao_diretorio = f'diretório com id {id_diretorio_pai[:10]}[...]'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/items/{id_diretorio_pai}/children'
            elif self.diretorio_raiz:
                descricao_diretorio = f'diretório {self.diretorio_raiz}'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/root:/{self.diretorio_raiz}:/children'
            else:
                descricao_diretorio = 'diretório raiz do projeto'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/root/children'

            select = '$select=id,name,webUrl,folder,file,size,parentReference'
            endpoint = f'{endpoint}?{select}'
            logger.debug(f'Obtendo conteúdo do {descricao_diretorio}.')

        logger.debug(f'GET {endpoint}')
        retorno = requests.get(
            endpoint,
            headers={'Authorization': f'Bearer {self.get_token()}'},
            timeout=settings.REQUESTS_TIMEOUT,
        )

        if retorno.status_code != 200:
            mensagem = f'Requisição mal sucedida ({retorno.status_code} {retorno.reason}). Detalhes: {retorno.text}.'
            logger.warning(mensagem)
            raise requests.HTTPError(mensagem)

        itens_buscados = []
        corpo_resposta = retorno.json()
        if 'value' in corpo_resposta:
            logger.debug('Processando itens retornados.')
            logger.debug(f'corpo_resposta: {corpo_resposta}')
            for arquivo_ou_diretorio in corpo_resposta['value']:
                caminho_do_item = f'{arquivo_ou_diretorio["parentReference"]["path"]}/{arquivo_ou_diretorio["name"]}'
                logger.debug(f'Analisando item {caminho_do_item}.')
                if func_filtro(arquivo_ou_diretorio):
                    itens_buscados.append(arquivo_ou_diretorio)
                if 'folder' in arquivo_ou_diretorio:
                    itens_buscados.extend(self.buscar_itens_no_drive(id_diretorio_pai=arquivo_ou_diretorio['id'], func_filtro=func_filtro))

            if '@odata.nextLink' in corpo_resposta:
                logger.debug('Usando o atributo @odata.nextLink para continuar busca por itens...')
                itens_buscados.extend(self.buscar_itens_no_drive(endpoint=corpo_resposta['@odata.nextLink'], func_filtro=func_filtro))

        return itens_buscados

    def buscar_arquivos_no_drive(self, func_filtro: Callable[[DriveItem], bool] = lambda di: True):
        """
        Usa o método `buscar_itens_no_drive` aplicando filtro para retornar apenas arquivos.

        :param query: texto da busca.
        :return: lista de diretórios.
        """
        return self.buscar_itens_no_drive(func_filtro=lambda r: 'file' in r and func_filtro(r))

    def buscar_diretorios_no_drive(self, func_filtro: Callable[[DriveItem], bool] = lambda di: True):
        """
        Usa o método `buscar_itens_no_drive` aplicando filtro para retornar apenas diretórios.

        :param func_filtro: função para filtrar quais DriveItems devem ser incluídos nos resultados.
        :return: lista de diretórios.
        """
        return self.buscar_itens_no_drive(func_filtro=lambda r: 'folder' in r and func_filtro(r))

    def processar_arquivos_do_diretorio(self, func_processar: Callable[[DriveItem], None], id_diretorio_pai=None, endpoint=None):
        """
        Percorre, em profundidade, a árvore de diretórios aplicando a função `func_processar` em todos os arquivos encontrados.

        Se `id_diretorio_pai` for omitido, a varredura utilizará a informação de `self.diretorio_raiz`.
        Se esse campo também estiver vazio, o percurso terá a raiz do drive como ponto de partida.

        :param func_processar: função que será chamada em cada arquivo.
        :param id_diretorio_pai:
        :param endpoint: se `None`, o endpoint é gerado com base nas configurações. Usado internamente para paginação.
        :return: list[DriveItem]
        """
        if endpoint is None:
            if id_diretorio_pai:
                descricao_diretorio = f'diretório com id {id_diretorio_pai[:10]}[...]'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/items/{id_diretorio_pai}/children'
            elif self.diretorio_raiz:
                descricao_diretorio = f'diretório {self.diretorio_raiz}'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/root:/{self.diretorio_raiz}:/children'
            else:
                descricao_diretorio = 'diretório raiz do projeto'
                endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/root/children'

            select = '$select=id,name,webUrl,folder,file,size,parentReference'
            endpoint = f'{endpoint}?{select}'
            logger.debug(f'Obtendo conteúdo do {descricao_diretorio}.')

        logger.debug(f'GET {endpoint}')
        retorno = requests.get(
            endpoint,
            headers={'Authorization': f'Bearer {self.get_token()}'},
            timeout=settings.REQUESTS_TIMEOUT,
        )

        if retorno.status_code != 200:
            mensagem = f'Requisição mal sucedida ({retorno.status_code} {retorno.reason}). Detalhes: {retorno.text}.'
            logger.warning(mensagem)
            raise HTTPError(mensagem)

        corpo_resposta = retorno.json()
        if 'value' in corpo_resposta:
            logger.debug('Processando itens retornados.')
            for arquivo_ou_diretorio in corpo_resposta['value']:
                logger.debug(f'{arquivo_ou_diretorio["parentReference"]["path"]}/{arquivo_ou_diretorio["name"]}')
                if 'file' in arquivo_ou_diretorio:
                    func_processar(arquivo_ou_diretorio)
                elif 'folder' in arquivo_ou_diretorio:
                    self.processar_arquivos_do_diretorio(id_diretorio_pai=arquivo_ou_diretorio['id'], func_processar=func_processar)

            if '@odata.nextLink' in corpo_resposta:
                logger.debug('Usando o atributo @odata.nextLink para varrer mais itens...')
                self.processar_arquivos_do_diretorio(endpoint=corpo_resposta['@odata.nextLink'], func_processar=func_processar)

    def baixar_arquivo(self, id_arquivo) -> bytes:
        endpoint = f'{self.msgraph_base_url}/sites/{self.get_id_do_site()}/drive/items/{id_arquivo}/content'
        logger.debug(f'Iniciando download de arquivo com id {id_arquivo[:10]}[...].')
        logger.debug(f'GET {endpoint}')
        resposta = requests.get(
            endpoint,
            headers={'Authorization': f'Bearer {self.get_token()}'},
            timeout=settings.REQUESTS_TIMEOUT,
        )

        if resposta.status_code != 200:
            mensagem = f'Requisição mal sucedida ({resposta.status_code} {resposta.reason}). Detalhes: {resposta.text}.'
            logger.warning(mensagem)
            raise HTTPError(mensagem)

        return resposta.content
