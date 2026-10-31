import base64
import json
import logging
import os
from datetime import datetime
from io import BytesIO

import jwt
from django.conf import settings
from django.contrib import auth, messages
from django.core.files.base import ContentFile
from django.db.models import Q
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from PIL import Image

from comum.models import APIExterna, JustificativaUsuarioExterno, Municipio, OauthLogin, PessoaEndereco, PessoaFisica, PrestadorServico, User, Vinculo
from djtools.utils import mask_cpf, requests
from rh.deduplicacao.entrada import Politica, aplicar_politica
from rh.models import PessoaInfoComplementar

logger = logging.getLogger(__name__)


"""
Classe responsável por implementar o fluxo de autenticação oauth do GovBR para o SUAP.
Foi baseada fundamentalmente em três pontos identificados a partir da necessidade de uma maior customização da autenticação,
o que não foi possível com o uso da biblioteca django-social-auth. São eles:

1) Redirecionamento para o GOV.BR ao tentar abrir uma tela que requer autenticação e retorno automático para ela ao final do login;
2) Possibilidade de cadastro automático da conta do usuário no SUAP para acessos com um determinado nível de confiabilidade do GOV.BR (prata ou ouro, por exemplo);
3) Implementação legível, explícita, segura e de fácil manutenção ;

Para iniciar o fluxo de autenticação, basta acessar a URL /accounts/login/?code=

Após autenticação do usuário no GovBR, as seguintes ações são executadas no SUAP:
• Criação automática do usuário inexistente no SUAP caso essa configuração esteja ativada
• Atualização dos dados do usuário com dados da Receita Federal caso essa configuração esteja ativada
• Registro na sessão do usuário para informar que a autenticação se deu via GovBR
• Verificação da quantidade de vínculos ativos do usuário e redirecionamento para a view de seleção de vínculo se necessário

Cenários de uso

1 - Login básico
    1.1 - Usuário cadastrado no SUAP
        - O usuário acessa tela de login do SUAP e clica no botão "Acessar com gov.br"
        - O usuário efetua login no gov.br e é redirecionado para a tela inicial
    1.2 - Usuário não cadastrado no SUAP
        - O usuário acessa tela de login do SUAP e clica no botão "Acessar com gov.br"
        - O usuário efetua login no gov.br e ao ser redirecionado recebe uma mensagem informando que o usuário não existe no SUAP
2 - Login com auto-cadastro
    - O usuário acessa tela de login do SUAP e clica no botão "Acessar com gov.br"
    - O usuário efetua login no gov.br
    - A conta do usuário é automaticamente criada no SUAP caso ela não exista
    - O usuário é redirecionado para a tela inicial
3 - Login via redirecionamento
    3.1 - Com backend de autenticação alternativo
        - O usuário tenta acessar uma view protegida
        - O usuário é redirecionado para a tela de login do SUAP
        - O usuáro efetua login via gov.br
        - O usuário é redirecionado para a página desejada
    3.2 - Sem backend de autenticação alternativo
        - O usuário tenta acessar uma view protegida
        - O usuário é redirecionado para o gov.br
        - O usuáro efetua login via gov.br
        - O usuário é redirecionado para a página desejada
4 - Assinatura de documentos
    4.1 - Com access token válido
        - O usuário acessa a tela de assinatura de documento
        - O SUAP verifica o grau de confiabilidade do usuário
        - O SUAP verifica a habilitação de multiplo-fator de autenticação
        - O usuário realiza a assinatura do documento
    4.2 - Com access token expirado
        - O usuário acessa a tela de assinatura de documento
        - O usuário é redirecionado para a tela de login do gov.br para renovação do token
        - O usuário é redirecionado para a tela de assinatura de documento com o token renovado
        - O SUAP verifica o grau de confiabilidade do usuário
        - O SUAP verifica a habilitação de multiplo-fator de autenticação
        - O usuário realiza a assinatura do documento
"""


def govbr_token_required(func):
    """
    Decorator para ser utilizada em views que requerem access_token não expirados.
    """

    def wrapper(request, *args, **kwargs):
        expires_at = datetime.fromtimestamp(request.session['token_govbr']['decoded_data']['exp'])
        expires_in = (expires_at - datetime.now()).total_seconds() / 60
        logger.debug(f'Govbr token expires at {expires_at}.')
        logger.debug(f'Govbr token expires in {expires_in} minutes.')
        if expires_in > 10:
            return func(request, *args, **kwargs)
        return redirect(f'/accounts/login/?govbr=1&next={request.path}')

    return wrapper


def user_confiability_level(cpf, access_token):
    """
    Funçao que checa o nivel de confiabilidade do usuário no gov.br
    """
    logger.debug('Fetching user confiability level...')
    url = settings.GOVBR['API_URL']
    url = f'{url}/confiabilidades/v3/contas/{cpf}/niveis?response-type=ids'
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(url, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
    try:
        values = response.json()
    except ValueError:
        logger.debug(
            'GovBR confiability returned invalid/empty JSON. status=%s body=%r',
            response.status_code,
            response.text[:200],
        )
        return '0'

    try:
        values = sorted(values, key=lambda x: x['id'], reverse=True)
        level = values[0]['id'] if values else '0'
        logger.debug(f'Received confiability level {level}')
    except Exception:
        logger.debug(f'Error fetching confiability level. Response: {values}')
        level = '0'
    return level


def destino_pos_autenticacao(request) -> str:
    """Retorna a URL para onde o usuário deve seguir após autenticar com o Gov.BR.

    Lê o cookie ``auth_redirect_url`` (gravado com o ``next`` da tela de login) e o
    valida, já que ele vem de parâmetro de URL e alimenta um ``redirect``.

    Args:
        request: Requisição HTTP em curso.

    Returns:
        A URL do cookie quando ela aponta para o próprio host, ``'/'`` caso contrário.
    """
    url = request.COOKIES.get('auth_redirect_url', '/')
    if not url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return '/'
    return url


def govbr_confiability_level(request):
    pessoa_fisica = request.user.get_profile()
    if pessoa_fisica and pessoa_fisica.cpf:
        cpf = pessoa_fisica.cpf.replace('.', '').replace('-', '')
        access_token = request.session['token_govbr']['access_token']
        return user_confiability_level(cpf, access_token)
    return '0'


class Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def redirect(self, request):
        redirect_uri = '{}{}'.format(settings.SITE_URL, settings.GOVBR['REDIRECT_URI'])
        authorize_url = '{}?response_type=code&client_id={}&redirect_uri={}'.format(
            settings.GOVBR['AUTHORIZATION_URL'], settings.GOVBR['CLIENT_ID'], redirect_uri
        )
        if settings.GOVBR.get('SCOPES'):
            authorize_url = '{}&scope={}'.format(authorize_url, ' '.join(settings.GOVBR.get('SCOPES')))
        logger.debug(f'Redirecting to {authorize_url}...')
        response = redirect(authorize_url)
        if 'govbr' not in request.GET:
            response.delete_cookie('auth_redirect_url')
        if 'next' in request.GET and request.GET['next'] != '/':
            response.set_cookie('auth_redirect_url', request.GET['next'], max_age=360)
        return response

    def get_token_data(self, code):
        logger.debug('Getting acess token...')
        client_secret = settings.GOVBR['SECRET_KEY']
        if client_secret.startswith('$'):
            client_secret = os.environ[client_secret[1:]]
        redirect_uri = '{}{}'.format(settings.SITE_URL, settings.GOVBR['REDIRECT_URI'])
        access_token_request_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': settings.GOVBR['CLIENT_ID'],
            'client_secret': client_secret,
        }
        response = requests.post(settings.GOVBR['ACCESS_TOKEN_URL'], data=access_token_request_data, verify=False, timeout=settings.REQUESTS_TIMEOUT)
        output = response.json()
        logger.debug(f'Received token data {output}')
        return output

    def decode_access_token(self, access_token):
        logger.debug('Decoding access token...')
        # jwt.decode(access_token, options={"verify_signature": False})
        header_encoded, _, _ = access_token.split('.')
        header = json.loads(base64.b64decode(header_encoded + '==').decode('utf-8'))
        kid = header.get('kid')
        for jwk in requests.get(settings.GOVBR['JWK_URL'], timeout=settings.REQUESTS_TIMEOUT).json()['keys']:
            if jwk['kid'] == kid:
                break
        decoded = jwt.decode(
            access_token, key=jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk)), algorithms=[jwk['alg']], audience=settings.GOVBR['CLIENT_ID']
        )
        logger.debug(f'Access token decoded to {decoded}')
        return decoded

    def get_user_data(self, token_response_data):
        logger.debug('Obtaining user data...')
        headers = {'Authorization': f'Bearer {token_response_data["access_token"]}', 'x-api-key': settings.GOVBR['SECRET_KEY']}
        response = requests.get(
            settings.GOVBR['USER_DATA_URL'],
            data={'scope': ' '.join(settings.GOVBR['SCOPES'])},
            headers=headers,
            verify=False,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        data = response.json()
        logger.debug(f'Received user data response {data}')
        splitted_name = data['name'].split()
        first_name, last_name = splitted_name[0], ''
        vinculos_ativos_ids = Vinculo.objects.filter(pessoa__pessoafisica__cpf=data['sub'], user__is_active=True).values_list('pk', flat=True)
        if len(splitted_name) > 1:
            last_name = splitted_name[-1]
        photo = (
            requests.get(data['picture'], headers=headers, timeout=settings.REQUESTS_TIMEOUT).content
            if data['picture']
            and Vinculo.objects.filter(pessoa__pessoafisica__cpf=mask_cpf(data['sub'])).filter(Q(foto='') | Q(foto__isnull=True)).exists()
            else None
        )
        user_data = {
            'username': data['sub'],
            'first_name': first_name.strip(),
            'last_name': last_name.strip(),
            'name': data['name'],
            'email': data['email'],
            'email_verified': data['email_verified'],
            'phone_number': data.get('phone_number', ''),
            'confiabilidade_govbr': user_confiability_level(data['sub'], token_response_data['access_token']),
            'vinculos_ativos_ids': list(vinculos_ativos_ids),
            'photo': photo,
            'token': {
                'access_token': token_response_data['access_token'],
                'decoded_data': self.decode_access_token(token_response_data['access_token']),
            },
        }
        logger.debug(f'Returning user data {user_data}')
        return user_data

    def create_user(self, user_data: dict) -> User:
        logger.debug(f'Creating user {user_data["username"]} with confiability level {user_data["confiabilidade_govbr"]}...')
        if user_data['confiabilidade_govbr'] in ('1', '2', '3'):
            cpf = mask_cpf(user_data['username'])
            pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': cpf, 'nome': user_data['name']}, Politica.PREENCHER)
            prestador_servico = PrestadorServico.objects.create(
                pessoa_fisica=pessoa_fisica, ativo=True, justificativa_cadastro=JustificativaUsuarioExterno.objects.first()
            )
            vinculo = prestador_servico.vinculos.first()
            # email migrou de Pessoa para Vinculo; grava o e-mail do gov.br no vínculo recém-criado.
            vinculo.email_pessoal = user_data['email']
            vinculo.save(update_fields=['email_pessoal'])
            logger.debug('User successfully created!')
            return vinculo.user
        raise Exception('Grau de confiabiliade inválida.')

    def update_user(self, user: User, user_data: dict) -> None:
        logger.debug(f'Consulting personal data for user {user}...')
        api = APIExterna.PESSOAFISICA
        dados_cidadao = []
        obj = PessoaInfoComplementar.get_instance(user.get_profile(), api, force=False)
        if obj:
            dados_cidadao = obj.informacoes
        sucesso = len(dados_cidadao) > 0 and 'mensagem' not in dados_cidadao[0]
        logger.debug(f'Personal data for user {user} received {dados_cidadao}')
        sexo = {1: 'M', 2: 'F', 3: None}
        if sucesso:
            logger.debug(f'Updating personal data for user {user}...')
            dados_cidadao = dados_cidadao[0]
            pessoa_fisica = user.get_profile()
            vinculo = user.get_vinculo()
            pessoa_fisica.nome_registro = dados_cidadao.get('Nome', None)
            try:
                nascimento_data = datetime.strptime(dados_cidadao.get('DataNascimento', None), '%Y%m%d').date()
            except Exception:
                nascimento_data = None
            # o governo é autoritativo, mas um dado vazio/ilegível não apaga o que a pessoa já tem
            dados_civis = {
                'sexo': sexo.get(dados_cidadao.get('Sexo')),
                'nome_mae': dados_cidadao.get('NomeMae', None),
                'nome_pai': dados_cidadao.get('NomePai', None),
                'nascimento_data': nascimento_data,
            }
            aplicar_politica(pessoa_fisica, dados_civis, Politica.AUTORITATIVA)
            if user_data['photo'] and vinculo and not vinculo.foto:
                image = Image.open(BytesIO(user_data['photo']))
                image_buffer = BytesIO()
                image.save(image_buffer, format='PNG')
                vinculo.foto.save(f'{user.get_profile().cpf}.jpg', ContentFile(image_buffer.getvalue()), save=True)
            pessoa_fisica.save()
            logger.debug(f'Updating address data for user {user}...')
            municipio = Municipio.objects.filter(uf=dados_cidadao.get('UF', None), nome__iexact=dados_cidadao.get('Municipio', None)).first()
            if not municipio:
                municipio = Municipio.objects.filter(uf=dados_cidadao.get('UF', None), nome__icontains=dados_cidadao.get('Municipio', None)).first()

            endereco_params = {
                'pessoa_id': pessoa_fisica.id,
                'logradouro': dados_cidadao.get('Logradouro'),
                'numero': dados_cidadao.get('NumeroLogradouro'),
                'bairro': dados_cidadao.get('Bairro'),
                'cep': dados_cidadao.get('Cep'),
                'municipio': municipio,
            }
            try:
                PessoaEndereco.objects.get_or_create(**endereco_params)
            except Exception:
                # Mais de um endereço encontrado, o que não deveria acontecer. Deletar os endereços duplicados.
                queryset = PessoaEndereco.objects.filter(**endereco_params)
                queryset.exclude(id=queryset.first().id).delete()
            logger.debug(f'User {user} successfully updated!')

    def update_session(self, request, user_data):
        logger.debug('Registering govbr authentication into session...')
        request.session['autenticou_com_govbr'] = True
        logger.debug(f'Registering confiability level {user_data["confiabilidade_govbr"]} into session...')
        request.session['confiabilidade_govbr'] = user_data['confiabilidade_govbr']
        logger.debug(f'Storing token data {user_data["confiabilidade_govbr"]} into session...')
        request.session['token_govbr'] = user_data['token']

    def login(self, request):
        token_response_data = self.get_token_data(request.GET['code'])
        user_data = self.get_user_data(token_response_data)
        vinculos = Vinculo.objects.filter(pessoa__pessoafisica__cpf=mask_cpf(user_data['username']), user__is_active=True).order_by(
            '-user__last_login'
        )
        vinculo = vinculos.filter(user__username=user_data['username']).first() or vinculos.first()
        if vinculo:
            user = vinculo.user
        else:
            logger.debug(f'User with username {user_data["username"]} was not found.')
            if settings.GOVBR['USER_AUTO_CREATE']:
                user = self.create_user(user_data)
            else:
                raise Exception('Usuário não localizado no SUAP.')
        if settings.GOVBR['USER_AUTO_UPDATE']:
            self.update_user(user, user_data)
        self.update_session(request, user_data)
        auth.login(request, user, backend='djtools.contrib.auth.backends.ModelBackendPlus')
        OauthLogin.objects.create(user=user, data_hora=datetime.now(), dados={k: v for k, v in user_data.items() if k != 'photo'})
        # Havendo mais de um vínculo, a seleção precisa acontecer antes de seguir para o destino
        # (senão o usuário é autenticado com o vínculo de último acesso, sem poder escolher).
        if vinculos.count() > 1:
            return redirect('/comum/selecionar_vinculo/')
        return redirect(destino_pos_autenticacao(request))

    def logout(self, request):
        url = settings.GOVBR['LOGOUT_URL']
        logger.debug('Logging out and redirecting to {url}')
        auth.logout(request)
        return redirect(url)

    def __call__(self, request):
        # Caso govbr seja o login principal do SUAP, salvar a URL que o usuário tentou abrir e redirecionar para login com código de autorização vazio
        if (settings.GOVBR['PRIMARY_LOGIN'] or 'govbr' in request.GET) and request.path == '/accounts/login/' and 'next' in request.GET:
            response = redirect('/accounts/login/?code=&govbr=1')
            response.set_cookie('auth_redirect_url', request.GET['next'], max_age=360)
            return response
        # Caso o código de autorização esteja vazio, redicionar para o govbr. Senão, proceder com o login.
        elif request.path == '/accounts/login/' and 'code' in request.GET:
            try:
                return self.login(request) if request.GET['code'] else self.redirect(request)
            except Exception as e:
                messages.error(request, f'Problema a efetuar login: {e}')
                return self.get_response(request)
        elif request.path == '/accounts/logout/':
            return self.logout(request)
        else:
            return self.get_response(request)
