import xmlrpc.client
from typing import Any
from xmlrpc.server import SimpleXMLRPCDispatcher

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from comum.models import User, Vinculo
from comum.utils import tl
from djtools.templatetags.filters import in_group
from djtools.utils import get_client_ip
from rh.models import PessoaFisica, Servidor


def _eh_maquina_de_cadastro() -> bool:
    """A requisição vem de uma ``Maquina`` ativa com o papel de cadastro de digitais?"""
    if 'ponto' not in settings.INSTALLED_APPS:
        return False
    from ponto.models import Maquina

    ip = get_client_ip(tl.get_request())
    return Maquina.objects.filter(ip=ip, ativo=True, cliente_cadastro_impressao_digital=True).exists()


def login(username: str, senha: str | None = None) -> dict[str, Any]:
    """
    Realiza o login

    O terminal autentica o operador localmente (digital) e chama sem senha antes de
    ``cadastrar_template``; por isso a chamada só é aceita de máquina de cadastro de digitais,
    o que impede a enumeração de usuários de fora dos terminais (#17407).
    """
    if not _eh_maquina_de_cadastro():
        return {'ok': False, 'msg': 'Máquina sem permissão para cadastro de impressões digitais'}
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return {'ok': False, 'msg': 'Usuário inválido'}
    if not user.is_active:
        return {'ok': False, 'msg': 'Usuário inativo'}
    if senha and not user.check_password(senha):
        return {'ok': False, 'msg': 'Senha incorreta'}

    return {'ok': True, 'msg': 'Login realizado com sucesso', 'session_pk': username}


def logout(chave):
    """
    Realiza o logout
    """
    return {'ok': True}


def cadastrar_template(
    session_pk: str, pessoa_id: int, template: xmlrpc.client.Binary, client_encoding: str = 'latin-1', db_encoding: str = 'utf-8'
) -> dict[str, Any]:
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}

    from ponto.models import Maquina, MaquinaLog

    try:
        ip = get_client_ip(tl.get_request())
        maquina = Maquina.objects.get(ip=ip, cliente_cadastro_impressao_digital=True)
    except Maquina.DoesNotExist:
        msg = 'Máquina sem permissão para cadastro de impressões digitais'
        return {'ok': False, 'msg': msg}

    MaquinaLog.objects.create(maquina=maquina, operacao='comum_cadastrar_template')

    try:
        user = User.objects.get(username=session_pk)
    except Exception:
        return {'ok': False, 'msg': 'Sua sessão expirou. Faça o login novamente.'}

    if not (user.has_perm('rh.pode_cadastrar_digital') or user.has_perm('rh.pode_atualizar_digital')):
        return {'ok': False, 'msg': 'Usuário sem permissões para cadastrar digitais'}

    # Operador com digital fraca entra no terminal legado por senha local, nunca conferida com o
    # SUAP (qualquer senha na 1ª vez); o terminal não pode ser atualizado, então a recusa é aqui (#17482).
    operador = user.get_profile()
    if operador and operador.tem_digital_fraca:
        return {'ok': False, 'msg': 'Operador com digital fraca não pode cadastrar digitais pelo terminal'}

    try:
        vinculo = Vinculo.objects.do_terminal(pessoa_id)
        pessoa_fisica = PessoaFisica.objects.get(id=vinculo.pessoa_id if vinculo else pessoa_id)
    except Vinculo.DoesNotExist, PessoaFisica.DoesNotExist:
        return {'ok': False, 'msg': 'Pessoa não encontrada'}

    if bool(pessoa_fisica.get_template()):
        if not (user.has_perm('rh.pode_cadastrar_digital') and user.has_perm('rh.pode_atualizar_digital')):
            return {'ok': False, 'msg': 'Usuário sem permissões para sobrescrever digitais'}

    # Salvando o ``template``

    if settings.USA_LEITOR_BIOMETRICO_GRIAULE:
        pessoa_fisica.template = template.data.decode(client_encoding).encode(db_encoding)
    else:
        pessoa_fisica.template = template.data
    pessoa_fisica.template_importado_terminal = True
    pessoa_fisica.save()
    return {'ok': True, 'msg': 'Impressão digital cadastrada com sucesso'}


def get_dados_pessoa(login: str, template_encoding: str = 'latin-1') -> dict[str, Any]:
    # TODO: usar ``values`` para evitar carregamento de colunas desnecessárias
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}
    from ponto.models import Maquina, MaquinaLog

    try:
        ip = get_client_ip(tl.get_request())
        maquina = Maquina.objects.get(ip=ip, ativo=True)
    except Maquina.DoesNotExist:
        msg = 'Máquina sem permissão para acessar o Web Service'
        return {'ok': False, 'msg': msg}

    MaquinaLog.objects.create(maquina=maquina, operacao='comum_get_dados_pessoa')

    user = User.objects.filter(username=login).first()
    pf = None
    if user:
        pf = user.get_profile()

    if pf:
        try:
            servidor = Servidor.objects.get(matricula=login)
            matricula = login
            setor = servidor.setor.sigla
        except Exception:
            matricula = ''
            setor = ''

        pode_cadastrar_digital_com_qualidade_media = user and (
            user.has_perm('rh.pode_cadastrar_digital') and user.has_perm('rh.pode_atualizar_digital')
        )

        template_str = pf.get_template(encoding=template_encoding) or ''
        tem_impressao_digital = bool(template_str)
        is_superuser = user and user.is_superuser
        operador_chave = user and in_group(user, 'Operador de Chaves, Coordenador de Chaves Sistêmico')

    else:
        usuarios = User.objects.filter(username=login)
        if len(usuarios) > 0 and usuarios[0].is_superuser:
            # O usário tentando logar é um 'super usuário', então uma pessoa física será criada para ele
            pf = PessoaFisica()
            pf.pk = -1
            pf.nome = 'Administrador'
            pf.cpf = ''
            pf.tem_digital_fraca = False
            tem_impressao_digital = False
            pode_cadastrar_digital_com_qualidade_media = True
            template_str = ''
            matricula = ''
            setor = ''
            is_superuser = True
            operador_chave = False
        # Não há pessoa física associada ao usuário e ele não é o 'admin'
        else:
            return {'ok': False, 'msg': 'Pessoa não encontrada'}

    # Ensure template is bytes before wrapping in xmlrpc.client.Binary
    if isinstance(template_str, str):
        try:
            template_bytes = template_str.encode(template_encoding)
        except Exception:
            template_bytes = template_str.encode('utf-8', errors='ignore')
    else:
        template_bytes = template_str or b''

    dados = {
        'ok': True,
        'msg': 'Pessoa encontrada',
        'pessoa_id': pf.pk,
        'nome': pf.nome,
        'cpf': pf.cpf or '',
        'matricula': matricula,
        'login': matricula or '',
        'foto_url': pf.get_foto_url_publica(),
        'tem_impressao_digital': tem_impressao_digital,
        'setor': setor,
        'tem_digital_fraca': pf.tem_digital_fraca,
        'pode_cadastrar_digital_com_qualidade_media': pode_cadastrar_digital_com_qualidade_media,
        'template': xmlrpc.client.Binary(data=template_bytes),
        'is_superuser': is_superuser,
        'operador_chave': operador_chave,
    }
    return dados


def meu_ip():
    """
    Retorna informações sobre a máquina requisitante
    """
    return {
        'ip': get_client_ip(tl.get_request()),
        'is_terminal_ponto': is_terminal_ponto()['is_terminal_ponto'],
        'is_terminal_cadastro': is_terminal_cadastro()['is_terminal_cadastro'],
        'is_terminal_chaves': is_terminal_chaves()['is_terminal_chaves'],
        'is_terminal_refeitorio': is_terminal_refeitorio()['is_terminal_refeitorio'],
    }


def is_terminal_ponto():
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}
    from ponto.models import Maquina

    try:
        maquina = Maquina.objects.get(ip=get_client_ip(tl.get_request()), ativo=True)
        return {'ok': True, 'is_terminal_ponto': maquina.cliente_ponto}
    except Maquina.DoesNotExist:
        return {'ok': False, 'is_terminal_ponto': False}


def is_terminal_cadastro():
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}
    from ponto.models import Maquina

    try:
        maquina = Maquina.objects.get(ip=get_client_ip(tl.get_request()), ativo=True)
        return {'ok': True, 'is_terminal_cadastro': maquina.cliente_cadastro_impressao_digital}
    except Maquina.DoesNotExist:
        return {'ok': False, 'is_terminal_cadastro': False}


def is_terminal_chaves():
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}
    from ponto.models import Maquina

    try:
        maquina = Maquina.objects.get(ip=get_client_ip(tl.get_request()), ativo=True)
        return {'ok': True, 'is_terminal_chaves': maquina.cliente_chaves}
    except Maquina.DoesNotExist:
        return {'ok': False, 'is_terminal_chaves': False}


def is_terminal_refeitorio():
    if 'ponto' not in settings.INSTALLED_APPS:
        msg = 'A aplicação de Ponto não está instalada no SUAP'
        return {'ok': False, 'msg': msg}
    from ponto.models import Maquina

    try:
        maquina = Maquina.objects.get(ip=get_client_ip(tl.get_request()), ativo=True)
        return {'ok': True, 'is_terminal_refeitorio': maquina.cliente_refeitorio}
    except Maquina.DoesNotExist:
        return {'ok': False, 'is_terminal_refeitorio': False}


comum_exposed = [
    [login, 'login'],
    [logout, 'logout'],
    [get_dados_pessoa, 'get_dados_pessoa'],
    [cadastrar_template, 'cadastrar_template'],
    [meu_ip, 'meu_ip'],
    [is_terminal_ponto, 'is_terminal_ponto'],
    [is_terminal_cadastro, 'is_terminal_cadastro'],
    [is_terminal_chaves, 'is_terminal_chaves'],
    [is_terminal_refeitorio, 'is_terminal_refeitorio'],
]

dispatcher = SimpleXMLRPCDispatcher(allow_none=False, encoding=None)


def rpc_handler(request):
    """
    the actual handler:
    if you setup your urls.py properly, all calls to the xml-rpc service
    should be routed through here.
    If post data is defined, it assumes it's XML-RPC and tries to process as such
    Empty post assumes you're viewing from a browser and tells you about the service.
    """
    response = HttpResponse()
    data = None
    if 'body' in request.POST:  # hack para testes unitários
        data = request.POST['body']
    elif request.body:  # fluxo normal (chamada do webservice)
        data = request.body

    if data:
        response.write(dispatcher._marshaled_dispatch(data))

    # tela de apresentação do webservice, listando os métodos disponíveis
    else:
        response.write('<h2>This is an XML-RPC Service</h2>')
        response.write('<p>You need to invoke it using an XML-RPC Client!</p>')
        response.write('<p>The following methods are available:</p>')
        methods = dispatcher.system_listMethods()
        for method in methods:
            sig = dispatcher.system_methodSignature(method)
            help_ = dispatcher.system_methodHelp(method)
            response.write(f'<li><strong>{method}</strong>: [{sig}] {help_}')
        response.write('</ul>')
        response.write('<p><a href="http://www.djangoproject.com/"><img src="/static/comum/img/django.gif" alt="Feito com Django" /></a></p>')

    response['Content-length'] = str(len(response.content))
    return response


rpc_handler = csrf_exempt(rpc_handler)


EXPOSED_FUNCTIONS = [comum_exposed]
if 'ponto' in settings.INSTALLED_APPS:
    from ponto.webservice import exposed as ponto_exposed

    EXPOSED_FUNCTIONS.append(ponto_exposed)

if 'ae' in settings.INSTALLED_APPS:
    from ae.webservice import exposed as ae_exposed

    EXPOSED_FUNCTIONS.append(ae_exposed)

if 'chaves' in settings.INSTALLED_APPS:
    from chaves.webservice import exposed as chaves_exposed

    EXPOSED_FUNCTIONS.append(chaves_exposed)

if 'protocolo' in settings.INSTALLED_APPS:
    from protocolo.webservice import exposed as protocolo_exposed

    EXPOSED_FUNCTIONS.append(protocolo_exposed)

if 'patrimonio' in settings.INSTALLED_APPS:
    from patrimonio.webservice import exposed as patrimonio_exposed

    EXPOSED_FUNCTIONS.append(patrimonio_exposed)


for app_exposed_functions in EXPOSED_FUNCTIONS:
    for item in app_exposed_functions:
        function, exposed_name = item
        dispatcher.register_function(function, exposed_name)
