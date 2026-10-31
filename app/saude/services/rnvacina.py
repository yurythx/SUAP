import logging
import re

from django.core.cache import cache
from django.core.exceptions import ValidationError
from requests.exceptions import RequestException

from comum.models import APIExterna
from comum.services import APIExternaService
from djtools.utils import requests

logger = logging.getLogger(__name__)


class ApiRNMaisVacinaService(APIExternaService):
    """
    Consome a API do RN+Vacina (https://rnmaisvacina.lais.ufrn.br/api/v1/) para consulta de
    imunizações de um cidadão pelo CPF.
    """

    # Validade documentada do refresh token (24h); cacheado com margem de segurança para nunca
    # tentar usar um refresh já expirado no servidor.
    REFRESH_TOKEN_TIMEOUT = 60 * 60 * 20

    def __init__(self):
        super().__init__(APIExterna.RNMAISVACINA)
        self.refresh_cache_name = f'{self.cache_name}_refresh'

    def cpf_auth_token(self, verbosity=False):
        # Override do fluxo genérico de CPF_AUTH: em vez de logar de novo com usuário/senha toda
        # vez que o access token em cache expira/é invalidado, tenta primeiro trocar o refresh
        # token (documentação "API Vacina e Confia" / RN+Vacina, seção "Atualização do Token de
        # Acesso": access token válido 1h, refresh token válido 24h, renovação via POST
        # {url_token}refresh/). Login completo (usuário/senha) repetido parece ser o gatilho dos
        # 403 intermitentes em produção — presumivelmente por abrir uma nova sessão e invalidar
        # tokens concorrentes (ex.: autoatendimento de outro cidadão em paralelo). O refresh é a
        # via de renovação prevista pela API e não deveria ter esse efeito colateral.
        return self._atualizar_com_refresh_token(verbosity=verbosity) or self._autenticar(verbosity=verbosity)

    def _atualizar_com_refresh_token(self, verbosity=False):
        refresh_token = cache.get(self.refresh_cache_name)
        if not refresh_token:
            return None
        url = f'{self.api_externa.url_token}refresh/'
        try:
            response = requests.post(
                url, json={'refresh': refresh_token}, timeout=self.timeout, verbosity=verbosity, API=f'{self.api_externa.nome} - Refresh Token'
            )
        except RequestException:
            return None
        if not response.ok:
            # Refresh token expirado/inválido: descarta e deixa o chamador cair para login completo.
            cache.delete(self.refresh_cache_name)
            return None
        token = response.json().get('access')
        if not token:
            return None
        self.set_token(token)
        return token

    def _autenticar(self, verbosity=False):
        # Login completo: diferente do padrão genérico de CPF_AUTH (payload {"cpf": ...}), o
        # RN+Vacina autentica com {"username": ..., "password": ...}.
        url = self.api_externa.url_token
        if not url:
            raise ValidationError('URL do servidor de autenticação não configurado.')
        data = {'username': self.api_externa.client_id, 'password': self.api_externa.secret}
        response = requests.post(url, json=data, timeout=self.timeout, verbosity=verbosity, API=f'{self.api_externa.nome} - Token')
        if not response.ok:
            raise ValidationError('Não foi possível autenticar no RN+Vacina. Verifique as credenciais.')
        payload = response.json()
        token = payload.get('access') or payload.get('token') or payload.get('accessToken') or payload.get('access_token')
        if not token:
            raise ValidationError('Token de acesso não encontrado na resposta do RN+Vacina.')
        self.set_token(token)
        refresh_token = payload.get('refresh')
        if refresh_token:
            cache.set(self.refresh_cache_name, refresh_token, self.REFRESH_TOKEN_TIMEOUT)
        return token

    def _get_imunizacoes(self, url, verbosity):
        return requests.get(url, headers=self.get_headers(verbosity=verbosity), timeout=self.timeout, verbosity=verbosity, API=self.api_externa.nome)

    def consultar_imunizacoes(self, cpf, verbosity=False):
        # verbosity=False por padrão: com True, o wrapper djtools.utils.requests loga o corpo
        # inteiro das requisições (incluindo a senha do POST de token) e das respostas (dados de
        # saúde do cidadão). Só deveria receber True a partir de uma ferramenta explícita de
        # diagnóstico — hoje nenhum chamador faz isso, então na prática o padrão False sempre vale.
        if not self.api_externa.ativo:
            raise ValidationError('A integração com o RN+Vacina está desativada. Entre em contato com o suporte técnico.')
        cpf_sem_mascara = re.sub(r'\D', '', cpf or '')
        url = f'{self.api_externa.url_base}cidadaos/{cpf_sem_mascara}/imunizacoes/'
        try:
            response = self._get_imunizacoes(url, verbosity)
            if response.status_code in (401, 403):
                # O RN+Vacina não usa só 401 para sinalizar token inválido: também devolve 403
                # ({"detail": "Você não tem permissão para executar essa ação."}) quando o access
                # token em cache foi invalidado antes da hora (ver cpf_auth_token, que agora tenta
                # renovar via refresh token em vez de logar de novo). Sem tratar 403 aqui, a
                # consulta falhava direto e o token ruim ficava parado no cache até expirar
                # sozinho, derrubando a taxa de sucesso das consultas nesse meio tempo.
                #
                # Além disso, tanto o token quanto a própria config da APIExterna
                # (comum.models.buscar_api) ficam em cache local por processo/worker (LocMemCache)
                # quando USE_REDIS=False. Uma correção feita no admin (ex.: tipo de autenticação)
                # só atualiza o cache do worker que atendeu aquele POST — outros workers continuam
                # com a config antiga por até alguns minutos. Por isso, recarrega a APIExterna
                # direto do banco (ignorando esse cache) e força reautenticação antes de tentar
                # mais uma vez.
                cache.delete(self.cache_name)
                self.api_externa = APIExterna.objects.get(pk=self.api_externa.pk)
                url = f'{self.api_externa.url_base}cidadaos/{cpf_sem_mascara}/imunizacoes/'
                response = self._get_imunizacoes(url, verbosity)
        except RequestException as e:
            raise ValidationError('Não foi possível conectar ao RN+Vacina no momento. Tente novamente mais tarde.') from e
        if not response.ok:
            # Anexado como atributo (não na mensagem) para não expor JSON bruto da API ao usuário
            # final; a ferramenta de teste do admin (comum.admin.APIExternaAdmin) lê esses
            # atributos para exibir a resposta crua, sem depender do logger (o root logger deste
            # projeto roda em CRITICAL, então logger.warning não chega a lugar nenhum aqui).
            erro = ValidationError(f'Não foi possível consultar o RN+Vacina no momento (HTTP {response.status_code}). Tente novamente mais tarde.')
            erro.response_status = response.status_code
            erro.response_body = response.text
            raise erro
        try:
            payload = response.json()
        except ValueError as e:
            raise ValidationError('O RN+Vacina retornou uma resposta em formato inesperado (não é JSON válido).') from e
        if not isinstance(payload, dict):
            raise ValidationError('O RN+Vacina retornou uma resposta em formato inesperado.')
        if payload.get('status') != 'sucesso':
            raise ValidationError(payload.get('mensagem') or 'Resposta inesperada do RN+Vacina.')
        dados = payload.get('dados', [])
        if not isinstance(dados, list):
            raise ValidationError('O RN+Vacina retornou uma lista de imunizações em formato inesperado.')
        return dados

    def consultar_por_cpf(self, cpf, verbosity=False):
        # Alias na convenção usada pela ferramenta de teste do admin (comum.admin.APIExternaAdmin):
        # qualquer serviço de APIExterna que implemente `consultar_por_cpf` ganha o botão "Testar
        # Consulta por CPF" automaticamente, sem precisar tocar no admin de novo.
        return self.consultar_imunizacoes(cpf, verbosity=verbosity)

    def estah_acessivel(self, verbosity=False):
        # Só valida a obtenção do token (conectividade/credenciais), sem consultar CPF de
        # paciente real, já que esse método é rodado diariamente para todas as APIExterna
        # (comum.management.commands.desativar_apis_inacessiveis).
        try:
            return bool(self.get_token(verbosity=verbosity))
        except Exception as e:
            if verbosity:
                logger.info(f'Erro ao verificar acessibilidade da API do RN+Vacina. Exception: {e}')
            return False
