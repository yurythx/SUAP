from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group, status
from erros.forms import ErroForm, RespostaFrequenteForm
from erros.models import Erro, RespostaFrequente
from djtools.utils import get_apps_suap, get_app_suap_display
from django.template.defaultfilters import truncatewords


class ModuloAfetadoListFilter(SimpleListFilter):
    title = 'Módulo Afetado'
    parameter_name = 'modulo_afetado'

    def lookups(self, request, model_admin):
        return [(c.label, c.verbose_name) for c in get_apps_suap()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(modulo_afetado=self.value())
        else:
            return queryset


class SouInteressadoErroFilter(SimpleListFilter):
    title = 'Sou Interessado'
    parameter_name = 'sou_interessado'

    def lookups(self, request, model_admin):
        return [('sim', 'Sim'), ('nao', 'Não')]

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(interessadoerro__vinculo=request.user.get_vinculo(), interessadoerro__ativo=True)
        else:
            return queryset


class AtribuidoAMimErroListFilter(SimpleListFilter):
    title = 'Atribuído a Mim'
    parameter_name = 'atribuido_a_mim'

    def lookups(self, request, model_admin):
        return [('sim', 'Sim'), ('nao', 'Não')]

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(atendente_atual=request.user.get_vinculo())
        else:
            return queryset


class PendenteAtribuicaoErroListFilter(SimpleListFilter):
    title = 'Pendente de Atribuição'
    parameter_name = 'pendente_atribuicao'

    def lookups(self, request, model_admin):
        return [('sim', 'Sim'), ('nao', 'Não')]

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(atendente_atual__isnull=True)
        else:
            return queryset


class PossuiURLGitlabFilter(SimpleListFilter):
    title = 'Possui URL do GitLab'
    parameter_name = 'possui_url_gitlab'

    def lookups(self, request, model_admin):
        return [('sim', 'Sim'), ('nao', 'Não')]

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.exclude(gitlab_issue_url__isnull=True).exclude(gitlab_issue_url='')
        if self.value() == 'nao':
            return queryset.filter(gitlab_issue_url__isnull=True) | queryset.filter(gitlab_issue_url='')
        return queryset


class ErroAdmin(ModelAdminPlus):
    list_display = ()
    list_filter = (
        CustomTabListFilter,
        ModuloAfetadoListFilter,
        SouInteressadoErroFilter,
        PossuiURLGitlabFilter,
        'atendente_atual',
    )
    search_fields = ('descricao', 'url', 'view', 'informante__pessoa__nome')
    list_display_icons = True
    show_count_on_tabs = True
    ordering = ('-qtd_vinculos_afetados', 'data_criacao')
    form = ErroForm
    date_hierarchy = 'data_criacao'

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if in_group(request.user, 'Recebedor de Demandas'):
            list_display += (
                'get_modulo_afetado',
                'get_urls_vinculadas',
                'get_atendimento',
                'get_descricao_resumida',
                'get_data_criacao',
                'informante',
                'qtd_vinculos_afetados',
            )
        else:
            list_display += (
                'get_modulo_afetado',
                'get_urls_vinculadas',
                'get_descricao_resumida',
                'get_data_criacao',
                'informante',
                'get_situacao_display',
            )
        return list_display

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if in_group(request.user, 'Analista'):
            list_filter += (AtribuidoAMimErroListFilter,)
        if in_group(request.user, 'Recebedor de Demandas'):
            list_filter += (PendenteAtribuicaoErroListFilter,)
        return list_filter

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if in_group(request.user, 'Analista'):
            return qs
        else:
            return (
                qs.exclude(situacao=Erro.SITUACAO_CANCELADO)
                | qs.filter(situacao=Erro.SITUACAO_CANCELADO, interessadoerro__vinculo=request.user.get_vinculo())
            ).distinct()

    def get_tabs(self, request):
        return ['tab_abertos', 'tab_em_andamento', 'tab_em_correcao', 'tab_aguardando_feedback', 'tab_resolvidos', 'tab_cancelados', 'tab_any_data']

    def tab_abertos(self, request, queryset):
        return queryset.filter(situacao__in=[Erro.SITUACAO_ABERTO, Erro.SITUACAO_REABERTO])

    tab_abertos.short_description = 'Reportados'

    def tab_em_andamento(self, request, queryset):
        return queryset.filter(situacao=Erro.SITUACAO_EM_ANALISE)

    tab_em_andamento.short_description = 'Em análise'

    def tab_em_correcao(self, request, queryset):
        return queryset.filter(situacao=Erro.SITUACAO_EM_CORRECAO)

    tab_em_correcao.short_description = 'Em correção'

    def tab_resolvidos(self, request, queryset):
        return queryset.filter(situacao=Erro.SITUACAO_RESOLVIDO)

    tab_resolvidos.short_description = 'Resolvidos'

    def tab_aguardando_feedback(self, request, queryset):
        return queryset.filter(situacao=Erro.SITUACAO_AGUARDANDO_FEEDBACK)

    tab_aguardando_feedback.short_description = 'Aguardando feedback'

    def tab_cancelados(self, request, queryset):
        return queryset.filter(situacao=Erro.SITUACAO_CANCELADO)

    tab_cancelados.short_description = 'Cancelados'

    def get_atendimento(self, obj):
        retorno = status(obj.get_situacao_display())
        if obj.atendente_atual:
            retorno += f'<hr><div class="person smallest text-nowrap"><div class="photo-circle smallest"><img src="{obj.atendente_atual.get_foto_75x100_url}" alt="{obj.atendente_atual.pessoa.pessoafisica.nome_usual}"></div><dl><dt class="visually-hidden">Nome</dt><dd class="pt-1">{obj.atendente_atual.pessoa.pessoafisica.nome_usual}</dd></dl></div>'
        return mark_safe(retorno)

    get_atendimento.short_description = 'Atendimento'

    def get_modulo_afetado(self, obj):
        try:
            app = get_app_suap_display(obj.modulo_afetado)
            retorno = f'<h3>{obj.pk} | {app}</h3><dl class="definition-list">'
            if in_group(self.request.user, 'Analista'):
                retorno += f'<dt>View</dt><dd>{obj.view}</dd>'
            retorno += '</dl>'
            return mark_safe(retorno)
        except Exception:
            return '-'

    get_modulo_afetado.short_description = 'Erro'

    def get_urls_vinculadas(self, obj):
        try:
            url = obj.url
            url_trimmed = (url[:100] + '...') if len(url) > 103 else url
            retorno = f'<dl class="definition-list"><dt>URL</dt><dd><a href="{url_trimmed}">{url_trimmed}</a></dd>'
            if obj.gitlab_issue_url:
                retorno += f'<dt>Gitlab</dt><dd><a href="{obj.gitlab_issue_url}">{obj.gitlab_issue_url}</a></dd>'
            if obj.url_sentry:
                retorno += f'<dt>Sentry</dt><dd><a href="{obj.url_sentry}">{obj.url_sentry}</a></dd>'
            retorno += '</dl>'
            return mark_safe(retorno)
        except Exception:
            return '-'

    get_urls_vinculadas.short_description = 'URLs vinculadas'

    def get_descricao_resumida(self, obj):
        return truncatewords(obj.descricao, 25)

    get_descricao_resumida.short_description = 'Descrição'

    def get_data_criacao(self, obj):
        data_criacao = obj.data_criacao
        if obj.situacao != Erro.SITUACAO_RESOLVIDO and obj.situacao != Erro.SITUACAO_CANCELADO:
            quinze_dias_atras = datetime.now() - relativedelta(days=15)

            if data_criacao < quinze_dias_atras:
                return mark_safe(f'<span class="false">{format(data_criacao.strftime("%d/%m/%Y"))}</span>')
            else:
                return data_criacao.strftime('%d/%m/%Y')
        else:
            return data_criacao.strftime('%d/%m/%Y')

    get_data_criacao.short_description = 'Reportado em'

    def get_situacao_display(self, obj):
        return status(obj.get_situacao_display())

    get_situacao_display.short_description = 'Situação'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(Erro, ErroAdmin)


class RespostaFrequenteAdmin(ModelAdminPlus):
    form = RespostaFrequenteForm
    search_fields = ('texto',)
    list_filter = ('atendente',)
    list_display = ('atendente', 'texto')
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.has_group_cached('centralservicos Administrador')):
            return qs.filter(atendente__id=request.user.id)
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.atendente = request.user
        super().save_model(request, obj, form, change)


admin.site.register(RespostaFrequente, RespostaFrequenteAdmin)
