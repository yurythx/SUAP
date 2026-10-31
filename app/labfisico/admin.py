from django.contrib import admin
from django.urls import path, reverse
from django.utils.safestring import mark_safe

from agendamento.status import SolicitacaoAgendamentoStatus

#
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, ModelAdminPlus
from djtools.contrib.admin.filters import PassThroughFilter
from djtools.utils import get_datetime_now, httprr

#
from rh.models import UnidadeOrganizacional

from .forms import GuacamoleConnectionForm, GuacamoleConnectionGroupEditForm, GuacamoleConnectionGroupForm
from .helpers import is_schedule_installed, support_periodic_tasks
from .models import AgendamentoLabFisico, GuacamoleConnection, GuacamoleConnectionGroup, GuacamoleServer, SolicitacaoLabFisico
from .perms import is_group_admin, pode_gerenciar_laboratorio_guacamole, pode_gerenciar_solicitacao_labfisico


class GuacamoleServerAdmin(ModelAdminPlus):
    list_display = ('name', 'uri', 'active', 'priority', 'get_auto_sync')
    ordering = ('-active', 'priority')

    def has_add_permission(self, request):
        has_permission = super().has_add_permission(request)
        if has_permission:
            return pode_gerenciar_laboratorio_guacamole(request.user)
        return has_permission

    def get_auto_sync(self, obj):
        if support_periodic_tasks() and is_schedule_installed():
            result = '<span class="status status-success">Instalada</span>'
        else:
            result = '<span class="status status-error">Não instalada</span>'
        return mark_safe(result)

    #
    get_auto_sync.short_description = 'Status Sincronização Automática'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request)
        items.append({'label': 'Carregar Agendador de Taferas', 'url': 'load_tasks'})
        return items

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('load_tasks/', self.load_schedule_tasks),
        ]
        return my_urls + urls

    def load_schedule_tasks(self, request):
        url = reverse(f'admin:{GuacamoleServer._meta.app_label}_{GuacamoleServer._meta.model_name}_changelist')
        try:
            from .tasks import load_tasks_schedule

            load_tasks_schedule()
            return httprr(url, 'Agendador de taferas carregado com sucesso')
        except Exception as e:
            return httprr(url, str(e), tag='error')


admin.site.register(GuacamoleServer, GuacamoleServerAdmin)


class CampusListFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'uo'

    def lookups(self, request, model_admin):
        lista_uos = []
        queryset = UnidadeOrganizacional.locals.all()
        for uo in queryset:
            lista_uos.append((str(uo.id), uo.sigla))
        return sorted(lista_uos, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        return queryset.filter()


class GuacamoleConnectionGroupAdmin(ModelAdminPlus):
    list_display = ('name', 'connection_group_id', 'ldap_group_name', 'campus', 'get_qtde_maquinas', 'get_options')
    search_fields = ('name', 'ldap_group_name')
    list_filter = (CampusListFilter, PassThroughFilter)
    add_form = GuacamoleConnectionGroupForm
    form = GuacamoleConnectionGroupEditForm
    list_display_icons = True
    actions = ['sincronizar_ldap']

    #
    def sincronizar_ldap(self, request, queryset):
        #
        for object in queryset.all():
            if not object.is_sync_ldap():
                object.sync_ldap()

    def get_qtde_maquinas(self, obj):
        return obj.connections_count()

    #
    get_qtde_maquinas.short_description = 'Qtde Clientes'

    #
    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        return queryset.my_guacamole_connection_groups(request.user)

    def get_form(self, request, *args, **kwargs):
        form = super().get_form(request, *args, **kwargs)
        return form

    #
    def get_options(self, obj):
        diario = self.request.GET.get('pt', None)
        texto = '<ul class="action-bar">'
        if self.request.user.has_perm('labfisico.add_guacamoleconnection'):
            texto = texto + '<li><a class="btn success" href="{}">Adicionar Cliente</a></li>'.format(
                reverse('labfisico:adicionar_cliente_guacamole', kwargs={'pk': obj.pk})
            )
        #
        if obj.pode_solicitar(self.request.user):
            solicitar_url = reverse('labfisico:solicitar_agendamento', kwargs={'pk': obj.pk})
            if diario:
                solicitar_url += f'?diario={diario}'
            #
            texto += f'<li><a class="btn" href="{solicitar_url}"> Solicitar Agendamento</a></li>'
            texto = texto + '<li><a class="btn danger" href="{}">Encerra sessões</a></li>'.format(
                reverse('labfisico:guacamole_connection_group_kill_sessions', kwargs={'pk': obj.pk})
            )
        #
        texto = texto + '</ul>'
        return mark_safe(texto)

    get_options.short_description = 'Ações'


admin.site.register(GuacamoleConnectionGroup, GuacamoleConnectionGroupAdmin)


class GuacamoleConnectionAdmin(ModelAdminPlus):
    list_display = ('connection_name', 'connection_id', 'connection_group', 'get_options')
    search_fields = ('connection_name', 'connection_group__name')
    list_filter = ('connection_group__name',)
    form = GuacamoleConnectionForm
    list_display_icons = True
    #
    add_form_template = 'rdp_connection_form.html'
    change_form_template = 'rdp_connection_form.html'
    #
    fieldsets = GuacamoleConnectionForm.fieldsets

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        if not is_group_admin(request.user):
            try:
                meu_campus = request.user.get_vinculo().setor.uo
                return queryset.filter(connection_group__campus=meu_campus)
            except Exception:
                return queryset.none()
        else:
            return queryset

    def get_options(self, obj):
        texto = '<ul class="action-bar">'
        has_permission = self.request.user.has_perm('labfisico.add_guacamoleconnection')
        if has_permission and pode_gerenciar_laboratorio_guacamole(self.request.user, obj):
            texto = texto + '<li><a class="btn success" href="{}">Adicionar Cliente</a></li>'.format(
                reverse('labfisico:adicionar_cliente_guacamole', kwargs={'pk': obj.connection_group.pk})
            )
        #
        texto = texto + '</ul>'
        return mark_safe(texto)

    get_options.short_description = 'Opções'


admin.site.register(GuacamoleConnection, GuacamoleConnectionAdmin)


class SolicitacaoLabFisicoAdmin(ModelAdminPlus):
    list_display = (
        'laboratorio',
        'solicitante',
        'get_periodo',
        'get_recorrencias',
        'get_status',
    )
    list_filter = (
        CustomTabListFilter,
        'status',
        ('data_inicio', DateRangeListFilter),
        ('data_fim', DateRangeListFilter),
    )
    exclude = ('status', 'data_avaliacao', 'observacao_avaliador', 'justificativa_cancelamento', 'data_cancelamento', 'cancelado_por')
    search_fields = ('laboratorio__name', 'solicitante__vinculo__pessoa__pessoafisica__nome')
    date_hierarchy = 'data_inicio'
    ordering = ('-data_inicio', '-hora_inicio')
    #
    list_display_icons = True
    #
    export_to_xls = True
    show_count_on_tabs = True
    #
    readonly_fields = [
        'laboratorio',
    ]

    actions = ['sincronizar_agendamentos']

    def sincronizar_agendamentos(self, request, queryset):
        #
        for object in queryset.filter(status=SolicitacaoAgendamentoStatus.STATUS_DEFERIDA):
            object.finalizar()
            object.save()
        #

    def add_view(self, request):
        app_label = GuacamoleConnectionGroup._meta.app_label
        model_name = GuacamoleConnectionGroup._meta.model_name
        url = reverse(f'admin:{app_label}_{model_name}_changelist')
        return httprr(url)

    def has_add_permission(self, request):
        has_permission = super().has_add_permission(request)
        return has_permission

    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj=obj)
        return has_permission and pode_gerenciar_solicitacao_labfisico(request.user, obj)

    # TODO: Não achei o metodo pode editar em Solicitacao LabFísico acredito que ngm ta podendo editar o objeto
    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj=obj)
        has_permission = has_permission and obj.pode_editar(user=request.user) if obj else has_permission
        return has_permission

    def get_tabs(self, request):
        tabs = []
        tabs = ['tab_minhas_solicitacoes', 'tab_solicitacoes_a_avaliar']
        tabs.append('tab_minhas_solicitacoes_futuras')
        return tabs

    def tab_minhas_solicitacoes_futuras(self, request, queryset):
        hoje = get_datetime_now()
        agora = hoje.time()
        reservas_derefidas = queryset.filter(solicitante=request.user)
        reservas_derefidas_hoje = reservas_derefidas.filter(data_inicio=hoje.date(), hora_inicio__gt=agora)
        reservas_derefidas_futuras = reservas_derefidas.filter(data_inicio__gt=hoje.date())
        return reservas_derefidas_hoje | reservas_derefidas_futuras

    tab_minhas_solicitacoes_futuras.short_description = 'Minhas Solicitações Futuras'

    def tab_minhas_solicitacoes(self, request, queryset):
        return queryset.filter(solicitante=request.user)

    tab_minhas_solicitacoes.short_description = 'Minhas Solicitações'

    def tab_solicitacoes_a_avaliar(self, request, queryset):
        return queryset.filter(status=SolicitacaoAgendamentoStatus.STATUS_ESPERANDO)

    tab_solicitacoes_a_avaliar.short_description = 'Solicitações a Avaliar'

    def get_periodo(self, obj):
        return obj.get_periodo()

    get_periodo.short_description = 'Período'

    def get_recorrencias(self, obj):
        return obj.get_recorrencias()

    get_recorrencias.short_description = 'Recorrência'

    def get_status(self, obj):
        return obj.get_formated_status()

    get_status.short_description = 'Status'


admin.site.register(SolicitacaoLabFisico, SolicitacaoLabFisicoAdmin)


class AgendamentoLabFisicoAdmin(ModelAdminPlus):
    list_display = ('laboratorio', 'get_ocorrencias', 'solicitante', 'get_status', 'get_options')
    search_fields = ('laboratorio__name', 'solicitacao__solicitante__vinculo__pessoa__pessoafisica__nome')

    readonly_fields = ['status', 'solicitacao', 'laboratorio']

    list_filter = ('status',)
    list_display_icons = True
    ordering = ('-data_hora_inicio',)

    #
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # has_change_permission = super().has_change_permission(request, obj=obj)
        # return has_change_permission and obj.inativo if obj else has_change_permission
        return False

    def has_delete_permission(self, request, obj=None):
        has_delete_permission = super().has_delete_permission(request, obj=obj)
        return has_delete_permission and (obj.inativo or obj.finalizado) if obj else has_delete_permission

    def get_options(self, obj):
        texto = '<ul class="action-bar">'
        if not obj.finalizado:
            if obj.pode_ativar():
                texto += '<li><a class="btn success popup" href="{}">Ativar</a></li>'.format(
                    reverse('labfisico:liberar_agendamento', kwargs={'pk': obj.pk})
                )
            #
            if obj.pode_inativar():
                texto += '<li><a class="btn danger popup" href="{}">Encerrar</a></li>'.format(
                    reverse('labfisico:encerrar_agendamento', kwargs={'pk': obj.pk})
                )
            #
        #
        texto = texto + '</ul>'
        return mark_safe(texto)

    #
    get_options.short_description = 'Ações'

    #
    def get_status(self, obj):
        if obj.ativo:
            retorno = f'<span class="status status-success">{obj.get_status_display()}</span>'
        elif obj.inativo:
            retorno = f'<span class="status status-alert">{obj.get_status_display()}</span>'
        else:
            retorno = f'<span class="status status-error">{obj.get_status_display()}</span>'

        return mark_safe(retorno)

    get_status.short_description = 'Status'

    def get_ocorrencias(self, obj):
        return obj.get_ocorrencias()

    get_ocorrencias.short_description = 'Ocorrência(s)'


admin.site.register(AgendamentoLabFisico, AgendamentoLabFisicoAdmin)
