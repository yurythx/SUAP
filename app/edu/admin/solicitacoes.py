from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import SolicitacaoProrrogacaoEtapaForm, SolicitacaoRelancamentoEtapaForm
from edu.models import SolicitacaoProrrogacaoEtapa, SolicitacaoRelancamentoEtapa, SolicitacaoUsuario
from edu.utils import SolicitacaoFilter


class SolicitacaoUsuarioAdmin(ModelAdminPlus):
    list_display = ('id', 'get_solicitante', 'data_solicitacao', 'get_descricao', 'sub_instance_title', 'get_acoes')
    list_display_icons = True
    list_filter = (CustomTabListFilter, 'solicitante', 'avaliador', SolicitacaoFilter)
    search_fields = ('id', 'solicitante__first_name', 'solicitante__username', 'avaliador__first_name', 'avaliador__username')
    ordering = ('-data_avaliacao',)
    form = SolicitacaoRelancamentoEtapaForm
    export_to_xls = True
    show_actions = False

    actions = ('deferir', 'indeferir')

    def get_actions(self, request):
        actions = super().get_actions(request)
        if self.show_actions and request.user.has_perm('edu.change_solicitacaousuario'):
            return actions
        else:
            for key in list(actions.keys()):
                del actions[key]
            return actions

    def deferir(self, request, queryset):
        for solicitacao in queryset.filter(data_avaliacao__isnull=True):
            solicitacao.sub_instance().atender(request.user)
        messages.success(request, 'Solicitações deferidas com sucesso.')

    deferir.short_description = 'Deferir'

    def indeferir(self, request, queryset):
        ids = [str(x) for x in queryset.filter(data_avaliacao__isnull=True).values_list('id', flat=True)]
        if ids:
            url = '/edu/rejeitar_solicitacao/{}/'.format('_'.join(ids))
            return HttpResponseRedirect(url)

    indeferir.short_description = 'Indeferir'

    def get_solicitante(self, obj):
        return mark_safe(obj.solicitante)

    get_solicitante.short_description = 'Solicitante'

    def get_action_bar(self, request):
        self.show_actions = request.GET.get('tab', None) == 'tab_pendentes'
        items = super().get_action_bar(request, True)
        return items

    def get_diretoria(self, obj):
        return mark_safe(obj.get_diretoria())

    get_diretoria.short_description = 'Diretoria'

    def get_acoes(self, obj):
        lista = []
        if obj.data_avaliacao:
            if obj.atendida:
                lista.append(
                    '<span class="status status-success">Deferida por {} em {}</span>'.format(obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y'))
                )
            else:
                lista.append(
                    '<span class="status status-error">Indeferida por {} em {}</span>'.format(obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y'))
                )
        else:
            lista.append('<span class="status status-pendente">Pendente</span>')
        return mark_safe(' '.join(lista))

    get_acoes.short_description = 'Status'

    def get_descricao(self, obj):
        filho = obj.sub_instance()
        if isinstance(filho, SolicitacaoRelancamentoEtapa) and filho.precisa_prorrogar_posse():
            return mark_safe(
                f'<p>{obj.descricao}</p><span class="status status-error">Data de posse da etapa já foi ultrapassada, será preciso definir uma nova data limite para a posse.</span>'
            )
        else:
            return obj.descricao

    get_descricao.short_description = 'Descrição'

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Solicitante', 'Data da Solicitação', 'Descrição', 'Campus', 'Status', 'Avaliador']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            if obj.data_avaliacao:
                if obj.atendida:
                    atendimento = 'Deferida'
                else:
                    atendimento = 'Indeferida'
            else:
                atendimento = 'Não avaliada'
            row = [idx + 1, obj.solicitante, obj.data_solicitacao, obj.descricao, obj.uo, atendimento, obj.avaliador]
            rows.append(row)
        return rows

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_avaliados']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes'

    def tab_avaliados(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=False)

    tab_avaliados.short_description = 'Avaliados'

    def get_queryset(self, request, manager=None):
        if not manager:
            manager = SolicitacaoUsuario.locals.exclude(solicitacaoacompanhamento__isnull=False)
        return super().get_queryset(request, manager).filter(solicitacaoprorrogacaoetapa__isnull=False) | super().get_queryset(
            request, manager
        ).filter(solicitacaorelancamentoetapa__isnull=False)


admin.site.register(SolicitacaoUsuario, SolicitacaoUsuarioAdmin)


class SolicitacaoRelancamentoEtapaAdmin(ModelAdminPlus):
    list_display = ('id', 'get_solicitante', 'data_solicitacao', 'get_descricao', 'get_diretoria', 'motivo', 'get_acoes')
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'professor_diario__diario__ano_letivo',
        'professor_diario__diario__periodo_letivo',
        'professor_diario__diario__turma__curso_campus__diretoria',
    )
    search_fields = ('id', 'solicitante__first_name', 'solicitante__username', 'avaliador__first_name', 'avaliador__username')
    ordering = ('-data_avaliacao',)
    form = SolicitacaoRelancamentoEtapaForm
    export_to_xls = True

    actions = ('deferir', 'indeferir')

    def get_solicitante(self, obj):
        return mark_safe(obj.solicitante)

    get_solicitante.short_description = 'Solicitante'

    def get_action_bar(self, request):
        items = super().get_action_bar(request, True)
        return items

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab', None) == 'tab_pendentes':
            return actions
        else:
            for key in list(actions.keys()):
                del actions[key]
            return actions

    def get_descricao(self, obj):
        filho = obj.sub_instance()
        if isinstance(filho, SolicitacaoRelancamentoEtapa) and filho.precisa_prorrogar_posse():
            descricao = obj.descricao
            ano_semestre = f'{obj.professor_diario.diario.ano_letivo}/{obj.professor_diario.diario.periodo_letivo}'
            descricao = f'{descricao} - {ano_semestre}'
            return mark_safe(
                f'<p>{descricao}</p><span class="status status-error">Data de posse da etapa já foi ultrapassada, será preciso definir uma nova data limite para a posse.</span>'
            )
        else:
            return obj.descricao

    get_descricao.short_description = 'Descrição'

    def get_diretoria(self, obj):
        return mark_safe(obj.get_diretoria())

    get_diretoria.short_description = 'Diretoria'

    def deferir(self, request, queryset):
        for solicitacao in queryset.filter(data_avaliacao__isnull=True):
            solicitacao.atender(request.user)
        messages.success(request, 'Solicitações deferidas com sucesso.')

    deferir.short_description = 'Deferir'

    def indeferir(self, request, queryset):
        ids = [str(x) for x in queryset.filter(data_avaliacao__isnull=True).values_list('id', flat=True)]
        if ids:
            url = '/edu/rejeitar_solicitacao/{}/'.format('_'.join(ids))
            return HttpResponseRedirect(url)

    indeferir.short_description = 'Indeferir'

    def get_acoes(self, obj):
        lista = []
        if obj.data_avaliacao:
            if obj.atendida:
                lista.append(
                    '<span class="status status-success">Deferida por {} em {}</span>'.format(obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y'))
                )
            else:
                lista.append(
                    '<span class="status status-error">Indeferida por {} em {}</span>'.format(obj.avaliador, obj.data_avaliacao.strftime('%d/%m/%y'))
                )
        else:
            lista.append('<span class="status status-pendente">Pendente</span>')
        return mark_safe(' '.join(lista))

    get_acoes.short_description = 'Situação'

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Solicitante', 'Data da Solicitação', 'Descrição', 'Campus', 'Status', 'Avaliador']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            if obj.data_avaliacao:
                if obj.atendida:
                    atendimento = 'Deferida'
                else:
                    atendimento = 'Indeferida'
            else:
                atendimento = 'Não avaliada'
            row = [idx + 1, obj.solicitante, obj.data_solicitacao, obj.descricao, obj.uo, atendimento, obj.avaliador]
            rows.append(row)
        return rows

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_avaliados']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=True)

    tab_pendentes.short_description = 'Pendentes'

    def tab_avaliados(self, request, queryset):
        return queryset.filter(data_avaliacao__isnull=False)

    tab_avaliados.short_description = 'Avaliados'

    def get_queryset(self, request, manager=None):
        if not manager:
            manager = SolicitacaoRelancamentoEtapa.locals
        return super().get_queryset(request, manager)


admin.site.register(SolicitacaoRelancamentoEtapa, SolicitacaoRelancamentoEtapaAdmin)


class SolicitacaoProrrogacaoEtapaAdmin(SolicitacaoRelancamentoEtapaAdmin):
    list_filter = (
        CustomTabListFilter,
        'professor_diario__diario__ano_letivo',
        'professor_diario__diario__periodo_letivo',
        'professor_diario__diario__turma__curso_campus__diretoria',
    )
    form = SolicitacaoProrrogacaoEtapaForm

    def get_queryset(self, request):
        return super().get_queryset(request, SolicitacaoProrrogacaoEtapa.locals)


admin.site.register(SolicitacaoProrrogacaoEtapa, SolicitacaoProrrogacaoEtapaAdmin)
