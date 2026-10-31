import datetime
import json
import os

import magic
from django.apps import apps
from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models.manager import Manager
from django.db.models.sql.query import Query
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from pycpfcnpj import cpfcnpj
from sentry_sdk import capture_exception

from comum.models import APIExterna, Configuracao, GerenciamentoGrupo, Municipio, User
from comum.utils import get_setor, get_uo
from djtools import HELP_XML_CONTENTS, tasks
from djtools.contrib.auth.helpers import has_delete_permission
from djtools.forms import (
    AccessLogForm,
    AtribuirPermissaoForm,
    AutocompleteDiagnosticsForm,
    EmailLogForm,
    HistoryForm,
    NotificacaoGrupoForm,
    RestaurarArquivosMediaForm,
    TwoFactorAuthenticationForm,
)
from djtools.models import PushSubscription, Task
from djtools.storages import is_remote_storage
from djtools.utils import (
    JsonResponse,
    decrypt,
    force_utf8_string,
    generate_file_response,
    get_opensearch_query_access_logs,
    get_opensearch_query_history,
    httprr,
    permission_required,
    random_with_N_digits,
    requests,
    rtr,
    running_tests,
    send_mail,
    timeless_load_qs_query,
)
from djtools.utils.autocomplete import (
    _generic_search_json_response,
    diagnostic_entries_for_model,
    diagnostic_params_from_form,
    filter_diagnostics_report,
    should_skip_diagnostic_model,
    summarize_diagnostics_report,
)
from djtools.utils.help import get_item
from rh.models import Pessoa
from rh.utils import estah_no_pgd_hoje_pgd1_pgd2


@login_required
@rtr()
def help_view(request, app, view):
    item = get_item(request, app, view, True)
    if item:
        title = 'Ajuda: {}'.format(item['name'])
        actions = []
        for action in item['actions']:
            if action.__class__ is dict and len(list(action.keys())) > 2:
                sub_item = action
            else:
                sub_item = action['view'] in HELP_XML_CONTENTS and HELP_XML_CONTENTS[action['view']] or None
                if 'tip' in action:
                    sub_item['tip'] = action['tip']
            if sub_item:
                if not sub_item.get('groups'):
                    sub_item['groups'] = item['groups']
                actions.append(sub_item)
        required_to = []
        for ref in item['required_to']:
            required_app, required_view = ref.split('.')
            if '#' in ref:
                sub_item = ref in HELP_XML_CONTENTS and HELP_XML_CONTENTS[ref] or None
            else:
                sub_item = get_item(request, required_app, required_view)
            if sub_item:
                required_to.append(sub_item)

    return locals()


def arquivo(request, app, model, pk, attr_name):
    """
    Função utilizada para possibilitar o acesso de arquivos de media sem autenticação caso o storage S3 esteja sendo utilizado.
    Para tal, é necessário definir o atributo can_view no campo relacionada ao FileFieldPlus.
    Ex: arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='arquivos', can_view=True)
        ou
        arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='arquivos', can_view='can_view_arquivo)
        def can_view_arquivo(self, user):
            pass
    """
    try:
        obj = get_object_or_404(apps.get_model(app, model).objects, pk=pk)
        field = obj._meta.get_field(attr_name)
        if field.can_view and (field.can_view is True or getattr(obj, field.can_view)(request.user)):
            file = getattr(obj, attr_name)
            url = file.url
            return redirect(url)
    except Exception as e:
        if settings.DEBUG:
            raise e
    raise PermissionDenied


def arquivo_uuid(request, app, model, uuid, attr_name, size=None):
    """
    Função utilizada para possibilitar o acesso de arquivos de fotos sem autenticação caso o storage S3 esteja sendo utilizado.
    Para tal, é necessário que o modelo possua um atributo chamado uuid
    Ex: arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='arquivos', can_view=True)
        ou
        foto = ImageWithThumbsField(upload_to="fotos", sizes=((75, 100), (150, 200)), null=True, blank=True)
    """
    try:
        obj = get_object_or_404(apps.get_model(app, model).objects, uuid=uuid)
        file = getattr(obj, attr_name)
        attr_url = f'url_{size}' if size else 'url'
        url = getattr(file, attr_url)
        return redirect(url)
    except Exception as e:
        if settings.DEBUG:
            raise e
    raise PermissionDenied


def delete_object(request, app, model, pk):
    """
    View genérica para remover um objeto de modelo.
    -----
    Parâmetro opcional no GET: ``redirect_url``.
    """

    # Pegando a classe de modelo e o objeto
    model_class = apps.get_model(app, model)
    obj = get_object_or_404(model_class, pk=pk)

    if not has_delete_permission(obj=obj, user=request.user):
        raise PermissionDenied

    # Removendo o objeto
    obj.delete()

    # redirect_url
    if 'redirect_url' in request.GET:
        redirect_url = request.GET['redirect_url']
    else:
        redirect_url = request.META.get('HTTP_REFERER', '/')

    # msg
    msg_args = {'name': model_class._meta.verbose_name.title(), 'obj': str(obj)}
    msg = '{name} "{obj}" foi removido com sucesso.'.format(**msg_args)

    return httprr(redirect_url, msg)


@rtr()
@login_required()
@permission_required('auth.can_change_user')
def give_permission(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    elif request.method == 'POST' and 'confirmacao' not in request.POST:
        form = AtribuirPermissaoForm(data=request.POST)
        if form.is_valid():
            usuarios = form.cleaned_data['usuarios']
            usuarios = usuarios.replace(',', ';').replace('\r\n', ';')
            grupos = form.cleaned_data['grupos']
            permissoes = form.cleaned_data['permissoes']
            lista_usuarios = []
            lista_usuarios_nao_identificados = []
            for login in usuarios.split(';'):
                if login:
                    login = login.strip()
                    usuario_qs = User.objects.filter(username=login)
                    if usuario_qs:
                        lista_usuarios.append(usuario_qs[0])
                    else:
                        lista_usuarios_nao_identificados.append(login)
            lista = []
            for usuario in lista_usuarios:
                lista.append(str(usuario.pk))
            usuarios_str = ';'.join(lista)
            lista = []
            for grupo in grupos:
                lista.append(str(grupo.pk))
            grupos_str = ';'.join(lista)
            lista = []
            for permissao in permissoes:
                lista.append(str(permissao.pk))
            permissoes_str = ';'.join(lista)
    elif request.method == 'POST' and 'confirmacao' in request.POST:
        form = AtribuirPermissaoForm()
        usuarios_str = request.POST['usuarios']
        grupos_str = request.POST['grupos']
        permissoes_str = request.POST['permissoes']

        grupos = []
        for id in grupos_str.split(';'):
            if id:
                grupos.append(Group.objects.get(pk=id))
        permissoes = []
        for id in permissoes_str.split(';'):
            if id:
                permissoes.append(Permission.objects.get(pk=id))
        for id in usuarios_str.split(';'):
            usuario = User.objects.get(pk=id)
            for grupo in grupos:
                usuario.groups.add(grupo)
            for permissao in permissoes:
                usuario.user_permissions.add(permissao)
            usuario.save()
        httprr('/djtools/give_permission/', 'Permissões atribuídas com sucesso')
    else:
        form = AtribuirPermissaoForm()
    return locals()


def breadcrumbs_reset(request, menu_item_id, url):
    query_string = request.META.get('QUERY_STRING', '')
    for model_name in settings.ADMIN_FILTER_REQUIRED_MODELS:
        if url.startswith('admin') and model_name in url:
            query_string = None
    if query_string:
        url += f'?{query_string}'
    bc = [['Início', '/']]
    request.session['bc'] = bc
    request.session['menu_item_id'] = menu_item_id
    return HttpResponseRedirect(f'/{url}')


@rtr()
def notificar_grupo(request, pk_grupo):
    title = 'Enviar Mensagem para Grupo'
    grupo = Group.objects.get(pk=pk_grupo)
    gd = grupo.groupdetail_set.first()
    if gd:
        redirect_url = f'/comum/gerenciamento_grupo/?modulo={gd.app}&grupo={grupo.pk}'
    else:
        redirect_url = '/comum/gerenciamento_grupo/'

    if not GerenciamentoGrupo.user_can_manage(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        form = NotificacaoGrupoForm(request.POST, request=request)
        if form.is_valid():
            titulo = form.cleaned_data['titulo']
            remetente = form.cleaned_data['remetente']
            texto = form.cleaned_data['texto']
            return tasks.notificar_usuarios_grupo(titulo, remetente, texto, grupo, redirect_url)
    else:
        form = NotificacaoGrupoForm(request=request)
    return locals()


def manifest(request):
    data = {
        'name': 'SUAP',
        'short_name': 'Sistem Unificado de Administração Pública',
        'lang': 'pt-BR',
        'start_url': settings.SITE_URL,
        'scope': settings.SITE_URL,
        'display': 'standalone',
        'icons': [
            {
                'src': f'{settings.SITE_URL}/static/comum/img/suap.png',
                'sizes': '192x192',
                'type': 'image/png',
            }
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False))


@csrf_exempt
def push_web_notification_subscription(request):
    data = json.loads(request.POST.get('subscription', 'null'))
    device = request.META.get('HTTP_USER_AGENT', '')
    if not data or not device:
        return HttpResponseForbidden()
    qs = PushSubscription.objects.filter(user=request.user, device=device)
    if qs.exists():
        qs.update(data=data)
    else:
        PushSubscription.objects.create(user=request.user, data=data, device=device)
    return HttpResponse('OK')


@csrf_exempt
@login_required
@rtr()
def popup_choice_field(request, name, ids=None):
    lista = ids.split(';') if ids else []

    try:
        multiple = request.POST.get('multiple', 'false').lower() == 'true'
        qs = timeless_load_qs_query(request.POST['qs'])
        list_template = request.POST.get('template', '')
        list_template = decrypt(list_template) if list_template else 'popup_choices.html'
    except Exception:
        raise PermissionDenied

    # Normalização do QuerySet
    if isinstance(qs, Manager):
        qs = qs.all()
    elif isinstance(qs, Query):
        qs = qs.model.objects.all()

    # Título dinâmico
    try:
        titulo = qs.model._meta.verbose_name
    except Exception:
        titulo = 'Opções'

    # Lógica de Filtros (depends)
    data = request.GET
    django_filter_names = data.get('django_filter_names', '').split(',') if 'django_filter_names' in data else None
    filter_pks = data.get('filter_pks', '').split(',') if 'filter_pks' in data else None

    if django_filter_names and filter_pks:
        depends = {}
        for lookup, pk in zip(django_filter_names, filter_pks, strict=False):
            if lookup and pk:
                # Trata filtros '__in' transformando a string em lista
                if lookup.endswith('__in'):
                    pk = pk.split(';')
                depends[lookup] = pk

        if depends:
            qs = qs.filter(**depends).distinct()

    # Se exitir mais de 1000 registros, outro widget deveria ser usado
    qs = qs[0:1000]
    # Marcação de itens selecionados
    for obj in qs:
        obj.checked_ = str(obj.pk) in lista

    return locals()


@rtr()
def process(request, uuid_task):
    from djtools.models import Task

    i = get_object_or_404(Task.objects, uuid=uuid_task)
    if i.user and request.user.pk != i.user_id and not request.user.is_superuser:
        return httprr('/', 'Você não tem permissão para isso.', 'error')
    interval = 5000
    is_testing = running_tests()
    if settings.DEBUG or is_testing:
        interval = 500
    url = request.META.get('HTTP_REFERER', '/')
    title = f'Tarefa {i.id} - {i.type}'
    if request.GET.get('send_email'):
        i.notify = True
        i.save()
        return httprr('/', mark_safe(f'O resultado do processo <a href="/djtools/view_task/{i.id}/">#{i.id}</a> será enviado por notificação.'))
    return locals()


def process_progress(request, download, uuid_task):
    from djtools.models import Task

    i = get_object_or_404(Task.objects, uuid=uuid_task)
    if i.user and request.user != i.user:
        return httprr('/', 'Você não tem permissão para isso.', 'error')
    if int(download) and i.file:
        return generate_file_response(i)
    return HttpResponse('{}::{}::{}::{}::{}'.format(i.percent, i.message or '', i.file or '', i.url or '', i.error or ''))


@rtr()
def view_task(request, pk):
    i = get_object_or_404(Task.objects, id=pk)
    result = i.get_result()
    result_details = i.get_celery_queue_items()
    title = f'Tarefa #{i.id} - {i.type}'

    if request.user.is_superuser and request.GET.get('revoke'):
        i.revoke()
        return httprr('..', 'Tarefa interrompida com sucesso.')

    data_exclusao = datetime.datetime.now() - datetime.timedelta(days=2)

    if request.user != i.user and not request.user.has_group_cached('Desenvolvedor'):
        return httprr('/', 'Você não tem permissão para isso.', 'error')

    if request.GET.get('download'):
        return generate_file_response(i)
    return locals()


@rtr()
@login_required()
def autocomplete_full_diagnostics(request):
    """
    Full diagnostics for autocompletes: for each model that defines
    `get_ext_combo_template` or `EXT_COMBO_RELATED`, render a sample of
    objects twice (raw and with the declared relateds applied) and capture
    DB queries. This reproduces N+1s that only occur during template rendering.
    """
    if not request.user.is_superuser:
        return httprr('/', 'Acesso restrito a superusuários.', 'error')

    # build form from GET so labels are rendered via Django form
    form = AutocompleteDiagnosticsForm(request.GET or None)
    limit, selected_app, declared_choice, only_special = diagnostic_params_from_form(form, request.GET)

    report = []
    for model in django_apps.get_models():
        if should_skip_diagnostic_model(model, selected_app, only_special, declared_choice):
            continue
        report.extend(diagnostic_entries_for_model(model, limit))

    report_filtered = filter_diagnostics_report(report, selected_app, declared_choice)
    summary = summarize_diagnostics_report(report_filtered)

    title = 'Autocomplete full diagnostics'
    return {'title': title, 'report': report_filtered, 'summary': summary, 'request': request, 'form': form}


@rtr()
@login_required()
def user_info(request, user_uuid):
    from comum.models import Vinculo

    user = get_object_or_404(User, uuid=user_uuid)
    eh_pessoafisica = eh_aluno = False
    requisitante_eh_aluno = request.user.get_vinculo().eh_aluno()
    profile = user.get_profile()
    vinculo = user.get_vinculo()
    if profile:
        if profile.eh_estrangeiro or not profile.cpf or not cpfcnpj.validate(profile.cpf):
            vinculos = Vinculo.objects.filter(pessoa__pessoafisica=profile)
        else:
            vinculos = Vinculo.objects.filter(pessoa__pessoafisica__cpf=profile.cpf).order_by('-id', 'ativo')
        tem_mais_de_1_vinculo = vinculos.count() > 1
        vinculos = vinculos.exclude(id=vinculo.id)
        eh_pessoafisica = True
        nome_social = None
        if user.get_relacionamento_title().capitalize() == 'Aluno':
            eh_aluno = True
            nome_social = user.get_relacionamento().get_nome_social_composto()
        nome = nome_social or profile.nome
        email = vinculo.email_notificacao if vinculo else ''
        foto = vinculo.get_foto_75x100_url()
        cargo = user.get_relacionamento_title().capitalize()
        setor = get_setor(user) or ''
        campus = get_uo(user) or ''
    elif hasattr(user, 'pessoajuridica'):
        profile = user.pessoajuridica
        nome = profile.nome
        cnpj = profile.cnpj

    if vinculo.eh_servidor():
        servidor = vinculo.relacionamento
        dia = datetime.datetime.today()
        em_ferias = servidor.estah_de_ferias_ateh(dia)
        ferias_a_comecar = servidor.estah_de_ferias_ateh(dia + datetime.timedelta(days=30))
        afastamento = servidor.estah_afastado_ateh(dia)
        recesso = servidor.estah_em_recesso(dia)
        esta_em_pgd, adesao_pgd = estah_no_pgd_hoje_pgd1_pgd2(servidor)
        if esta_em_pgd:
            from pgd2.models import PlanoIndividualTrabalho, PlanoIndividualTrabalhoAtendimento

            preferencia_contato_pgd = adesao_pgd.get_preferencia_contato_display()
            pits_da_adesao = (
                PlanoIndividualTrabalho.objects.filter(adesao=adesao_pgd).exclude(situacao=PlanoIndividualTrabalho.CANCELADO).order_by('data_inicio')
            )
            horarios_atendimento_pgd = PlanoIndividualTrabalhoAtendimento.objects.filter(pit__in=pits_da_adesao, homologado=True, data=dia).order_by(
                'data', 'hora_inicio'
            )
            em_horario_atendimento = False
            horario_atendimento = []
            for horario in horarios_atendimento_pgd:
                horario_atendimento.append(f'{horario.hora_inicio.strftime("%H:%M:%S")} às {horario.hora_final.strftime("%H:%M:%S")}')
                if horario.hora_inicio < dia.time() < horario.hora_final:
                    em_horario_atendimento = True
    return locals()


@rtr()
@login_required()
def profile_info(request, profile_uuid):
    from comum.models import Configuracao, Vinculo

    pessoa = get_object_or_404(Pessoa, uuid=profile_uuid)
    eh_pessoafisica = eh_aluno = False
    requisitante_eh_aluno = request.user.get_vinculo().eh_aluno()
    nao_exibir_matricula_userexterno_profile = Configuracao.get_valor_por_chave('comum', 'nao_exibir_matricula_userexterno_profile')
    nao_exibir_matricula_prestador_profile = Configuracao.get_valor_por_chave('comum', 'nao_exibir_matricula_prestador_profile')
    if hasattr(pessoa, 'pessoafisica'):
        profile = pessoa.pessoafisica
        if profile.eh_estrangeiro or not profile.cpf or not cpfcnpj.validate(profile.cpf):
            vinculos = Vinculo.objects.filter(pessoa=pessoa)
        else:
            vinculos = Vinculo.objects.filter(pessoa__pessoafisica__cpf=profile.cpf)
        eh_pessoafisica = True
        nome_social = profile.nome_social
        nome = nome_social or profile.nome
        # ponytail: multi-vínculo pega o primeiro; papel com foto prevalece na prática
        primeiro_vinculo = vinculos.first()
        email = primeiro_vinculo.email_pessoal if primeiro_vinculo else ''
        foto = primeiro_vinculo.get_foto_75x100_url() if primeiro_vinculo else '/static/comum/img/default.jpg'
    elif hasattr(pessoa, 'pessoajuridica'):
        profile = pessoa.pessoajuridica
        nome = profile.nome
        cnpj = profile.cnpj
    return locals()


@rtr()
@login_required()
def view_email(request):
    title = 'Notificação por E-mail'
    import json

    emails = json.load(open('deploy/emails.json'))
    emails_file_path = 'deploy/emails.json'
    os.unlink(emails_file_path)
    return locals()


@login_required()
def consultar_cep(request, cep):
    cep = cep.replace('.', '').replace('-', '')
    if cep.isdigit() and len(cep) == 8:
        try:
            response = requests.get(f'https://viacep.com.br/ws/{cep}/json/', timeout=settings.REQUESTS_TIMEOUT)
            dados = response.json()
            identificacao = Municipio.get_identificacao(dados['localidade'], dados['uf'])
            municipio = Municipio.objects.filter(identificacao=identificacao).first()
            if municipio is None and Configuracao.get_valor_por_chave('djtools', 'cadastrar_municipio_ao_consultar_cep'):
                municipio = Municipio.objects.create(nome=dados['localidade'], uf=dados['uf'])
            if municipio:
                dados.update(municipio={'id': municipio.id, 'nome': str(municipio)})
            return JsonResponse(dados)
        except Exception:
            pass
    return HttpResponse('{}')


@csrf_exempt
def consulta_cep_govbr(request, cep):
    api = APIExterna.CEP
    if not api.ativo:
        return JsonResponse({'erro': 'Serviço de consulta de CEP via gov.br está desativado temporariamente.'}, status=503)

    sucesso, dados = api.get_service().consulta_cep(cep)

    if sucesso:
        return JsonResponse(dados)
    else:
        return JsonResponse(dados if dados is not None else {'erro': 'Não foi possível consultar o CEP.'}, status=500)


def _destino_apos_2fa(request: HttpRequest) -> str:
    """Devolve o ``next`` da verificação do segundo fator, se ele aponta para o próprio host.

    O ``next`` vem da query string e alimenta um redirecionamento: sem a validação, a tela de
    verificação vira um redirecionador aberto para qualquer site.

    Args:
        request: Requisição HTTP em curso.

    Returns:
        A URL de origem completa (com toda a query), ou ``'/'`` quando ausente ou externa.
    """
    destino = request.GET.get('next', '/')
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return destino
    return '/'


@rtr()
def two_factor_authentication(request: HttpRequest) -> dict | HttpResponse:
    title = 'Autenticação via E-mail'
    # removendo a chave de autenticação por e-mail da seção quando o formulário for aberto
    if request.method == 'GET' and '2fa' in request.session:
        del request.session['2fa']
    if not request.user.is_authenticated:
        return httprr('..', 'Por favor realize o login novamente.')
    eh_aluno = request.user.get_vinculo().eh_aluno
    form = TwoFactorAuthenticationForm(data=request.POST or None, request=request)

    if settings.DEBUG:
        from djtools.models import TwoFactorAuthenticationCode

        usable_code = TwoFactorAuthenticationCode.objects.filter(
            user=request.user,
            expires__gte=datetime.datetime.now(),
        ).first()

    try:
        if form.is_valid():
            # adicinando a chave de autenticação por e-mail na seção
            request.session['2fa'] = 1
            request.session.save()
            # O ``httprr`` já mantém o ``_popup`` da requisição, respeitando a query do destino.
            return httprr(_destino_apos_2fa(request), 'Código de autenticação validado com sucesso.')
    except Exception as e:
        if settings.DEBUG:
            raise e
        return httprr('/', 'Código de autenticação inválido. Por favor, tente novamente.', 'error')
    return locals()


@login_required()
def private_media(request):
    media = request.GET.get('media', '').strip('/')
    if media.split('/')[0] == 'private-media':
        relative_path = os.path.join('private-media', media.split('/', 1)[1])
    else:
        relative_path = os.path.join('private-media', media)

    if not default_storage.exists(relative_path):
        return httprr('/', 'Arquivo inexistente.', 'error')

    _file_name, file_extension = os.path.splitext(relative_path)

    mime = magic.Magic(mime=True)
    try:
        with default_storage.open(relative_path) as f:
            content = f.read()
        content_type = mime.from_buffer(content)
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename=temp{get_random_string(12)}{file_extension}'
        return response
    except FileNotFoundError as e:
        if settings.DEBUG:
            raise e
        return httprr('/', 'Arquivo não encontrado.', 'error')


@login_required()
def send_token(request, method):
    try:
        from catalogo_provedor_servico.models import TemplateNotificaGovBR
        from comum.models import Configuracao

        vinculo = request.user.get_vinculo()
        codigo_verificacao = cache.get(f'password_check_{vinculo.id}', None)
        if not codigo_verificacao:
            codigo_verificacao = random_with_N_digits(5)
            cache.set(f'password_check_{vinculo.id}', codigo_verificacao, 300)
        instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        api_externa = APIExterna.NOTIFICA_GOVBR
        if method == 'govbr':
            TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR = (
                TemplateNotificaGovBR.objects.filter(
                    tipo_notificacao=TemplateNotificaGovBR.CODIGO_VERIFICADOR, canal_notificacao=TemplateNotificaGovBR.APP_GOVBR
                )
                .first()
                .id_template
            )

            if not TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR:
                result = {
                    'message': 'Não é possível enviar a notificação pois não foi localizado o id do Template da Plataforma Notifica. Entre em contato com os administradores do sistema!',
                    'status': 501,
                }
            if not settings.DEBUG and not api_externa.ativo:
                result = {
                    'message': 'Não é possível enviar o código de verificação pois a integração do SUAP com a Plataforma Notifica está desativada!',
                    'status': 501,
                }
            else:
                try:
                    api_service = api_externa.get_service()

                    cpf = request.user.get_profile().cpf.replace('.', '').replace('-', '')
                    sucesso, _ = api_service.send_cpf_notification(
                        cpf=cpf,
                        id_template=TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR,
                        parametrosTemplate={
                            'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                            'codigo_verificacao': codigo_verificacao,
                        },
                    )
                    if sucesso:
                        result = {'message': 'Código enviado com sucesso para App Gov.BR. A validade deste código é de 5 minutos!', 'status': 200}
                    else:
                        raise Exception('Erro ao enviar código para App Gov.BR.')
                except Exception:
                    result = {
                        'message': 'Houve um erro ao enviar código de verificação para o aplicativo Gov.BR. Utilize a opção: Enviar novo Código por Email.',
                        'status': 503,
                    }
        elif method == 'email':
            title = f'Código de Verificação - SUAP/{instituicao}'
            message = f"""<p>Seu código de verificação no SUAP/{instituicao}: {codigo_verificacao}<p>
                          <p>A validade deste código é de 5 minutos.<p>
                      """
            try:
                # Código de verificação usa SÓ o e-mail pessoal — nunca o institucional (mesma senha do SUAP).
                email_pessoal = vinculo.email_pessoal if vinculo else ''
                if not email_pessoal or email_pessoal == 'None':
                    raise Exception('Email inexistente.')
                send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_pessoal])
                result = {
                    'message': f'Código enviado com sucesso para o e-mail: {email_pessoal}. A validade deste código é de 5 minutos.',
                    'status': 200,
                }
            except Exception:
                result = {
                    'message': 'Houve um erro ao enviar código de verificação por e-mail, certifique-se que o usuário possui e-mail secundário cadastrado no SUAP.',
                    'status': 503,
                }
        else:
            result = {'message': 'Método indisponível', 'status': 501}
    except Exception as e:
        result = {'message': 'Erro ao tentar enviar token', 'status': 503}
        capture_exception(e)

    return JsonResponse(result, status=result['status'])


@csrf_exempt
def json_view(request, app_name, class_name):
    """
    View genérica que retorna o conteúdo de um modelo no formato *JSON*.

    Args:
        request (HttpRequest): objeto request da requisição;
        app_name (string): string contendo o nome da aplicação do modelo;
        class_name (string): string contendo o nome do modelo.

    Raises:
        Exception se o conjunto app_name.class_name não representar um modelo existente.

    Returns:
        Conteúdo formatado no padrão *JSON*

    Notes:
        É utilizado o generic_search_json que tem o funcionamento semelhante ao generic_search, com isso, os paramentros
        devem ser passados via request.POST ou request.GET, itens esperados: 'q', manager_name', 'force_generic_search'.

    """
    SEARCH_FUNCTION_NAME = 'buscar_json'
    try:
        cls = apps.get_model(app_name, class_name)
        public_search = getattr(cls, 'PUBLIC_SEARCH', False)
    except Exception:
        return JsonResponse({'error': 'Bad Request'}, status=400)

    if not request.user.is_authenticated and not public_search:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    data = request.method == 'POST' and request.POST or request.GET
    if cls is None:
        raise Exception('Invalid Class')

    if 'force_generic_search' not in data and hasattr(cls, SEARCH_FUNCTION_NAME):
        args = {'autocomplete': True}
        for key, value in list(data.items()):
            args[str(key)] = value
        return JsonResponse(cls.buscar_json(**args))
    else:
        return _generic_search_json_response(cls, data)


@login_required
@csrf_exempt
def chained_select_view(request, app_name, class_name):
    """
    View utilizada para gerar dependência entre items de form do tipo select.

    Args:
        request (HttpRequest): objeto request da requisição;
        app_name (string): nome da aplicação que contem a classe de modelo;
        class_name (string): nome da classe de modelo.

    Returns:
        *JsonResponse* com a lista de id, label dos itens contidos em **app_name.class_name**

    Notes:
        As chaves: django_filter_names, filter_pks, control, label, qs_filter, qs_filter_params_map podem ser passados
        via POST/GET.
    """
    cls = apps.get_model(app_name, class_name)
    data = request.POST or request.GET
    label = data.get('label')
    control = data.get('control')

    qs = cls.objects.all()
    if control:
        qs.query = timeless_load_qs_query(control)

    if 'django_filter_names' in data and 'filter_pks' in data:
        django_filter_names = data['django_filter_names'].split(',')
        filter_pks = data['filter_pks'].split(',')
        for i, elem in enumerate(filter_pks):
            if elem and django_filter_names[i].endswith('__in'):
                filter_pks[i] = elem.split(';')
    else:
        django_filter_names = None
        filter_pks = None

    depends = {}
    if django_filter_names and filter_pks:
        list_depends = list(zip(django_filter_names, filter_pks, strict=False))
        for item in list_depends:
            if item[0] and item[1]:
                depends[item[0]] = item[1]
        if depends:
            qs = qs.filter(**depends).distinct()

    qs_filter = data.get('qs_filter', None)

    if qs_filter:
        filters = {}
        qs_filters = qs_filter.split(',')
        for qs_filter in qs_filters:
            k, v = qs_filter.split('=')
            k = k.strip()
            v = v.strip()
            if v == 'False':
                v = False
            elif v == 'True':
                v = True
            else:
                qs_filter_value = data.get(f'qs_filter_params_map[{v}]', None)
                if qs_filter_value:
                    v = qs_filter_value
            filters[k] = v

        qs = qs.filter(**filters)

    return JsonResponse(list(qs.distinct().values('id', label)))


@login_required
def apagar_chave_sessao(request, chave):
    """
    Remove a chave da sessão.
    Útil para remover dicionário de dados dos relatórios.

    Args:
        request (HttpRequest): objeto request;
        chave (string): chave a ser removida.

    Returns:
        Objeto HttpResponse com a mensagem de remoção da chave.
    """
    if chave in request.session:
        del request.session[chave]
    return HttpResponse(f'Chave {chave} removida com sucesso.')


@rtr()
@login_required
def restaurar_arquivos_media(request):
    title = 'Restaurar Arquivos de Mídia'
    if not request.user.has_group_cached(['Coordenador de TI sistêmico']):
        raise PermissionDenied
    if not is_remote_storage():
        return httprr('/', 'O storage precisa ser do tipo S3.', 'error')
    form = RestaurarArquivosMediaForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        return tasks.restaurar_arquivos_media(form.arquivos)
    return locals()


@rtr()
@permission_required('djtools.view_emailenviadolog')
def history(request):
    from comum.models import Configuracao

    title = 'Histórico de Objetos'
    form = HistoryForm(data=request.GET or None, request=request)
    opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
    if not opensearch_configurado:
        return httprr('/', 'O recurso de auditoria não está habilitado.', 'error')

    if form.is_valid():
        try:
            page = int(request.GET.get('page', '1'))
            if page > 100:
                page = 100
        except ValueError:
            page = 1
        logs = form.processar(page)
        getvars = request.GET.copy()
        if 'page' in getvars:
            del getvars['page']
        getvars = getvars.urlencode()
        has_previous = page > 1
        previous_page = page - 1
        next_page = page + 1
        tamanho = len(logs)
        has_next = tamanho >= 100 and page < 100
        if tamanho < 100:
            has_next = False
    return locals()


@rtr()
@permission_required('djtools.view_emailenviadolog')
def access_logs(request):
    from comum.models import Configuracao

    title = 'Logs de Acesso'
    form = AccessLogForm(data=request.GET or None, request=request)
    opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
    if not opensearch_configurado:
        return httprr('/', 'O recurso de logs de acesso não está habilitado.', 'error')

    if form.is_valid():
        try:
            page = int(request.GET.get('page', '1'))
            if page > 100:
                page = 100
        except ValueError:
            page = 1
        logs = form.processar(page)
        getvars = request.GET.copy()
        if 'page' in getvars:
            del getvars['page']
        getvars = getvars.urlencode()
        has_previous = page > 1
        previous_page = page - 1
        next_page = page + 1
        tamanho = len(logs)
        has_next = tamanho >= 100 and page < 100
        if tamanho < 100:
            has_next = False
    return locals()


@rtr()
@permission_required('djtools.view_emailenviadolog')
def email_logs(request):
    from comum.models import Configuracao

    title = 'Logs de Envio de Email'
    form = EmailLogForm(data=request.GET or None, request=request)
    opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
    if not opensearch_configurado:
        return httprr('/', 'O recurso de logs de acesso não está habilitado.', 'error')

    if form.is_valid():
        try:
            page = int(request.GET.get('page', '1'))
            if page > 100:
                page = 100
        except ValueError:
            page = 1
        logs = form.processar(page)
        getvars = request.GET.copy()
        if 'page' in getvars:
            del getvars['page']
        getvars = getvars.urlencode()
        has_previous = page > 1
        previous_page = page - 1
        next_page = page + 1
        tamanho = len(logs)
        has_next = tamanho >= 100 and page < 100
        if tamanho < 100:
            has_next = False
    return locals()


@rtr()
@permission_required('djtools.view_emailenviadolog')
def log_history(request, pk):
    import pytz

    from comum.models import Configuracao

    tz = pytz.timezone(settings.TIME_ZONE)

    title = f'Log #{pk}'

    opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
    if not opensearch_configurado:
        return httprr('/', 'O recurso de auditoria não está habilitado.', 'error')

    query = {'ids': {'values': [pk]}}
    response = get_opensearch_query_history(query)

    def gerar_descricao(source, user):
        match source['status']:
            case 'deleted':
                acao = 'excluiu'
            case 'created':
                acao = 'criou'
            case _:
                acao = 'atualizou'
        try:
            modelo = apps.get_model(source['model'])._meta.verbose_name
        except Exception:
            modelo = source['model']
        if user:
            usuario = 'usuário'
        else:
            usuario = 'sistema'
        descricao = f'O {usuario} {acao} {modelo} #{source["pk"]}'
        return descricao

    logs = response['hits']['hits'][:]
    for hits in logs:
        if 'request' in hits['_source']:
            hits['user'] = User.objects.filter(username=hits['_source']['request']['author']['username']).first()
            hits['id'] = hits['_id']
            hits['dt'] = tz.fromutc(datetime.datetime.fromisoformat(hits['_source']['request']['last_update']))
            hits['pk'] = hits['_source']['pk']
            try:
                modelo = apps.get_model(hits['_source']['model'])
                nome_modelo = modelo._meta.verbose_name
                hits['instancia'] = modelo.objects.filter(pk=hits['_source']['pk']).first()
            except Exception:
                nome_modelo = hits['_source']['model']
                hits['instancia'] = None
            hits['nome_modelo'] = nome_modelo
            hits['descricao'] = gerar_descricao(hits['_source'], hits['user'])
            hits['endereco_ip'] = hits['_source']['request']['ip_address']
            hits['servidor'] = hits['_source']['request']['server']
            hits['url'] = hits['_source']['request']['url']
            hits['user_agent'] = hits['_source']['request']['user_agent']
            hits['diff'] = hits['_source']['diff']
            for diff in hits['diff']:
                diff['new_value'] = force_utf8_string(diff.get('new_value'))
                diff['old_value'] = force_utf8_string(diff.get('old_value'))

    if len(logs):
        obj = logs[0]
    else:
        obj = None
    return locals()


@rtr()
@permission_required('djtools.view_emailenviadolog')
def log_access(request, pk):
    from comum.models import Configuracao

    title = f'Log #{pk}'

    opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
    if not opensearch_configurado:
        return httprr('/', 'O recurso de auditoria não está habilitado.', 'error')

    query = {'ids': {'values': [pk]}}
    response = get_opensearch_query_access_logs(query)

    logs = response['hits']['hits'][:]
    for hits in logs:
        hits['user'] = User.objects.filter(username=hits['_source']['user']).first()
        hits['id'] = hits['_id']
        hits['dt'] = timezone.make_aware(timezone.make_naive(datetime.datetime.fromisoformat(hits['_source']['@timestamp'])))
        hits['path'] = hits['_source']['path']
        hits['ip_address'] = hits['_source']['ip_address']
        hits['server'] = hits['_source']['server']
        hits['user_agent'] = hits['_source']['agent']
        hits['referer'] = hits['_source']['referer']
        hits['status_code'] = hits['_source']['status_code']
        hits['method'] = hits['_source']['method']
        hits['total_time'] = hits['_source']['total_time']
        hits['upstream_time'] = hits['_source']['upstream_time']
        hits['http_version'] = hits['_source']['http_version']
        hits['body_bytes_sent'] = hits['_source']['body_bytes_sent']
    if len(logs):
        obj = logs[0]
    else:
        obj = None
    return locals()
