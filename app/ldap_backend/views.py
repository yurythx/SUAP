import datetime
import urllib
import urllib.parse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from comum.models import Configuracao, Vinculo
from djtools import layout
from djtools.utils import httprr, is_ldap_write_enabled, permission_required, requests, rtr
from rh.models import Setor

from . import tasks

#
from .forms import ExpirarSenhaLoteForm, SearchForm, SelecaoEmailForm
from .models import LdapConf, LdapGroup, LdapUser
from .utils import get_tipos_email_disponiveis


@layout.notificacoes_importantes()
def index_notificacoes_importantes(request: HttpRequest) -> list[str]:
    notificacoes_importantes = []
    username = request.user.username if request.user.is_authenticated else None
    accountExpires = request.session.get(f'adAccountExpires_{username}', False)
    if accountExpires and username:
        accountExpires = datetime.datetime.fromisoformat(accountExpires)
        data_hora_expira = None
        hoje = datetime.datetime.today()
        data_hora_expira = accountExpires
        if data_hora_expira > hoje and (data_hora_expira - hoje).days < 90:
            # Sem sigla configurada, texto neutro em vez de "com o None" (#17472).
            sigla = Configuracao.get_valor_por_chave_str('comum', 'instituicao_sigla')
            com_instituicao = f'com o {sigla}' if sigla else 'com a instituição'
            da_instituicao = f'do {sigla}' if sigla else 'da instituição'
            notificacoes_importantes.append(
                f'Seu vínculo - {username} - {com_instituicao} será desativado nos sistemas no dia {data_hora_expira.strftime("%d/%m/%Y")}. Após essa data, você não poderá mais acessar o SUAP e demais sistemas {da_instituicao} com sua senha, além de perder o acesso aos e-mails institucionais.'
            )
    return notificacoes_importantes


@layout.info()
def index_infos(request):
    infos = []
    for tipo, label in list(get_tipos_email_disponiveis(request.user).items()):
        url = f'/ldap_backend/escolher_email/{tipo}/'
        titulo = f'Escolha seu email {label}.'
        infos.append({'url': url, 'titulo': titulo})
    return infos


@rtr()
@permission_required('ldap_backend.view_ldap_user')
def search(request, pk):
    ldap_conf = get_object_or_404(LdapConf, pk=pk)
    form = SearchForm(request.POST or None, ldap_conf=ldap_conf)
    parameters = form.get_attrlist()
    if form.is_valid():
        try:
            objects = form.search()
        except Exception as e:
            error = str(e)
        return locals()
    return locals()


@rtr()
@permission_required('ldap_backend.view_ldap_user')
def show_object(request, username):
    ldap_conf = LdapConf.get_active()
    vinculo = Vinculo.objects.filter(user__username=username).first()
    if not vinculo:
        return httprr('..', 'Usuário inexistente', 'error')
    pf = vinculo.pessoa.pessoafisica
    obj = ldap_conf.get_user(username)
    keys = sorted(obj.keys())
    title = f'Usuário {username} ({ldap_conf.get_solucao_display()})'
    return locals()


@rtr()
@permission_required('ldap_backend.view_ldap_user')
def show_ou_setor(request, setor_id):
    ldap_conf = LdapConf.get_active()

    obj = ldap_conf.get_ou_by_admin_description(setor_id)
    if not obj:
        return httprr('..', 'Unidade Organizacional inexistente', 'error')
    else:
        obj = obj[0]
    keys = sorted(obj.keys())
    ou_name = obj.get('ou')
    ou_name_display = ou_name[0].decode() if ou_name and len(ou_name) > 0 else ''
    title = f'Unidade Organizacional {ou_name_display} ({ldap_conf.get_solucao_display()})'
    users = ldap_conf.get_users_by_ou(obj.get('dn'), attrlist=['cn', 'description'])
    return locals()


@rtr()
@permission_required('ldap_backend.sync_ldap_user')
def sync_user(request, username):
    try:
        ldap_conf = LdapConf.get_active()
        vinculo = Vinculo.objects.filter(user__username=username).first()
        if vinculo:
            if vinculo.setor:
                ldap_conf.sync_ou_setor(vinculo.setor, test_mode=False)
            ldap_conf.sync_user(username)
        else:
            return httprr('..', 'Usuário inexistente.', 'error')
        return httprr(request.META.get('HTTP_REFERER', '..'), 'Usuário sincronizado com sucesso.')
    except Exception as e:
        if settings.DEBUG:
            raise e
        return httprr('..', str(e), 'error')


@rtr()
@permission_required('ldap_backend.sync_ldap_user')
def sync_ou_setor(request, setor_id):
    try:
        setor = get_object_or_404(Setor, pk=setor_id)
        ldap_conf = LdapConf.get_active()
        ldap_conf.sync_ou_setor(setor, test_mode=False, force=True)
        return httprr(request.META.get('HTTP_REFERER', '..'), 'Unidade Organizacional sincronizada com sucesso.')
    except Exception as e:
        if settings.DEBUG:
            raise e
        return httprr(f'/ldap_backend/show_ou_setor/{setor_id}/', str(e), 'error')


@rtr()
@login_required
def escolher_email(request, tipo):
    tipos_email_disponiveis = get_tipos_email_disponiveis(request.user)
    if tipo not in tipos_email_disponiveis:
        raise PermissionDenied

    if not is_ldap_write_enabled():
        return httprr('/', 'Não é possível definir o email do usuário sem permissão de escrita no LDAP.', 'error')

    instance = request.user.get_vinculo().relacionamento
    title = f'Escolha seu E-mail {tipos_email_disponiveis[tipo]}'
    form = SelecaoEmailForm(request.user.get_profile(), tipo, data=request.POST or None, request=request)
    if form.is_valid():
        # Atribuindo o email de acordo com o tipo do domínio selecionado
        setattr(instance, f'email_{tipo}', form.cleaned_data['email'])
        try:
            form.processar(instance, request.user.username)
        except Exception:
            return httprr('/', f'Erro ao tentar definir email "{form.cleaned_data["email"]}". Por favor tente novamente.', 'error')
        return httprr('/', 'O email "{}" foi definido com sucesso e estará disponível para uso em 3 horas.'.format(form.cleaned_data['email']))
    return locals()


@rtr()
@login_required
def redirecionar_google_classroom(request):
    relacionamento = request.user.get_relacionamento()
    if not relacionamento.email_google_classroom or (request.user.eh_prestador and not request.user.has_group_cached('Usuários do Google Classroom')):
        return httprr('..', 'Você não tem permissão para isso.', 'error')
    utilizar_saml2idp_outra_maquina = Configuracao.get_valor_por_chave('ldap_backend', 'utilizar_saml2idp_outra_maquina')
    dominio_google_classroom = Configuracao.get_valor_por_chave('ldap_backend', 'dominio_google_classroom')
    url_saml2idp = Configuracao.get_valor_por_chave('ldap_backend', 'url_saml2idp')
    email_usuario = request.user.get_relacionamento().email_google_classroom
    SAMLRequest = request.GET.get('SAMLRequest')
    RelayState = request.GET.get('RelayState')

    if utilizar_saml2idp_outra_maquina:
        if not SAMLRequest:
            return httprr(f'https://accounts.google.com/AccountChooser?hd={dominio_google_classroom}&continue=https://classroom.google.com')
        else:
            url_params = {'SAMLRequest': SAMLRequest, 'RelayState': RelayState, 'email_usuario': email_usuario}

            try:
                url = f'{url_saml2idp}?{urllib.parse.urlencode(url_params)}'
                resposta_saml2idp = requests.get(url, timeout=settings.REQUESTS_TIMEOUT).json()
                response_url = resposta_saml2idp['response_url']
                saml_response = resposta_saml2idp['SAMLResponse']
                token = resposta_saml2idp['RelayState']

                return locals()
            except Exception:
                return HttpResponse('Não foi possível processar a requisição.')
    else:
        if not SAMLRequest:
            return httprr(f'https://accounts.google.com/AccountChooser?hd={dominio_google_classroom}&continue=https://classroom.google.com')
        else:
            return redirect(f'/saml2idp/?SAMLRequest={urllib.parse.quote_plus(SAMLRequest)}&RelayState={urllib.parse.quote_plus(RelayState)}')


@login_required
def logout_google_classroom(request):
    if 'autenticou_google_sso' in request.session:
        del request.session['autenticou_google_sso']
        return httprr('/', 'Você foi desconectado do Google Sala de Aula com sucesso.')
    else:
        return httprr('/')


@rtr('ldap_backend/templates/groups/change.html')
@login_required
def ldap_group_change_view(request, group_name):
    if 'ldap_backend.router.SuapRouter' not in settings.DATABASE_ROUTERS:
        raise Http404
    #
    ldap_conf = LdapConf.get_active()
    group = LdapGroup.objects.get(cn=group_name)
    form = SearchForm(request.POST or None, ldap_conf=ldap_conf)
    if form.is_valid():
        objects = form.search()
        for object in objects:
            object.is_member = group.is_member(object)
    #
    return locals()


@rtr()
@login_required
def ldap_add_member_view(request, gid, uid):
    if 'ldap_backend.router.SuapRouter' not in settings.DATABASE_ROUTERS:
        raise Http404
    ldap_group = get_object_or_404(LdapGroup, cn=gid)
    ldap_user = get_object_or_404(LdapUser, uid=uid)
    ldap_group.add_member(ldap_user)
    return httprr('..', f'Usuário {ldap_user} adicionado ao grupo {ldap_group.name} com sucesso.')


@rtr()
@login_required
def ldap_remove_member_view(request, gid, uid):
    if 'ldap_backend.router.SuapRouter' not in settings.DATABASE_ROUTERS:
        raise Http404
    #
    ldap_group = get_object_or_404(LdapGroup, cn=gid)
    ldap_user = get_object_or_404(LdapUser, uid=uid)
    ldap_group.remove_member(ldap_user)
    return httprr('..', f'Usuário {ldap_user} removido do grupo {ldap_group.name} com sucesso.')


@rtr()
@login_required
def expirar_senhas_em_lote(request):
    title = 'Expirar senhas em lote'
    if not request.user.has_group_cached(['Coordenador de TI sistêmico']):
        raise PermissionDenied
    form = ExpirarSenhaLoteForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        return tasks.expirar_senhas_em_lote(form.usuarios, form.cleaned_data.get('simular', True), form.cleaned_data.get('forcar_expiracao', False))
    return locals()
