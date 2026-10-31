from datetime import date

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.safestring import mark_safe

from djtools import tasks
from djtools.contrib.admin import ModelAdminPlus, PermissionDenied
from djtools.contrib.admin.filters import CustomTabListFilter
from djtools.templatetags.filters import status
from djtools.templatetags.tags import icon
from gerenciador_projetos.enums import SituacaoProjeto
from gerenciador_projetos.forms import ListaForm, ProjetoForm, TagForm, TipoAtividadeForm
from gerenciador_projetos.models import Lista, Projeto, Tag, TipoAtividade
from gerenciador_projetos.portfolio import indicadores, projetos_visiveis


CABECALHO_XLS = [
    'Projeto',
    'Áreas',
    'Campus',
    'Gerentes',
    'Situação',
    'Evolução (%)',
    'Prazo',
    'Abertas',
    'Em andamento',
    'Em análise',
    'Suspensas',
    'Concluídas',
    'Canceladas',
    'Atrasadas',
    'Vencendo em 7 dias',
    'Conclusão estimada',
    'Conclusão',
]


class ProjetoAdmin(ModelAdminPlus):
    form = ProjetoForm
    list_display = ('get_acoes', 'titulo', 'get_areas', 'get_gerentes', 'get_membros', 'get_situacao_display', 'get_qtd_tarefas', 'get_opcoes')
    list_display_icons = False
    search_fields = ('titulo', 'descricao')
    list_filter = (CustomTabListFilter, 'areas', 'gerentes', 'situacao')
    show_count_on_tabs = True
    actions = ['comparar_projetos', 'exportar_projetos']
    export_to_xls = True

    @admin.display(description='Ações')
    def get_acoes(self, obj):
        texto = icon('view', f'/gerenciador_projetos/projeto/{obj.id:d}/')
        if obj.pode_editar_projeto():
            texto = texto + icon('edit', f'/admin/gerenciador_projetos/projeto/{obj.id:d}/change')
        return mark_safe(texto)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(f'/gerenciador_projetos/projeto/{obj.id:d}/')

    def response_change(self, request, obj):
        return HttpResponseRedirect(f'/gerenciador_projetos/projeto/{obj.id:d}/')

    @admin.display(description='Áreas')
    def get_areas(self, obj):
        lista = ['<ul>']
        for area in obj.areas.all():
            lista.append(f'<li>{area}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    @admin.display(description='Membros')
    def get_membros(self, obj):
        lista = ['<ul>']
        for user in obj.membros.all():
            lista.append(f'<li>{user} ({user.get_vinculo().setor})</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    @admin.display(description='Tarefas')
    def get_qtd_tarefas(self, obj):
        return obj.tarefa_set.count()

    @admin.display(description='Situação')
    def get_situacao_display(self, obj):
        return status(obj.get_situacao_display())

    @admin.display(description='Opções')
    def get_opcoes(self, obj):
        return mark_safe(
            '<ul class="action-bar">'
            f'<li><a href="/gerenciador_projetos/projeto/{obj.id}/dashboard/" class="btn default"><span class="fas fa-columns" aria-hidden="true"></span> Dashboard</a></li>'
            '</ul>'
        )

    def get_actions(self, request: HttpRequest) -> dict[str, tuple[object, str, str]]:
        acoes = super().get_actions(request)
        # A comparação é a visão de carteira da gestão: só o grupo Monitor de Projetos a vê.
        if not Projeto.eh_monitor_projetos(request.user):
            acoes.pop('comparar_projetos', None)
        return acoes

    @admin.action(description='Comparar projetos selecionados')
    def comparar_projetos(self, request: HttpRequest, queryset: QuerySet[Projeto]) -> HttpResponseRedirect:
        ids = '&'.join(f'projeto={pk}' for pk in queryset.values_list('pk', flat=True))
        return HttpResponseRedirect(f'{reverse("comparar_projetos")}?{ids}')

    @admin.action(description='Exportar projetos selecionados para XLS')
    def exportar_projetos(self, request: HttpRequest, queryset: QuerySet[Projeto]) -> HttpResponse:
        return tasks.admin_export('xls', queryset, request, self)

    def to_xls(self, request: HttpRequest, queryset: QuerySet[Projeto], processo: object) -> list[list[object]]:
        """Planilha de projetos com os mesmos indicadores do painel de comparação (`portfolio.indicadores`).

        Vale para o botão "Exportar para XLS" (o que a listagem mostra) e para a ação com os
        selecionados; nos dois casos o queryset já vem filtrado pela visibilidade do usuário.
        """
        linhas: list[list[object]] = [CABECALHO_XLS]
        for i in indicadores(queryset, date.today()):
            projeto = i.projeto
            linhas.append(
                [
                    projeto.titulo,
                    ', '.join(str(area) for area in projeto.areas.all()),
                    projeto.uo,
                    ', '.join(str(gerente) for gerente in projeto.gerentes.all()),
                    projeto.get_situacao_display(),
                    round(i.progresso),
                    i.status_prazo,
                    *i.contagens_ordenadas,
                    i.atrasadas,
                    i.vencendo,
                    projeto.data_conclusao_estimada,
                    projeto.data_conclusao,
                ]
            )
        return linhas

    def get_queryset(self, request: HttpRequest) -> QuerySet[Projeto]:
        return super().get_queryset(request).filter(pk__in=projetos_visiveis(request.user).values('pk'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        projeto = get_object_or_404(Projeto, pk=object_id)
        if not projeto.pode_editar_projeto(request.user):
            raise PermissionDenied
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description='Gerentes')
    def get_gerentes(self, obj):
        lista = ['<ul>']
        for user in obj.gerentes.all():
            lista.append(f'<li>{user} ({user.get_vinculo().setor})</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    @admin.display(description='Ativos')
    def tab_ativos(self, request, queryset):
        return queryset.exclude(situacao__in=[SituacaoProjeto.CONCLUIDO, SituacaoProjeto.CANCELADO])

    @admin.display(description='Concluídos')
    def tab_concluidos(self, request, queryset):
        return queryset.filter(situacao=SituacaoProjeto.CONCLUIDO)

    def get_tabs(self, request):
        return ['tab_ativos', 'tab_concluidos', 'tab_any_data']


admin.site.register(Projeto, ProjetoAdmin)


class ListaAdmin(ModelAdminPlus):
    form = ListaForm
    search_fields = ('nome',)
    list_display = ('nome', 'ativa', 'criada_por')
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.filter(criada_por=request.user)
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.criada_por = request.user
        super().save_model(request, obj, form, change)


admin.site.register(Lista, ListaAdmin)


class TagAdmin(ModelAdminPlus):
    form = TagForm
    search_fields = ('nome',)
    list_filter = ('projeto',)
    list_display = ('projeto', 'nome', 'cor')
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.has_group_cached('centralservicos Administrador')):
            return qs  # .filter(projeto__id=request.user.id)
        return qs


admin.site.register(Tag, TagAdmin)


class TipoAtividadeAdmin(ModelAdminPlus):
    form = TipoAtividadeForm
    search_fields = ('nome',)
    list_display = ('nome',)
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.has_group_cached('centralservicos Administrador')):
            return qs  # .filter(projeto__id=request.user.id)
        return qs


admin.site.register(TipoAtividade, TipoAtividadeAdmin)
