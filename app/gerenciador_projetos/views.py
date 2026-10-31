import calendar
from datetime import date, datetime

import plotly.figure_factory as ff
import plotly.offline as opy
from dateutil import rrule
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_POST

from comum.models import Comentario, User
from djtools import layout
from djtools.html.calendarios import CalendarioPlus
from djtools.html.graficos import BarChart, StackedGroupedColumnChart
from djtools.signals import minhas_acoes
from djtools.utils import JsonResponse, httprr, permission_required, rtr
from gerenciador_projetos.forms import (
    CompararCalendarioForm,
    CompararProjetosForm,
    AdicionarAnexoForm,
    AdicionarOuVincularListaProjetoForm,
    AlterarAtribuidosTarefaForm,
    AlterarSituacaoTarefaForm,
    AtribuirTarefaACampus,
    AtualizarPosicaoListaProjetoForm,
    BuscaHistoricoEvolucaoForm,
    ComentarioRapidoTarefaForm,
    ConfirmarAcaoForm,
    DashboardForm,
    FiltrarCalendarioForm,
    HistoricoEvolucaoForm,
    LinkTarefaForm,
    MinhasTarefasForm,
    RecorrenciaTarefaForm,
    TagForm,
    TarefaFormFactory,
    TarefaProjetoFiltroForm,
)
from gerenciador_projetos.models import (
    HistoricoEvolucao,
    ItemChecklist,
    Lista,
    LinkTarefa,
    ListaProjeto,
    ListaTarefa,
    Projeto,
    RecorrenciaTarefa,
    Tag,
    Tarefa,
)
from gerenciador_projetos.portfolio import ORDEM_SITUACOES, StatusPrazo, indicadores, projetos_selecionados
from gerenciador_projetos.utils import Notificar, generate_color
from gerenciador_projetos.enums import SituacaoProjeto, SituacaoTarefa
from django.db import models


@layout.quadro('Gerenciador de Projetos', icone='bug', pode_esconder=True)
def index_quadros(quadro, request):
    usuario = request.user

    if usuario.has_perm('view_projeto'):
        tarefas_andamento = Tarefa.objects.filter(atribuido_a=usuario, data_conclusao__isnull=True).count()
        if tarefas_andamento:
            quadro.add_item(
                layout.ItemContador(
                    titulo=f'Tarefa{pluralize(tarefas_andamento)}',
                    subtitulo='Em andamento',
                    qtd=tarefas_andamento,
                    url='/gerenciador_projetos/minhastarefas/',
                )
            )

    return quadro


@rtr('gerenciador_projetos/templates/projeto.html')
@permission_required('gerenciador_projetos.view_projeto')
def projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')

    title = f'Projeto: {projeto.titulo}'

    user = request.user
    eh_superusuario = user.is_superuser
    eh_gerente_projeto = projeto.eh_gerente_projeto(user)
    eh_membro_projeto = projeto.eh_membro_projeto(user)

    pode_adicionar_comentarios = projeto.pode_adicionar_comentarios(user)
    pode_adicionar_tarefas = projeto.pode_adicionar_tarefas(user)
    pode_adicionar_listas = projeto.pode_adicionar_listas(user)
    pode_editar_tags = projeto.pode_editar_tags(user)

    pode_editar_projeto = projeto.pode_editar_projeto(user)
    pode_editar_tarefas = projeto.pode_editar_tarefas(user)
    pode_registrar_evolucao = request.user.has_perm('gerenciador_projetos.change_historicoevolucao')

    qtd_comentarios = Comentario.objects.filter(
        content_type=ContentType.objects.get(app_label='gerenciador_projetos', model='projeto'), object_id=projeto.pk, resposta=None
    ).count()
    qtd_tarefas = projeto.tarefa_set.count()

    tarefa_projeto_filtro_form = TarefaProjetoFiltroForm(data=request.POST or None)
    if tarefa_projeto_filtro_form.is_valid():
        tarefas = projeto.tarefas_raiz(
            tarefa_projeto_filtro_form.cleaned_data.get('situacao'),
            tarefa_projeto_filtro_form.cleaned_data.get('prioridade'),
            tarefa_projeto_filtro_form.cleaned_data.get('tipo_ordenacao'),
        )
    else:
        tarefas = projeto.tarefas_raiz()
    tarefas_canceladas = projeto.tarefas_canceladas()

    return locals()


@rtr()
@permission_required('gerenciador_projetos.change_lista')
def adicionar_ou_vincular_lista_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = projeto.titulo
    if not projeto.pode_editar_listas(request.user):
        return httprr('..', 'Você não tem permissão para adicionar e/ou editar listas nesse projeto.', 'error')

    form = AdicionarOuVincularListaProjetoForm(request.POST or None, request=request, projeto=projeto)
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada com sucesso.')

    return locals()


@rtr()
@permission_required('gerenciador_projetos.add_tag')
def adicionar_tag(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = 'Adicionar tag'
    if not projeto.pode_editar_tags(request.user):
        return httprr('..', 'Você não tem permissão para adicionar e/ou editar listas nesse projeto.', 'error')

    form = TagForm(request.POST or None, request=request)
    if form.is_valid():
        tag = form.instance
        tag.projeto = projeto
        form.save()
        return httprr('..', 'Tag adicionada com sucesso.')

    return locals()


@rtr()
@permission_required('gerenciador_projetos.change_tag')
def editar_tag(request, tag_id):
    tag = get_object_or_404(Tag, pk=tag_id)
    title = 'Editar tag'
    if not tag.projeto.pode_editar_tags(request.user):
        return httprr('..', 'Você não tem permissão para adicionar e/ou editar listas nesse projeto.', 'error')

    form = TagForm(request.POST or None, request=request, instance=tag)
    if form.is_valid():
        tag = form.instance
        form.save()
        return httprr('..', 'Tag atualizada com sucesso.')

    return locals()


def _exigir_equipe(pode: bool) -> None:
    """A permissão do grupo (`change_tarefa` etc.) vem de ser gerente ou membro de *algum* projeto:
    toda view que altera um projeto ou uma tarefa precisa conferir também a equipe *deste* projeto."""
    if not pode:
        raise PermissionDenied('Você não está na equipe desse projeto.')


def _recusar_se_bloqueada(tarefa: Tarefa) -> HttpResponse | None:
    """Tarefa somente leitura (`Tarefa.bloqueada_para_novas_acoes`) não abre formulário nem grava."""
    if tarefa.bloqueada_para_novas_acoes:
        motivo = 'o projeto está encerrado' if tarefa.projeto.encerrado else f'a tarefa está {tarefa.get_situacao_display()}'
        return httprr(tarefa.get_absolute_url(), f'Não é possível alterar: {motivo}.', 'error', close_popup=True)
    return None


def _recusar_se_projeto_encerrado(tarefa: Tarefa) -> HttpResponse | None:
    if tarefa.projeto.encerrado:
        return httprr(tarefa.get_absolute_url(), 'Não é possível alterar: o projeto está encerrado.', 'error', close_popup=True)
    return None


def _recusar_edicao_ou_subtarefa_bloqueada(projeto: Projeto, tarefa_id: int | None, tarefa_pai: str | None) -> HttpResponse | None:
    """Editar tarefa travada ou criar subtarefa dentro dela também é alteração."""
    if tarefa_id:
        return _recusar_se_bloqueada(get_object_or_404(Tarefa, pk=tarefa_id, projeto=projeto))
    pai = Tarefa.objects.filter(pk=tarefa_pai, projeto=projeto).first() if tarefa_pai and tarefa_pai.isdecimal() else None
    return _recusar_se_bloqueada(pai) if pai else None


def _tarefa_da_equipe(tarefa_id: int, user: User) -> Tarefa:
    """Tarefa que o usuário pode alterar: gerente ou membro do projeto dela."""
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    _exigir_equipe(tarefa.projeto.pode_editar_tarefas(user))
    return tarefa


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def recorrencia_tarefa(request, tarefa_id):
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    title = tarefa.titulo
    form = RecorrenciaTarefaForm(request.POST or None, request=request)
    form.instance.tarefa = tarefa
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada com sucesso.')

    return locals()


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def remover_recorrencia_tarefa(request, recorrenciatarefa_id):
    recorrenciatarefa = get_object_or_404(RecorrenciaTarefa, pk=recorrenciatarefa_id)
    tarefa = recorrenciatarefa.tarefa
    _exigir_equipe(tarefa.projeto.pode_editar_tarefas(request.user))
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    if request.method == 'POST':
        recorrenciatarefa.delete()
        return httprr(tarefa.get_absolute_url(), 'Operação realizada com sucesso.')
    return locals()


@rtr('gerenciador_projetos/templates/confirmar_acao.html')
@permission_required('gerenciador_projetos.change_tarefa')
def reabrir_tarefa(request: HttpRequest, tarefa_id: int) -> dict[str, object] | HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    if not tarefa.pode_reabrir:
        return httprr(
            tarefa.get_absolute_url(), 'Só tarefa concluída ou cancelada, de projeto não encerrado, pode ser reaberta.', 'error', close_popup=True
        )
    form = ConfirmarAcaoForm(request.POST if request.method == 'POST' else None, rotulo='Reabrir tarefa')
    if not form.is_valid():
        title = f'Reabrir tarefa: {tarefa.titulo}'
        mensagem = 'A tarefa volta à situação Aberta e a data de conclusão é removida.'
        return locals()

    url = reverse('tarefa', args=[tarefa_id])
    try:
        tarefa.reabrir(request.user)
    except ValidationError as e:
        return httprr(url, str(e), 'error', close_popup=True)
    return httprr(url, 'A tarefa foi reaberta.', close_popup=True)


@rtr()
@permission_required('gerenciador_projetos.change_projeto')
def atualizar_posicao_lista_projeto(request, lista_projeto_id):
    listaprojeto = get_object_or_404(ListaProjeto, pk=lista_projeto_id)
    _exigir_equipe(listaprojeto.projeto.pode_editar_listas(request.user))
    title = listaprojeto.projeto.titulo
    form = AtualizarPosicaoListaProjetoForm(request.POST or None)
    if form.is_valid():
        posicao = form.cleaned_data.get('posicao')
        ListaProjeto.objects.filter(projeto=listaprojeto.projeto, posicao__gte=posicao).update(posicao=F('posicao') + 1)
        listaprojeto.posicao = posicao
        listaprojeto.save()
        count = 1
        for obj in ListaProjeto.objects.filter(projeto=listaprojeto.projeto).order_by('posicao'):
            ListaProjeto.objects.filter(pk=obj.pk).update(posicao=count)
            count += 1

        return httprr('..', 'Operação realizada com sucesso.')

    return locals()


@rtr('gerenciador_projetos/templates/dashboard.html')
@permission_required('gerenciador_projetos.view_projeto')
def dashboard(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')
    user = request.user
    pode_adicionar_listas = projeto.pode_adicionar_listas(user)
    pode_adicionar_tarefas = projeto.pode_adicionar_tarefas(user)
    pode_editar_projeto = projeto.pode_editar_projeto(user)
    pode_editar_tarefas = projeto.pode_editar_tarefas(user)
    title = f'Dashboard: {projeto.titulo}'

    listaprojeto = projeto.listaprojeto_set.filter(lista__ativa=True).order_by('posicao')
    listaprojeto_inativas = projeto.listaprojeto_set.filter(
        lista__pk__in=Tarefa.objects.filter(lista__ativa=False, projeto=projeto).values_list('lista__pk', flat=True)
    ).order_by('posicao')

    form_filtros = DashboardForm(request.POST or None, projeto=projeto)
    if form_filtros.is_valid():
        filtros = {}
        atribuido_a = form_filtros.cleaned_data.get('atribuido_a')
        situacao = form_filtros.cleaned_data.get('situacao')
        prioridade = form_filtros.cleaned_data.get('prioridade')
        exibir_concluidas = form_filtros.cleaned_data.get('exibir_concluidas')
        if atribuido_a:
            filtros['atribuido_a__in'] = atribuido_a
        if situacao:
            filtros['situacao'] = situacao
        if prioridade:
            filtros['prioridade'] = prioridade

    return locals()


@rtr('gerenciador_projetos/templates/calendario.html')
@permission_required('gerenciador_projetos.view_projeto')
def calendario(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')

    pode_editar_projeto = projeto.pode_editar_projeto(request.user)
    pode_editar_tarefas = projeto.pode_editar_tarefas(request.user)
    title = f'Calendário: {projeto.titulo}'
    tarefas = Tarefa.objects.filter(projeto=projeto, data_conclusao_estimada__isnull=False)

    hoje = datetime.today()
    data_inicio = hoje.replace(day=1)
    data_fim = data_inicio.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])

    form = FiltrarCalendarioForm(request.POST or None)

    if form.is_valid():
        data_inicio = form.cleaned_data.get('data_inicio')
        data_fim = form.cleaned_data.get('data_fim')
        tarefas = tarefas.filter(data_conclusao_estimada__gte=data_inicio, data_conclusao_estimada__lte=data_fim)
        situacao = form.cleaned_data.get('situacao')
        if situacao:
            tarefas = tarefas.filter(situacao=situacao)

    cal = CalendarioPlus()
    cal.mostrar_mes_e_ano = True

    for tarefa in tarefas.order_by('data_conclusao_estimada'):
        uo = f' - {escape(tarefa.uo)}' if tarefa.uo else ''
        descricao = f'<a href="{tarefa.get_absolute_url()}">{escape(tarefa.titulo)}{uo}</a>'
        cal.adicionar_evento_calendario(tarefa.data_conclusao_estimada, tarefa.data_conclusao_estimada, descricao, tarefa.get_situacao_tarefa_css())

    calendario = []
    for dt in rrule.rrule(rrule.MONTHLY, dtstart=data_inicio, until=data_fim):
        calendario.append(cal.formato_mes(dt.year, dt.month))

    return locals()


@rtr('gerenciador_projetos/templates/gantt.html')
@permission_required('gerenciador_projetos.view_projeto')
def gantt(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    title = f'Gantt: {projeto.titulo}'

    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')

    tarefas = Tarefa.objects.filter(projeto_id=projeto_id, data_inicio__isnull=False, data_conclusao_estimada__isnull=False).order_by(
        'lista', '-data_inicio'
    )
    pode_editar_projeto = projeto.pode_editar_projeto(request.user)
    pode_editar_tarefas = projeto.pode_editar_tarefas(request.user)
    if tarefas.exists():
        colors = []
        df = []
        for tarefa in tarefas:
            info = {
                'Task': tarefa.titulo,
                'Start': tarefa.data_inicio.strftime('%Y-%m-%d'),
                'Finish': tarefa.data_conclusao_estimada.strftime('%Y-%m-%d'),
            }
            df.append(info)
            colors.append(generate_color())
        fig = ff.create_gantt(
            df,
            colors=colors,
            index_col='Finish',
            show_colorbar=True,
            bar_width=0.2,
            showgrid_x=True,
            title='Gráfico de Gantt',
            height=900,
            width=1440,
        )
        fig['layout'].pop('height', None)
        fig['layout'].pop('width', None)
        # height = 600, width = 900
        # fig['layout'].update(autosize=False, height=900, width=1440, margin=dict(l=110))

        gantt = opy.plot(fig, auto_open=False, output_type='div')
    return locals()


@rtr()
@permission_required(['gerenciador_projetos.change_tarefa'])
def gerenciar_tarefa(request: HttpRequest, projeto_id: int, tarefa_id: int | None = None) -> dict[str, object] | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    permissao_ok = projeto.pode_adicionar_tarefas(request.user) if tarefa_id is None else projeto.pode_editar_tarefas(request.user)
    if not permissao_ok:
        return httprr('..', 'Você não tem permissão para adicionar e/ou editar tarefas nesse projeto.', 'error')

    title = projeto.titulo
    lista_id = request.GET.get('lista')
    lista = Lista.objects.get(pk=lista_id) if lista_id and projeto.listas_do_projeto().filter(lista__id=lista_id).exists() else None

    tarefa_pai = request.GET.get('tarefa_pai')
    eh_nova_tarefa = tarefa_id is None
    if recusa := _recusar_edicao_ou_subtarefa_bloqueada(projeto, tarefa_id, tarefa_pai):
        return recusa

    if tarefa_id:  # Alterando uma tarefa: a permissão foi conferida no projeto da URL, a tarefa tem de ser dele
        tarefa = get_object_or_404(Tarefa, pk=tarefa_id, projeto=projeto)
        lista_original_id = tarefa.lista_id
        FormClass = TarefaFormFactory(request, projeto=projeto, tarefa=tarefa, tarefa_pai=tarefa_pai)
        form = FormClass(request.POST or None, instance=tarefa)
    else:  # Adicionando uma tarefa
        lista_original_id = None
        FormClass = TarefaFormFactory(request, projeto=projeto, tarefa_pai=tarefa_pai)
        form = FormClass(request.POST or None)
        form.instance.projeto = projeto
        form.instance.criado_por = request.user
        if lista:
            form.instance.lista = lista

    if form.is_valid():
        lista_selecionada = form.cleaned_data.get('lista') if 'lista' in form.fields else None
        lista_efetiva = (lista or lista_selecionada) if eh_nova_tarefa else lista_selecionada
        lista_mudou = tarefa_id is not None and lista_original_id != (lista_efetiva.id if lista_efetiva else None)
        form.save()
        tarefa_salva = form.instance
        if (eh_nova_tarefa and lista_efetiva) or lista_mudou:
            tarefa_salva.mover_para_lista(lista_efetiva, request.user)
        if eh_nova_tarefa and projeto.situacao == SituacaoProjeto.ABERTO:
            messages.warning(request, 'Este projeto ainda está com situação Aberto, favor editar o projeto e corrigir a situação.')
        return httprr(form.instance.get_absolute_url(), 'Operação realizada com sucesso.')

    return locals()


@rtr('gerenciador_projetos/templates/confirmar_acao.html')
@permission_required(['gerenciador_projetos.delete_tarefa'])
def excluir_tarefa(request: HttpRequest, tarefa_id: int) -> dict[str, object] | HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    if recusa := _recusar_se_projeto_encerrado(tarefa):
        return recusa
    form = ConfirmarAcaoForm(request.POST if request.method == 'POST' else None, rotulo='Excluir tarefa')
    if not form.is_valid():
        title = f'Excluir tarefa: {tarefa.titulo}'
        mensagem = 'A tarefa e as subtarefas dela serão excluídas. Esta ação não pode ser desfeita.'
        return locals()
    projeto = tarefa.projeto
    tarefa.delete()
    return httprr(projeto.get_absolute_url(), 'Exclusão realizada com sucesso.')


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def gerenciar_link_tarefa(request: HttpRequest, tarefa_id: int, link_id: int | None = None) -> dict[str, object] | HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    title = 'Adicionar link' if link_id is None else 'Editar link'

    if link_id:
        link = get_object_or_404(LinkTarefa, pk=link_id, tarefa=tarefa)
        if not link.pode_editar(request.user):
            return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para editar este link.', 'error')
        form = LinkTarefaForm(request.POST or None, instance=link)
    else:
        if not tarefa.projeto.pode_editar_tarefas(request.user):
            return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para adicionar links a esta tarefa.', 'error')
        form = LinkTarefaForm(request.POST or None)
        form.instance.tarefa = tarefa
        form.instance.criado_por = request.user

    if form.is_valid():
        form.save()
        if link_id is None:
            Notificar.nova_atividade_tarefa(tarefa, 'link', request.user, f'{form.instance.titulo}: {form.instance.url}')
        return httprr(tarefa.get_absolute_url(), 'Link salvo com sucesso.', close_popup=True)

    return locals()


@rtr()
@permission_required(['gerenciador_projetos.change_tarefa'])
@require_POST
def excluir_link_tarefa(request: HttpRequest, link_id: int) -> HttpResponse:
    link = get_object_or_404(LinkTarefa, pk=link_id)
    tarefa = link.tarefa
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    if not link.pode_editar(request.user):
        return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para remover este link.', 'error')
    link.delete()
    return httprr(tarefa.get_absolute_url(), 'Link removido com sucesso.')


def _reordenar_checklist(tarefa: Tarefa, ordem: list[str]) -> None:
    """Atualiza a posição de cada item do checklist conforme a ordem recebida."""
    for posicao, item_id in enumerate(ordem):
        ItemChecklist.objects.filter(pk=item_id, tarefa=tarefa).update(posicao=posicao)


@rtr()
def gerenciar_checklist(request: HttpRequest, tarefa_id: int) -> HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    projeto = get_object_or_404(Projeto, pk=tarefa.projeto_id)
    if not projeto.pode_editar_tarefas(request.user):
        return httprr('..', 'Você não tem permissão para editar tarefas nesse projeto.', 'error')

    if request.method == 'GET':
        itens = list(tarefa.itens_checklist.order_by('posicao').values('id', 'descricao', 'concluido'))
        concluidos = sum(1 for item in itens if item['concluido'])
        total = len(itens)
        return JsonResponse({'itens': itens, 'concluidos': concluidos, 'total': total})

    # Post requests handle adding and updating checklist items
    if request.method == 'POST':
        if recusa := _recusar_se_bloqueada(tarefa):
            return recusa

        action = request.POST.get('action')

        if action == 'reordenar':
            _reordenar_checklist(tarefa, request.POST.getlist('ordem[]'))
            return JsonResponse({'ok': True})

        descricao = request.POST.get('descricao', '').strip()
        if action == 'add' and descricao:
            proxima_posicao = tarefa.itens_checklist.count()
            novo_item = ItemChecklist.objects.create(tarefa=tarefa, descricao=descricao, posicao=proxima_posicao)
            return JsonResponse({'id': novo_item.id, 'descricao': novo_item.descricao, 'concluido': novo_item.concluido})

        item_id = request.POST.get('item_id')
        item = get_object_or_404(ItemChecklist, pk=item_id, tarefa=tarefa)

        if action == 'toggle':
            item.concluido = not item.concluido
            item.save()
            return JsonResponse({'id': item.id, 'concluido': item.concluido})

        if action == 'delete':
            item.delete()
            return JsonResponse({'message': 'Item excluído com sucesso.'}, status=204)

        return JsonResponse({'error': 'Ação inválida.'}, status=400)

    # return HttpResponse(status=400)


@permission_required(['gerenciador_projetos.change_tarefa'])
def gerenciar_tarefa_api(request: HttpRequest, projeto_id: int) -> JsonResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.pode_adicionar_tarefas(request.user):
        return JsonResponse({'ok': False})

    lista_id = request.POST.get('lista')
    lista = Lista.objects.get(pk=lista_id) if lista_id and projeto.listas_do_projeto().filter(lista__id=lista_id).exists() else None
    titulo = request.POST.get('titulo')

    tarefa = Tarefa(titulo=titulo, lista=lista, criado_por=request.user, projeto=projeto)

    tarefa.save()
    if tarefa.id is not None:
        return JsonResponse({'ok': True})
    else:
        return JsonResponse({'ok': False})


@rtr('gerenciador_projetos/templates/tarefa.html')
@permission_required('gerenciador_projetos.view_tarefa')
def tarefa(request, tarefa_id):
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if not tarefa.projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')
    tarefa_concluida = tarefa.situacao == SituacaoTarefa.CONCLUIDA
    tem_historico_sem_observacoes = tarefa.get_historicoevolucao().filter(mensagem_automatica=False).exists()
    projeto = tarefa.projeto
    pode_editar_tarefas = tarefa.projeto.pode_editar_tarefas(request.user)
    eh_membro_projeto = tarefa.projeto.eh_membro_projeto(request.user)
    pode_registrar_evolucao = all(
        [request.user.has_perm('gerenciador_projetos.change_historicoevolucao'), pode_editar_tarefas, not tarefa.bloqueada_para_novas_acoes]
    )
    eh_observador = tarefa.observadores.filter(pk=request.user.pk).exists()
    pode_adicionar_observador = pode_editar_tarefas and not eh_observador
    if tarefa.uo:
        title = f'Tarefa: {tarefa.uo} - {tarefa.titulo}'
    else:
        title = f'Tarefa: {tarefa.titulo}'
    return locals()


@require_POST
@permission_required('gerenciador_projetos.change_tarefa')
def adicionar_observador(request: HttpRequest, tarefa_id: int) -> HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if not tarefa.projeto.pode_editar_tarefas(request.user):
        return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para se adicionar como observador desta tarefa.')
    if tarefa.observadores.filter(pk=request.user.pk).exists():
        return httprr(tarefa.get_absolute_url(), 'Você já é observador desta tarefa.')
    tarefa.observadores.add(request.user)
    return httprr(tarefa.get_absolute_url(), 'Você foi adicionado como observador desta tarefa.')


@require_POST
@permission_required('gerenciador_projetos.view_tarefa')
def remover_observador(request: HttpRequest, tarefa_id: int) -> HttpResponse:
    """Quem observa sai sozinho da lista, sem precisar editar a tarefa (vale também para tarefa travada)."""
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if not tarefa.observadores.filter(pk=request.user.pk).exists():
        return httprr(tarefa.get_absolute_url(), 'Você não é observador desta tarefa.', 'warning')
    tarefa.observadores.remove(request.user)
    return httprr(tarefa.get_absolute_url(), 'Você deixou de observar esta tarefa.')


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def alterar_atribuidos_tarefa(request: HttpRequest, tarefa_id: int) -> dict[str, object] | HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    title = f'Atribuições: {tarefa.titulo}'
    if not tarefa.projeto.pode_editar_tarefas(request.user):
        return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para alterar as atribuições desta tarefa.', 'error')
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa

    form = AlterarAtribuidosTarefaForm(request.POST or None, instance=tarefa, usuario=request.user)
    if form.is_valid():
        form.save()
        return httprr(tarefa.get_absolute_url(), 'Atribuições atualizadas com sucesso.', close_popup=True)

    return locals()


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def alterar_situacao_tarefa(request: HttpRequest, tarefa_id: int, situacao: int) -> dict[str, object] | HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    title = f'Alterar situação: {tarefa.titulo}'
    if not tarefa.projeto.pode_editar_tarefas(request.user):
        return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para alterar a situação desta tarefa.', 'error')
    if not tarefa.pode_alterar_situacao:
        return httprr(
            tarefa.get_absolute_url(), 'Não é possível alterar a situação: tarefa concluída ou cancelada (use Reabrir) ou projeto encerrado.', 'error'
        )
    if situacao not in dict(SituacaoTarefa.choices):
        raise Http404('Situação inválida.')

    form = AlterarSituacaoTarefaForm(request.POST or None, tarefa=tarefa, situacao=situacao)
    situacao_atual_label = tarefa.get_situacao_display()
    nova_situacao_label = dict(SituacaoTarefa.choices)[situacao]
    if request.method == 'POST' and form.is_valid():
        form.processar()
        return httprr(tarefa.get_absolute_url(), 'Situação da tarefa alterada com sucesso.', close_popup=True)

    return locals()


@permission_required('gerenciador_projetos.change_tarefa')
def alterar_progresso_tarefa(request: HttpRequest, tarefa_id: int, percentual: int) -> HttpResponse:
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    if not tarefa.projeto.pode_editar_tarefas(request.user):
        return httprr(tarefa.get_absolute_url(), 'Você não tem permissão para alterar o progresso desta tarefa.', 'error')
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    if percentual not in Tarefa.PROGRESSOS_RAPIDOS:
        raise Http404('Percentual inválido.')
    if request.method != 'POST':
        return httprr(tarefa.get_absolute_url())

    tarefa.alterar_progresso(percentual)
    return httprr(tarefa.get_absolute_url(), 'Progresso atualizado com sucesso.')


@rtr('gerenciador_projetos/templates/confirmar_acao.html')
@permission_required('gerenciador_projetos.change_projeto')
def clonar_projeto(request: HttpRequest, projeto_id: int) -> dict[str, object] | HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)
    _exigir_equipe(projeto.pode_editar_projeto(request.user))
    form = ConfirmarAcaoForm(request.POST if request.method == 'POST' else None, rotulo='Clonar projeto')
    if not form.is_valid():
        title = f'Clonar projeto: {projeto.titulo}'
        mensagem = 'Será criada uma cópia do projeto, com as tarefas, listas e tags, tendo você como gerente.'
        return locals()
    copia = projeto.clonar(request.user)
    return httprr(copia.get_absolute_url(), 'Operação realizada com sucesso.')


@rtr('gerenciador_projetos/templates/confirmar_acao.html')
@permission_required('gerenciador_projetos.change_tarefa')
def clonar_tarefa(request: HttpRequest, tarefa_id: int) -> dict[str, object] | HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    if recusa := _recusar_se_projeto_encerrado(tarefa):
        return recusa
    form = ConfirmarAcaoForm(request.POST if request.method == 'POST' else None, rotulo='Clonar tarefa')
    if not form.is_valid():
        title = f'Clonar tarefa: {tarefa.titulo}'
        mensagem = 'Será criada uma cópia da tarefa no mesmo projeto.'
        return locals()
    copia = tarefa.clonar(request.user)
    return httprr(copia.get_absolute_url(), 'Operação realizada com sucesso.')


@require_POST
@permission_required('gerenciador_projetos.change_tarefa')
def atribuir_a_mim(request: HttpRequest, tarefa_id: int) -> HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa
    tarefa.atribuir_para(request.user)
    return httprr(tarefa.projeto.get_absolute_url(), 'Atribuição realizada com sucesso.')


@rtr()
@permission_required('gerenciador_projetos.change_historicoevolucao')
def gerenciar_historicoevolucao(request: HttpRequest, tarefa_id: int, historicoevolucao_id: int | None = None) -> dict[str, object] | HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    title = 'Registrar evolução'

    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa

    if historicoevolucao_id:
        historicoevolucao = get_object_or_404(HistoricoEvolucao, pk=historicoevolucao_id, tarefa=tarefa)
        form = HistoricoEvolucaoForm(request.POST or None, request.FILES or None, instance=historicoevolucao, tarefa=tarefa)
    else:
        form = HistoricoEvolucaoForm(request.POST or None, request.FILES or None, tarefa=tarefa)
        form.instance.tarefa = tarefa

    form.instance.registrado_por = request.user
    if form.is_valid():
        novo_registro = historicoevolucao_id is None
        form.save()
        if novo_registro and form.cleaned_data.get('comentario'):
            Notificar.nova_atividade_tarefa(tarefa, 'comentário', request.user, form.cleaned_data['comentario'])
        if novo_registro and form.cleaned_data.get('anexo'):
            Notificar.nova_atividade_tarefa(tarefa, 'anexo', request.user, form.cleaned_data['anexo'].name)
        link_titulo = form.cleaned_data.get('link_titulo')
        link_url = form.cleaned_data.get('link_url')
        if link_titulo and link_url:
            LinkTarefa.objects.create(tarefa=tarefa, titulo=link_titulo, url=link_url, criado_por=request.user)
            Notificar.nova_atividade_tarefa(tarefa, 'link', request.user, f'{link_titulo}: {link_url}')
        return httprr('..', 'Evolução registrada com sucesso.')

    return locals()


@rtr()
@permission_required('gerenciador_projetos.change_historicoevolucao')
def adicionar_comentario_rapido_tarefa(request: HttpRequest, tarefa_id: int) -> HttpResponse:
    """Registra um comentário simples de Histórico de Evolução a partir do mini-form
    exibido acima da listagem da aba "Evolução" (sem anexo/percentual/link)."""
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    _exigir_equipe(tarefa.projeto.pode_adicionar_comentarios(request.user))

    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa

    form = ComentarioRapidoTarefaForm(request.POST or None)
    form.instance.tarefa = tarefa
    form.instance.registrado_por = request.user
    if form.is_valid():
        form.save()
        Notificar.nova_atividade_tarefa(tarefa, 'comentário', request.user, form.cleaned_data['comentario'])
        return httprr(tarefa.get_absolute_url() + '?tab=historico', 'Comentário adicionado com sucesso.')

    return httprr(tarefa.get_absolute_url() + '?tab=historico', 'Não foi possível adicionar o comentário.', 'error')


@rtr()
@permission_required('gerenciador_projetos.change_historicoevolucao')
def adicionar_anexo(request: HttpRequest, tarefa_id: int) -> dict[str, object] | HttpResponse:
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    title = tarefa.titulo

    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa

    form = AdicionarAnexoForm(request.POST or None, request.FILES or None, tarefa=tarefa)
    form.instance.tarefa = tarefa
    form.instance.registrado_por = request.user
    if form.is_valid():
        form.save()
        Notificar.nova_atividade_tarefa(tarefa, 'anexo', request.user, form.cleaned_data['anexo'].name)
        return httprr('..', 'Anexo adicionado com sucesso.')

    return locals()


@rtr()
@permission_required(['gerenciador_projetos.change_tarefa'])
def atribuir_tarefa_a_campus(request, tarefa_id):
    title = 'Atribuir tarefa a campus'
    tarefa = get_object_or_404(Tarefa, pk=tarefa_id)
    projeto = get_object_or_404(Projeto, pk=tarefa.projeto_id)
    if not projeto.pode_editar_tarefas(request.user):
        return httprr('..', 'Você não tem permissão para adicionar e/ou editar tarefas nesse projeto.', 'error')

    if recusa := _recusar_se_bloqueada(tarefa):
        return recusa

    form = AtribuirTarefaACampus(request.POST or None)
    if form.is_valid():
        form.processar(tarefa, request.user)
        return httprr(projeto.get_absolute_url(), 'Vínculo realizado com sucesso.')

    return locals()


@require_POST
@permission_required('gerenciador_projetos.change_historicoevolucao')
def mudarlista(request, tarefa_id, lista_id, posicao):
    tarefa = _tarefa_da_equipe(tarefa_id, request.user)
    # Organizar o quadro vale para tarefa encerrada (levar à coluna "Feito"), não para projeto encerrado.
    if posicao < 2 or tarefa.projeto.encerrado:
        return JsonResponse({'erro': True})
    posicao = posicao - 2
    # A lista precisa ser uma coluna do quadro deste projeto.
    lista = get_object_or_404(Lista, pk=lista_id, listaprojeto__projeto=tarefa.projeto) if int(lista_id) != 0 else None
    ListaTarefa.objects.filter(tarefa=tarefa, data_hora_saida__isnull=True).update(data_hora_saida=datetime.now())
    if lista:
        tarefa.lista = lista
        for index, item in enumerate(ListaTarefa.objects.filter(lista=lista, data_hora_saida__isnull=True).order_by('posicao')):
            if index >= posicao:
                index += 1
            item.posicao = index
            item.save()
        ListaTarefa.objects.create(lista=lista, tarefa=tarefa, posicao=posicao, registrado_por=request.user)
    else:
        tarefa.lista = None
    tarefa.save()
    return JsonResponse({'ok': True})


@rtr()
@permission_required('gerenciador_projetos.change_tarefa')
def minhas_tarefas(request):
    title = 'Minhas tarefas'

    tarefas_andamento = Tarefa.objects_card().filter(atribuido_a=request.user).exclude(situacao=SituacaoTarefa.CONCLUIDA)
    tarefas_concluidas = Tarefa.objects_card().filter(atribuido_a=request.user, situacao=SituacaoTarefa.CONCLUIDA)

    form_filtros = MinhasTarefasForm(request.POST or None, usuario=request.user)
    if form_filtros.is_valid():
        tarefas_andamento = tarefas_andamento.filter(projeto=form_filtros.cleaned_data['projeto'])
        tarefas_concluidas = tarefas_concluidas.filter(projeto=form_filtros.cleaned_data['projeto'])

    return locals()


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def status_projeto(request: HttpRequest, projeto_id: int) -> HttpResponse:
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')

    pode_editar_tarefas = projeto.pode_editar_tarefas(request.user)
    pode_adicionar_tarefas = projeto.pode_adicionar_tarefas(request.user)
    pode_editar_projeto = projeto.pode_editar_projeto(request.user)

    title = f'Tarefas por situação: {projeto}'

    lista_tarefas = []
    tarefas = projeto.tarefas_raiz()
    subtarefas = Tarefa.objects_card().filter(tarefa_pai__in=tarefas)
    lista_tarefas.extend(list(tarefas))
    lista_tarefas.extend(list(subtarefas))
    lista_tarefas.sort(
        key=lambda tarefa: (
            tarefa.data_conclusao_estimada is None,
            tarefa.data_conclusao_estimada or date.max,
            tarefa.prioridade,
            -(tarefa.percentual_executado or 0),
            tarefa.pk,
        )
    )

    ordem_situacoes = [
        SituacaoTarefa.ABERTA,
        SituacaoTarefa.EM_ANDAMENTO,
        SituacaoTarefa.EM_ANALISE,
        SituacaoTarefa.SUSPENSA,
        SituacaoTarefa.CONCLUIDA,
        SituacaoTarefa.CANCELADA,
    ]
    situacoes = [(codigo, dict(SituacaoTarefa.choices)[codigo]) for codigo in ordem_situacoes]
    tarefas_por_situacao = [(codigo, rotulo, [tarefa for tarefa in lista_tarefas if tarefa.situacao == codigo]) for codigo, rotulo in situacoes]

    return locals()


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def evolucao_tarefas_projeto(request, projeto_id):
    projeto = get_object_or_404(Projeto, pk=projeto_id)

    if not projeto.pode_ver_projeto(request.user):
        raise PermissionDenied('Você não está na equipe desse projeto.')

    title = f'Evolução das tarefas: {projeto}'

    historico = HistoricoEvolucao.objects.filter(tarefa__projeto=projeto).order_by('-data_hora')

    pode_editar_projeto = projeto.pode_editar_projeto(request.user)
    pode_editar_tarefas = projeto.pode_editar_tarefas(request.user)

    form = BuscaHistoricoEvolucaoForm(request.POST or None)
    if form.is_valid():
        di = form.cleaned_data.get('data_inicio')
        df = form.cleaned_data.get('data_final')

        if di or df:
            if di and df:
                historico = historico.filter(data_hora__gte=di, data_hora__lte=df)
            elif di and not df:
                historico = historico.filter(data_hora__gte=di)
            else:
                historico = historico.filter(data_hora__lte=df)

    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_gerenciador_projetos(request, data, datahora_inicio, datahora_fim):
    qs_tarefas = Tarefa.objects.select_related(
        'uo',
    ).prefetch_related(
        'atribuido_a',
    )

    qs_historico_evolucao_tarefas = HistoricoEvolucao.objects.select_related(
        'tarefa',
        'registrado_por',
    )

    qs_projetos = Projeto.objects.select_related(
        'criado_por',
    )

    filters_tarefas_abertas = {}
    filters_tarefas_iniciadas = {}
    filters_historico_evolucao_tarefas = {}
    filters_tarefas_concluidas = {}
    filters_projetos = {}

    if datahora_inicio:
        filters_tarefas_abertas['aberto_em__gte'] = datahora_inicio
        filters_tarefas_iniciadas['data_inicio__gte'] = datahora_inicio
        filters_historico_evolucao_tarefas['data_hora__gte'] = datahora_inicio
        filters_tarefas_concluidas['data_conclusao__gte'] = datahora_inicio
        filters_projetos['criado_em__gte'] = datahora_inicio

    if datahora_fim:
        filters_tarefas_abertas['aberto_em__lte'] = datahora_fim
        filters_tarefas_iniciadas['data_inicio__lte'] = datahora_fim
        filters_historico_evolucao_tarefas['data_hora__lte'] = datahora_fim
        filters_tarefas_concluidas['data_conclusao__lte'] = datahora_fim
        filters_projetos['criado_em__lte'] = datahora_fim

    qs_tarefas_em_andamento_abertas = qs_tarefas.filter(
        atribuido_a=request.user, situacao=SituacaoTarefa.EM_ANDAMENTO, data_inicio__isnull=True, **filters_tarefas_abertas
    ).order_by('aberto_em')
    qs_tarefas_em_andamento_iniciadas = qs_tarefas.filter(
        atribuido_a=request.user, situacao=SituacaoTarefa.EM_ANDAMENTO, data_inicio__isnull=False, **filters_tarefas_iniciadas
    ).order_by('data_inicio')

    for tarefa in qs_tarefas_em_andamento_abertas | qs_tarefas_em_andamento_iniciadas:
        titulo = f'{tarefa.uo} - {tarefa.titulo}' if tarefa.uo else tarefa.titulo
        data.append(
            (
                'Gerenciador de Projetos',
                'Tarefas em andamento iniciadas' if tarefa.data_inicio else 'Tarefas em andamento abertas',
                titulo,
                f'em {tarefa.data_inicio.strftime("%d/%m/%Y")}' if tarefa.data_inicio else f'em {tarefa.aberto_em.strftime("%d/%m/%Y às %H:%M")}',
                f'{tarefa.get_absolute_url()}',
            )
        )

    qs_tarefas_em_andamento_evoluidas = (
        qs_tarefas.annotate(
            data_hora_ultima_evolucao_registrada_por_mim=models.Subquery(
                qs_historico_evolucao_tarefas.filter(
                    tarefa__pk=models.OuterRef('pk'), registrado_por=request.user, **filters_historico_evolucao_tarefas
                )
                .order_by('-data_hora')[:1]
                .values('data_hora')
            ),
        )
        .filter(situacao=SituacaoTarefa.EM_ANDAMENTO, data_hora_ultima_evolucao_registrada_por_mim__isnull=False)
        .order_by('data_hora_ultima_evolucao_registrada_por_mim')
        .distinct()
    )

    for tarefa in qs_tarefas_em_andamento_evoluidas:
        titulo = f'{tarefa.uo} - {tarefa.titulo}' if tarefa.uo else tarefa.titulo
        data.append(
            (
                'Gerenciador de Projetos',
                'Tarefas em andamento evoluídas',
                titulo,
                f'em {tarefa.data_hora_ultima_evolucao_registrada_por_mim.strftime("%d/%m/%Y às %H:%M")}',
                f'{tarefa.get_absolute_url()}',
            )
        )

    qs_tarefas_concluidas = qs_tarefas.filter(
        atribuido_a=request.user, situacao=SituacaoTarefa.CONCLUIDA, data_conclusao__isnull=False, **filters_tarefas_concluidas
    ).order_by('data_conclusao')
    for tarefa in qs_tarefas_concluidas:
        titulo = f'{tarefa.uo} - {tarefa.titulo}' if tarefa.uo else tarefa.titulo
        data.append(
            (
                'Gerenciador de Projetos',
                'Tarefas concluídas',
                titulo,
                f'em {tarefa.data_conclusao.strftime("%d/%m/%Y")}',
                f'{tarefa.get_absolute_url()}',
            )
        )

    qs_projetos_criados = qs_projetos.filter(criado_por_id=request.user.id, **filters_projetos).order_by('criado_em')
    for projeto in qs_projetos_criados:
        data.append(
            (
                'Gerenciador de Projetos',
                'Projetos criados',
                projeto,
                f'em {projeto.criado_em.strftime("%d/%m/%Y")}',
                f'{projeto.get_absolute_url()}',
            )
        )


def _contexto_comparacao(request: HttpRequest) -> dict[str, object]:
    """Seleção comum às visões de comparação: os projetos pedidos que o usuário pode ver."""
    if not Projeto.eh_monitor_projetos(request.user):
        raise PermissionDenied('A comparação de projetos é exclusiva do grupo Monitor de Projetos.')
    projetos = projetos_selecionados(request.user, request.GET.getlist('projeto'))
    return {
        'form': CompararProjetosForm(initial={'projeto': projetos}, usuario=request.user),
        'projetos': projetos,
        'querystring': '&'.join(f'projeto={projeto.pk}' for projeto in projetos),
        # Sem seleção a caixa abre, para o formulário ser a primeira coisa na tela.
        'classe_caixa_selecao': 'mb-3 collapsed' if projetos else 'mb-3',
    }


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def comparar_projetos(request: HttpRequest) -> dict[str, object]:
    contexto = _contexto_comparacao(request)
    return {'title': 'Comparar projetos', **contexto, 'indicadores': indicadores(contexto['projetos'], date.today())}


# Cor da barra de cada projeto no Gantt da comparação, pelo status de prazo.
CORES_STATUS_PRAZO = {
    StatusPrazo.NO_PRAZO: '#2e7d32',
    StatusPrazo.ATRASADO: '#c62828',
    StatusPrazo.CONCLUIDO: '#1565c0',
    StatusPrazo.CANCELADO: '#757575',
    StatusPrazo.SEM_PRAZO: '#9e9e9e',
}


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def comparar_projetos_graficos(request: HttpRequest) -> dict[str, object]:
    contexto = _contexto_comparacao(request)
    lista = indicadores(contexto['projetos'], date.today())
    rotulos = dict(SituacaoTarefa.choices)
    grafico_evolucao = BarChart('grafico_evolucao', title='Evolução (%)', data=[[i.projeto.titulo, round(i.progresso)] for i in lista])
    grafico_situacoes = StackedGroupedColumnChart(
        'grafico_situacoes',
        title='Tarefas por situação',
        groups=[rotulos[codigo] for codigo in ORDEM_SITUACOES],
        data=[[i.projeto.titulo, *i.contagens_ordenadas] for i in lista],
    )
    grafico_evolucao.yAxis = {'title': {'text': '%'}, 'max': 100}
    # O StackedGroupedColumnChart empilha em percentual; aqui interessam as quantidades.
    grafico_situacoes.plotOptions['column']['stacking'] = 'normal'
    grafico_situacoes.yAxis = {'title': {'text': 'Tarefas'}}
    return {
        'title': 'Comparar projetos: gráficos',
        **contexto,
        'indicadores': lista,
        'grafico_evolucao': grafico_evolucao,
        'grafico_situacoes': grafico_situacoes,
    }


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def comparar_projetos_gantt(request: HttpRequest) -> dict[str, object]:
    contexto = _contexto_comparacao(request)
    lista = indicadores(contexto['projetos'], date.today())
    com_datas = [i for i in lista if i.fim]
    gantt = None
    if com_datas:
        linhas = [
            {'Task': i.projeto.titulo, 'Start': i.inicio.isoformat(), 'Finish': i.fim.isoformat(), 'Resource': i.status_prazo} for i in com_datas
        ]
        status_presentes = {i.status_prazo for i in com_datas}
        cores = {status: cor for status, cor in CORES_STATUS_PRAZO.items() if status in status_presentes}
        fig = ff.create_gantt(linhas, colors=cores, index_col='Resource', show_colorbar=True, group_tasks=True, showgrid_x=True, title='Projetos')
        fig['layout'].pop('height', None)
        fig['layout'].pop('width', None)
        gantt = opy.plot(fig, auto_open=False, output_type='div')
    return {'title': 'Comparar projetos: Gantt', **contexto, 'gantt': gantt, 'sem_datas': [i.projeto for i in lista if not i.fim]}


@rtr()
@permission_required('gerenciador_projetos.view_projeto')
def comparar_projetos_calendario(request: HttpRequest) -> dict[str, object]:
    contexto = _contexto_comparacao(request)
    dados = None
    if 'data_inicio' in request.GET:
        # Os ocultos voltam com o que veio na URL; trocá-los pela seleção já validada evita que
        # um id alheio ou inválido derrube o filtro de período.
        dados = request.GET.copy()
        dados.setlist('projeto', [str(projeto.pk) for projeto in contexto['projetos']])
    form_calendario = CompararCalendarioForm(dados, projetos=contexto['projetos'])
    data_inicio, data_fim = form_calendario.fields['data_inicio'].initial, form_calendario.fields['data_fim'].initial
    tarefas = Tarefa.objects.filter(projeto__in=contexto['projetos'], data_conclusao_estimada__isnull=False).select_related('projeto')
    if form_calendario.is_bound and form_calendario.is_valid():
        data_inicio, data_fim = form_calendario.cleaned_data['data_inicio'], form_calendario.cleaned_data['data_fim']
        if form_calendario.cleaned_data.get('situacao'):
            tarefas = tarefas.filter(situacao=form_calendario.cleaned_data['situacao'])

    cal = CalendarioPlus()
    cal.mostrar_mes_e_ano = True
    for tarefa in tarefas.filter(data_conclusao_estimada__range=(data_inicio, data_fim)).order_by('data_conclusao_estimada'):
        descricao = f'<a href="{tarefa.get_absolute_url()}">{escape(tarefa.projeto.titulo)}: {escape(tarefa.titulo)}</a>'
        cal.adicionar_evento_calendario(tarefa.data_conclusao_estimada, tarefa.data_conclusao_estimada, descricao, tarefa.get_situacao_tarefa_css())
    meses = rrule.rrule(rrule.MONTHLY, dtstart=data_inicio.replace(day=1), until=data_fim)
    return {
        'title': 'Comparar projetos: calendário',
        **contexto,
        'form_calendario': form_calendario,
        'calendario': [cal.formato_mes(dt.year, dt.month) for dt in meses],
    }
