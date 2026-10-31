import base64
from time import sleep

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from sentry_sdk import capture_exception

from comum.models import Configuracao, Vinculo
from comum.utils import ferramentas_configuradas, tem_permissao_informar_erro
from djtools import layout
from djtools.signals import minhas_acoes
from djtools.utils import get_apps_suap, get_areas_suap, get_client_ip, httprr, requests, rtr
from erros.forms import (
    AlterarURLErroForm,
    AnexoErroForm,
    AtribuirErroForm,
    ComentarioErroForm,
    EditarAtualizacaoErroForm,
    ReportarErroForm,
    ReportarErroPorChamadoForm,
    SituacaoErroForm,
    UnificarErroForm,
)
from erros.models import AtendenteErro, Erro, HistoricoComentarioErro, RespostaFrequente
from erros.utils import criar_issue_gitlab, get_custom_view_name_from_url, get_hostname, popular_links_gitlab


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Conta erros aguardando feedback do usuário logado.

    Args:
        request: requisição HTTP usada para identificar o vínculo do usuário.

    Returns:
        list[dict]: um cartão com a quantidade quando houver erros nessa situação;
        lista vazia se o usuário não tiver vínculo ou não houver pendências.
    """
    pendencias = []
    vinculo = request.user.get_vinculo()
    if not vinculo:
        return pendencias

    qtd_feedback = Erro.objects.filter(interessadoerro__vinculo=vinculo, situacao=Erro.SITUACAO_AGUARDANDO_FEEDBACK).count()
    if qtd_feedback:
        pendencias.append(
            {
                'titulo': f'Erro{pluralize(qtd_feedback)}',
                'subtitulo': 'aguardando feedback',
                'qtd': qtd_feedback,
                'url': '/admin/erros/erro/?sou_interessado=sim',
            }
        )

    return pendencias


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []

    if request.user.has_group_cached('Recebedor de Demandas', ignore_groups_if_superuser=False):
        erros = Erro.objects.filter(situacao__in=[Erro.SITUACAO_ABERTO, Erro.SITUACAO_REABERTO])
        erros_sem_atribuicao = erros.filter(atendente_atual__isnull=True, gitlab_issue_url__isnull=True).count()
        if erros_sem_atribuicao:
            pendencias.append(
                {
                    'titulo': f'Erro{pluralize(erros_sem_atribuicao)}',
                    'subtitulo': 'a atribuir',
                    'qtd': erros_sem_atribuicao,
                    'url': '/admin/erros/erro/?pendente_atribuicao=sim&possui_url_gitlab=nao',
                }
            )

    return pendencias


@layout.quadro('Erros', icone='bug', pode_esconder=True)
def index_quadros(quadro, request):
    usuario = request.user
    vinculo = usuario.get_vinculo()

    erros = Erro.objects.filter(interessadoerro__vinculo=vinculo, interessadoerro__ativo=True).exclude(situacao__in=Erro.SITUACOES_FINAIS).count()
    if erros:
        quadro.add_item(
            layout.ItemContador(
                titulo=f'Erro{pluralize(erros)}',
                subtitulo='Aguardando resolução',
                qtd=erros,
                url='/admin/erros/erro/?sou_interessado=sim',
            )
        )

    if usuario.has_group_cached('Analista'):
        erros = Erro.objects.exclude(situacao__in=Erro.SITUACOES_FINAIS).exclude(situacao=Erro.SITUACAO_AGUARDANDO_FEEDBACK)
        erros_a_resolver = erros.filter(atendente_atual=vinculo).count()
        if erros_a_resolver:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Erro{pluralize(erros_a_resolver)}',
                    subtitulo='Em análise',
                    qtd=erros_a_resolver,
                    url=f'/admin/erros/erro/?atendente_atual={vinculo.pk}&tab=tab_em_andamento',
                )
            )

    return quadro


@rtr()
@login_required
def reportar_erro_500(request):
    try:  # esta tela não pode quebrar
        descricao = request.POST.get('descricao')
        event_id = request.POST.get('event_id')
        full_url = request.POST.get('full_url')
        view_name = get_custom_view_name_from_url(full_url)

        sentry_token = Configuracao.get_valor_por_chave('comum', 'sentry_token')
        sentry_url = Configuracao.get_valor_por_chave('comum', 'sentry_url')
        sentry_organization = Configuracao.get_valor_por_chave('comum', 'sentry_organization')
        sentry_project = Configuracao.get_valor_por_chave('comum', 'sentry_project')
        sentry_glitchtip = Configuracao.get_valor_por_chave('comum', 'sentry_glitchtip')

        if all([tem_permissao_informar_erro(request), descricao, full_url, view_name]):
            from erros.models import Erro

            try:
                headers_api = {'Authorization': f'Bearer {sentry_token}'}
                data = {
                    'event_id': event_id,
                    'name': request.user.get_profile().nome,
                    'email': request.user.get_vinculo().email_notificacao or settings.DEFAULT_FROM_EMAIL,
                    'comments': descricao,
                }
                if sentry_glitchtip:
                    sentry_issue_url = f'{sentry_url}/api/0/projects/{sentry_organization}/{sentry_project}/events/{event_id}/'
                    sentry_issue_id = requests.get(
                        sentry_issue_url,
                        headers=headers_api,
                        data=data,
                        timeout=settings.REQUESTS_TIMEOUT,
                    ).json()['issue']
                    sentry_event_url = f'{sentry_url}/{sentry_organization}/issues/{sentry_issue_id}/'
                else:
                    sentry_issue_url = f'{sentry_url}/api/0/projects/{sentry_organization}/{sentry_project}/issues/?query={event_id}'
                    sentry_issue_id = None
                    count = 0
                    while not sentry_issue_id and count < 20:  # aguardando sincronizar o evento com o sentry por até 10 segundos
                        try:
                            sentry_issue_id = requests.get(
                                sentry_issue_url,
                                headers=headers_api,
                                data=data,
                                timeout=settings.REQUESTS_TIMEOUT,
                            ).json()[0]['id']
                        except Exception:
                            count += 1
                            sleep(1)
                    sentry_event_url = f'{sentry_url}/organizations/sentry/issues/{sentry_issue_id}/'
            except Exception as e:
                capture_exception(e)
                sentry_issue_id = None
                sentry_event_url = None

            obj = (
                Erro.objects.filter(sentry_issue_id__isnull=False, sentry_issue_id=sentry_issue_id)
                .exclude(situacao__in=Erro.SITUACOES_FINAIS)
                .first()
            )
            if obj:
                obj.gerenciar_interessado(request.user.get_vinculo())
                obj.comentar(request.user.get_vinculo(), descricao, tipo=HistoricoComentarioErro.TIPO_COMENTARIO)
                messages.success(request, 'Comentário adicionado ao erro com sucesso.')
            else:
                obj = Erro()
                obj.informante = request.user.get_vinculo()
                obj.descricao = descricao
                obj.url = full_url
                obj.url_sentry = sentry_event_url
                obj.view = view_name
                obj.sentry_issue_id = sentry_issue_id
                obj.agent = request.META.get('HTTP_USER_AGENT', '-')
                obj.ip_address = get_client_ip(request)
                obj.maquina = get_hostname()
                obj.criar()

                messages.success(request, 'Problema informado com sucesso.')

            return HttpResponseRedirect(obj.get_absolute_url())
    except Exception as e:
        if settings.DEBUG:
            import traceback

            traceback.print_exc()
            messages.error(request, str(e))
        messages.error(request, 'Você não tem permissão para fazer isso.')
    return HttpResponseRedirect('/')


@rtr()
@login_required
def reportar_erro_por_chamado(request, chamado_pk):
    title = f'Reportar erro a partir do chamado #{chamado_pk}'
    if 'centralservicos' in settings.INSTALLED_APPS:
        from centralservicos.models import Chamado

        chamado = get_object_or_404(Chamado.objects, pk=chamado_pk)
        if chamado.pode_reclassificar(request.user):
            form = ReportarErroPorChamadoForm(request.POST or None, request=request)
            if form.is_valid():
                form.processar(chamado)
                return httprr('..', 'Erro reportado com sucesso.')
            return locals()
    return httprr(request, 'Você não tem permissão para fazer isso.', 'error')


@rtr()
@login_required
def reportar_erro(request):
    title = 'Reportar Erro no SUAP'
    path = request.GET.get('url')
    try:
        path = base64.b64decode(path.encode()).decode()
        url = request.build_absolute_uri(path)
        view = get_custom_view_name_from_url(url)
        if not view:
            raise Exception('url inválida.')
    except Exception:
        return httprr('..', 'URL informada é incorreta.', 'error')

    qs = Erro.objects.filter(view=view).exclude(situacao__in=Erro.SITUACOES_FINAIS)
    existe_erro = qs.exists()

    qs_outros = qs.exclude(informante=request.user.get_vinculo())
    qs_meus = qs.filter(informante=request.user.get_vinculo())
    reportar = not existe_erro or existe_erro and 'reportar' in request.GET

    if reportar:
        erros_mesma_view = Erro.objects.filter(view=view, informante=request.user.get_vinculo())
        form = ReportarErroForm(request.POST or None, request=request, url=url)
        if form.is_valid():
            obj = form.processar()
            return httprr(obj.get_absolute_url(), 'Erro reportado com sucesso.')

    return locals()


@rtr()
@login_required
def areas(request):
    title = 'Erros'
    lista_areas = get_areas_suap()
    return locals()


@rtr()
@login_required
def modulos(request, area_id):
    areas = get_areas_suap()
    area = areas.get(area_id, {})
    if not area:
        return httprr('/erros/areas', 'Área inexistente.', 'error')
    title = f'Área {area.get("area")}'
    lista_modulos = get_apps_suap(area)
    for modulo in lista_modulos:
        erros = Erro.objects.filter(modulo_afetado=modulo.label)
        modulo.reportados = erros.filter(situacao=Erro.SITUACAO_ABERTO).count()
        modulo.em_analise = erros.filter(situacao=Erro.SITUACAO_EM_ANALISE).count()
        modulo.aguardando_feedback = erros.filter(situacao=Erro.SITUACAO_AGUARDANDO_FEEDBACK).count()
        modulo.em_correcao = erros.filter(situacao=Erro.SITUACAO_EM_CORRECAO).count()
        modulo.resolvidos = erros.filter(situacao=Erro.SITUACAO_RESOLVIDO).count()
    return locals()


@rtr()
@login_required
def modulo(request, modulo_id):
    url = base64.b64encode(f'/erros/modulo/{modulo_id}/'.encode()).decode()
    return HttpResponseRedirect(f'/erros/reportar_erro/?url={url}')


@rtr()
@login_required
def erro(request, pk):
    obj = get_object_or_404(Erro, pk=pk)

    title = f'Erro {pk}: {obj.modulo_afetado_display}'

    vinculo = request.user.get_vinculo()

    if not obj.vinculo_eh_interessado(vinculo) and not obj.vinculo_pode_ser_atendente(vinculo) and obj.situacao == Erro.SITUACAO_CANCELADO:
        raise PermissionDenied

    outros_interessados = obj.get_outros_interessados()
    outros_atendentes = obj.get_outros_atendentes()
    comentarios = obj.historicocomentarioerro_set.exclude(tipo=HistoricoComentarioErro.TIPO_NOTA_INTERNA)
    notas_internas = obj.historicocomentarioerro_set.filter(tipo=HistoricoComentarioErro.TIPO_NOTA_INTERNA)
    eh_atendente = obj.vinculo_pode_ser_atendente(vinculo)
    eh_atendente_atual = obj.vinculo_eh_atendente_atual(vinculo)
    eh_interessado = obj.vinculo_eh_interessado(vinculo)
    pode_comentar = obj.pode_comentar(vinculo)
    pode_comentar_nota_interna = obj.pode_comentar_nota_interna(vinculo)
    pode_sincronizar_gitlab = obj.pode_sincronizar_gitlab(vinculo)
    pode_criar_issue_gitlab = obj.pode_criar_issue_gitlab(vinculo)
    pode_ver_comentarios = obj.pode_ver_comentarios(vinculo)
    pode_ver_nota_interna = obj.pode_ver_nota_interna(vinculo)
    pode_assumir = obj.pode_assumir(vinculo)
    pode_devolver = obj.pode_devolver(vinculo)
    pode_se_interessar = obj.pode_se_interessar(vinculo)
    pode_alterar_url = obj.pode_alterar_url(vinculo)
    pode_editar_atualizacao = obj.pode_editar_atualizacao(vinculo)
    pode_se_desinteressar = obj.pode_se_desinteressar(vinculo)
    pode_atribuir = obj.pode_atribuir(vinculo)
    pode_unificar = obj.pode_unificar(vinculo)
    pode_cancelar_por_erro_de_abertura = obj.pode_cancelar_por_erro_de_abertura(vinculo)
    situacoes_disponiveis = obj.get_situacoes_disponiveis(vinculo)
    conf = ferramentas_configuradas()
    respostas_frequentes_do_atendente = RespostaFrequente.objects.filter(atendente=request.user).values_list('texto', flat=True)
    outros_erros_informante = Erro.objects.filter(informante=obj.informante).exclude(situacao__in=Erro.SITUACOES_FINAIS).exclude(id=obj.id)

    if eh_atendente:
        erros_mesma_view = Erro.objects.filter(view=obj.view).exclude(situacao__in=Erro.SITUACOES_FINAIS).exclude(id=obj.id).count()
        if request.GET.get('sincronizar_gitlab'):
            if conf:
                if obj.pode_sincronizar_gitlab(vinculo):
                    url_gitlab = popular_links_gitlab(obj, conf)
                else:
                    return httprr('.', 'Usuário sem permissão para sincronizar o gitlab.')
            else:
                return httprr('.', 'Sentry ou Gitlab não configurados.')
            if url_gitlab:
                return httprr('.', 'Url de Issue do Gitlab sincronizada com sucesso.')
            else:
                return httprr('.', 'Url de Issue do Gitlab inexistente.', 'error')
        if request.GET.get('criar_issue_gitlab'):
            if conf:
                if obj.pode_criar_issue_gitlab(vinculo):
                    url_gitlab = criar_issue_gitlab(obj, conf, request)
                else:
                    return httprr('.', 'Usuário sem permissão para criar issue no gitlab.')
            else:
                return httprr('.', 'Sentry ou Gitlab não configurados.')
            if url_gitlab:
                return httprr('.', 'Issue criada no Gitlab com sucesso.')
            else:
                return httprr('.', 'Não foi possível criar Issue no Gitlab.', 'error')
        if request.GET.get('assumir'):
            obj.gerenciar_atendente(vinculo, forcar_assumir=True)
            return httprr('.', 'Você agora é o Atendente Principal deste erro.')
        elif request.GET.get('devolver'):
            obj.devolver(vinculo)
            return httprr('.', 'Erro devolvido com sucesso.')

    if request.GET.get('cancelar_por_erro_de_abertura'):
        if pode_cancelar_por_erro_de_abertura:
            obj.cancelar_por_erro_de_abertura()
            return httprr('.', 'Cancelado por não atender às instruções exibidas na tela de abertura deste Erro.')
        else:
            return httprr('.', 'Só é possível cancelar um erro com situação igual a "Reportado".')

    if request.GET.get('interessar') and pode_se_interessar:
        obj.gerenciar_interessado(vinculo)
        return httprr('.', 'Você agora é um Interessado deste erro.')
    if request.GET.get('desinteressar') and pode_se_desinteressar:
        obj.gerenciar_interessado(vinculo, habilitar=False)
        return httprr('.', 'Interesse removido com sucesso.')

    form = ComentarioErroForm(request.POST or None, situacao_atual=obj.situacao, eh_atendente=eh_atendente)
    if form.is_valid() and pode_comentar:
        tipo = request.POST.get('tipo', 'comentario')
        if form.cleaned_data.get('situacao', False):
            situacao_id = int(form.cleaned_data.get('situacao'))
            obj.gerenciar_situacao(vinculo=vinculo, situacao=situacao_id, motivo=form.cleaned_data.get('descricao'))
            obj.gerenciar_atendente(vinculo, forcar_assumir=True)
            messages.add_message(request, messages.SUCCESS, 'Situação alterada com sucesso.')
        else:
            form.processar(obj, vinculo, tipo=tipo)
            if tipo == 'comentario':
                obj.gerenciar_atendente(vinculo, forcar_assumir=True)
        url = obj.get_absolute_url()
        if tipo == 'nota_interna':
            url += '?tab=notas_internas'
        messages.add_message(request, messages.SUCCESS, 'Comentário cadastrado com sucesso.')
        return httprr(url)

    return locals()


@rtr()
@login_required
def erros_informante(request, pk):
    obj = get_object_or_404(Vinculo, pk=pk)
    title = f'Erros reportados por: {obj}'

    erros = Erro.objects.filter(informante=obj).exclude(situacao__in=Erro.SITUACOES_FINAIS)

    return locals()


@rtr()
@login_required
def alterar_situacao_erro(request, pk):
    erro = get_object_or_404(Erro, pk=pk)
    vinculo = request.user.get_vinculo()

    try:
        situacao_id = int(request.GET.get('situacao'))
    except Exception:
        return httprr('..', 'Situação de destino inválida.', 'error')

    if situacao_id in erro.get_situacoes_disponiveis(vinculo):
        situacao_nova_display = Erro(situacao=situacao_id).get_situacao_display()
        title = 'Criar Atualização'
        if situacao_id == Erro.SITUACAO_REABERTO and not erro.vinculo_pode_ser_atendente(vinculo):
            form = SituacaoErroForm(request.POST or None)
            if form.is_valid():
                form.processar(erro, vinculo, situacao_id)
                return httprr('..', 'Situação alterada com sucesso.')
        elif situacao_id == Erro.SITUACAO_RESOLVIDO:
            form = EditarAtualizacaoErroForm(request.POST or None, request=request, instance=erro, required=False)
            if form.is_valid():
                form.save()
                erro.gerenciar_situacao(vinculo=request.user.get_vinculo(), situacao=situacao_id)
                return httprr('..', 'Situação alterada com sucesso.')
        else:
            erro.gerenciar_situacao(vinculo=request.user.get_vinculo(), situacao=situacao_id)
            return httprr(erro.get_absolute_url(), 'Situação alterada com sucesso.')
    else:
        return httprr('..', 'Você não possui permissão para fazer isto.', 'error')
    return locals()


@rtr()
@login_required
def alterar_url(request, pk):
    title = f'Alterar URL do Erro {pk}'
    erro = get_object_or_404(Erro, pk=pk)
    tipo = request.GET.get('tipo')
    vinculo = request.user.get_vinculo()
    if not erro.pode_alterar_url(vinculo) or tipo not in ['erro', 'sentry', 'gitlab']:
        return httprr('..', 'Você não tem permissão para fazer isto.', 'erro')

    url = ''
    if tipo == 'erro':
        url = erro.url
    elif tipo == 'sentry':
        url = erro.url_sentry
    elif tipo == 'gitlab':
        url = erro.gitlab_issue_url

    form = AlterarURLErroForm(request.POST or None, request=request, initial={'url': url}, tipo=tipo, erro=erro, vinculo=vinculo)
    if form.is_valid():
        form.processar()
        return httprr('..', f'URL do {tipo} alterada com sucesso.')

    return locals()


@rtr()
@login_required
def adicionar_anexo(request, pk):
    title = f'Adicionar anexo ao Erro {pk}'
    erro = get_object_or_404(Erro, pk=pk)
    vinculo = request.user.get_vinculo()
    if not erro.pode_comentar(vinculo):
        return httprr('..', 'Você não tem permissão para fazer isto.', 'erro')

    form = AnexoErroForm(request.POST or None, files=request.FILES or None, request=request, erro=erro, vinculo=vinculo)
    if form.is_valid():
        try:
            instancia = form.processar()
            return httprr('..', 'Anexo adicionado com sucesso.')
        except Exception:
            return httprr('..', 'Erro de comunicação com o gerenciador de arquivos, por favor tente enviar o anexo novamente.', 'error')
    return locals()


@rtr()
@login_required
def atribuir_atendente(request, pk):
    title = f'Atribuir Atendente ao erro #{pk}'
    erro = get_object_or_404(Erro, pk=pk)
    atribuinte = request.user.get_vinculo()
    if not erro.pode_atribuir(atribuinte):
        return httprr('..', 'Você não tem permissão para fazer isto.', 'erro')

    form = AtribuirErroForm(request.POST or None, files=request.FILES or None, request=request, erro=erro, atribuinte=atribuinte)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Usuário atribuído com sucesso.')
    return locals()


@rtr()
@login_required
def unificar_erros(request, pk):
    title = f'Unificar erros ao erro #{pk}'
    erro = get_object_or_404(Erro, pk=pk)
    vinculo = request.user.get_vinculo()
    if not erro.pode_unificar(vinculo):
        return httprr('..', 'Você não tem permissão para fazer isto.', 'erro')

    form = UnificarErroForm(request.POST or None, files=request.FILES or None, request=request, erro=erro, vinculo=vinculo)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Erros unificados com sucesso.')
    return locals()


@rtr()
@login_required
def desconsiderar_comentario(request, pk):
    comentario = get_object_or_404(HistoricoComentarioErro, pk=pk)
    vinculo = request.user.get_vinculo()
    if not comentario.pode_desconsiderar_comentario(vinculo):
        return httprr(comentario.erro.get_absolute_url(), 'Você não tem permissão para fazer isto.', 'erro')

    comentario.desconsiderar_comentario()

    return httprr(comentario.erro.get_absolute_url(), 'Comentário desconsiderado com sucesso.')


@rtr()
@login_required
def remover_atendente(request, pk_erro, pk_vinculo):
    obj = get_object_or_404(Erro, pk=pk_erro)
    if request.user.get_vinculo().id == pk_vinculo:
        qs = AtendenteErro.objects.filter(erro_id=pk_erro, vinculo_id=pk_vinculo).exclude(vinculo=obj.atendente_atual)
        if qs.exists():
            qs.delete()
            HistoricoComentarioErro.objects.create(
                erro=obj, descricao='se removeu do atendimento.', vinculo=request.user.get_vinculo(), automatico=True
            )
            return httprr(obj.get_absolute_url(), 'Remoção realizada com sucesso.')
    return httprr(obj.get_absolute_url(), 'Você não tem permissão para fazer isto.', 'erro')


@rtr()
@login_required
def editar_atualizacao(request, pk):
    obj = get_object_or_404(Erro, pk=pk)
    vinculo = request.user.get_vinculo()
    if not obj.pode_editar_atualizacao(vinculo):
        return httprr('..', 'Você não tem permissão para fazer isto.', 'erro')

    if obj.atualizacao:
        title = f'Editar Atualização para o Erro #{pk}'
    else:
        title = f'Criar Atualização para o Erro #{pk}'

    form = EditarAtualizacaoErroForm(request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Atualização editada com sucesso.')
    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_erros(request, data, datahora_inicio, datahora_fim):
    usuario_id = request.user.id

    filters_erros_abertos = {}
    if datahora_inicio:
        filters_erros_abertos['data_criacao__gte'] = datahora_inicio
    if datahora_fim:
        filters_erros_abertos['data_criacao__lte'] = datahora_fim

    qs_erros_abertos = Erro.objects.filter(informante__user_id=usuario_id, **filters_erros_abertos).order_by('data_criacao')
    for erro_aberto in qs_erros_abertos:
        data.append(
            (
                'Erros',
                'Abertura de Erros',
                erro_aberto,
                f'em {erro_aberto.data_criacao.strftime("%d/%m/%Y %H:%M")}',
                f'{erro_aberto.get_absolute_url()}',
            )
        )

    filters_erros_ultima_alteracao = {}
    if datahora_inicio:
        filters_erros_ultima_alteracao['data_ultima_alteracao__gte'] = datahora_inicio
    if datahora_fim:
        filters_erros_ultima_alteracao['data_ultima_alteracao__lte'] = datahora_fim

    qs_erros_resolvidos = Erro.objects.filter(
        atendente_atual__user_id=usuario_id, situacao=Erro.SITUACAO_RESOLVIDO, **filters_erros_ultima_alteracao
    ).order_by('data_ultima_alteracao')
    for erro_resolvido in qs_erros_resolvidos:
        data.append(
            (
                'Erros',
                'Resolução de Erros',
                erro_resolvido,
                f'em {erro_resolvido.data_ultima_alteracao.strftime("%d/%m/%Y %H:%M")}',
                f'{erro_resolvido.get_absolute_url()}',
            )
        )

    qs_erros_cancelados = Erro.objects.filter(
        atendente_atual__user_id=usuario_id, situacao=Erro.SITUACAO_CANCELADO, **filters_erros_ultima_alteracao
    ).order_by('data_ultima_alteracao')
    for erro_cancelado in qs_erros_cancelados:
        data.append(
            (
                'Erros',
                'Cancelamento de Erros',
                erro_cancelado,
                f'em {erro_cancelado.data_ultima_alteracao.strftime("%d/%m/%Y %H:%M")}',
                f'{erro_cancelado.get_absolute_url()}',
            )
        )

    filters_unificacao_erros = {}
    if datahora_inicio:
        filters_unificacao_erros['data_alteracao__gte'] = datahora_inicio
    if datahora_fim:
        filters_unificacao_erros['data_alteracao__lte'] = datahora_fim
    qs_erros_unificados = HistoricoComentarioErro.objects.filter(
        vinculo__user_id=usuario_id, erro__situacao=Erro.SITUACAO_UNIFICADO, descricao__icontains='unificou este erro', **filters_unificacao_erros
    ).order_by('data_alteracao')
    for erro_unificado in qs_erros_unificados:
        data.append(
            (
                'Erros',
                'Unificação de Erros',
                erro_unificado.erro,
                f'em {erro_unificado.data_alteracao.strftime("%d/%m/%Y %H:%M")}',
                f'{erro_unificado.erro.get_absolute_url()}',
            )
        )


def exception(request, pk=None):
    from sentry_sdk import capture_exception

    from comum.views import handler500

    e = Exception('Erro simulado para testar o sentry .')

    if not settings.DEBUG:
        raise e

    capture_exception(e)
    return handler500(request)
