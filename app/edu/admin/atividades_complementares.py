from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import httprr
from edu.models import AtividadeComplementar, ConfiguracaoAtividadeAprofundamento, ConfiguracaoAtividadeComplementar
from edu.models.atividades_complementares import AtividadeAprofundamento


class ConfiguracaoAtividadeAprofundamentoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    list_filter = (CustomTabListFilter,)
    list_display_icons = True
    search_fields = ('descricao',)
    ordering = ('-id',)

    def get_tabs(self, request):
        return ['tab_vinculadas', 'tab_nao_vinculadas']

    def tab_vinculadas(self, request, queryset):
        return queryset.filter(matriz__isnull=False).distinct()

    tab_vinculadas.short_description = 'Vinculadas'

    def tab_nao_vinculadas(self, request, queryset):
        return queryset.filter(matriz__isnull=True).distinct()

    tab_nao_vinculadas.short_description = 'Não Vinculadas'

    def response_add(self, request, obj):
        return httprr(f'/edu/configuracaoatividadeaprofundamento/{obj.pk}/', 'Configuração cadastrada com sucesso. Adicione os tipos de atividades.')


admin.site.register(ConfiguracaoAtividadeAprofundamento, ConfiguracaoAtividadeAprofundamentoAdmin)


class AtividadeAprofundamentoAdmin(ModelAdminPlus):
    list_display = ('get_ano_periodo', 'get_nome_aluno', 'tipo', 'descricao', 'get_curso', 'deferida')
    list_filter = ('tipo', 'deferida', 'aluno__curso_campus', 'aluno__matriz')
    search_fields = ('aluno__pessoa_fisica__nome_registro', 'aluno__matricula', 'aluno__pessoa_fisica__nome_social', 'descricao')
    list_display_icons = True

    def get_nome_aluno(self, obj):
        return mark_safe(f'(<a href="/edu/aluno/{obj.aluno.matricula}/">{obj.aluno.matricula}</a>) {obj.aluno.get_nome()}')

    get_nome_aluno.short_description = 'Aluno'
    get_nome_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'

    def get_ano_periodo(self, obj):
        return mark_safe(f'{obj.ano_letivo.ano}.{obj.periodo_letivo}')

    get_ano_periodo.short_description = 'Ano/Período'

    def get_curso(self, obj):
        return obj.aluno.curso_campus

    get_curso.short_description = 'Curso'

    def get_tabs(self, request):
        return ['tab_aguardando_deferimento']

    def get_queryset(self, request):
        return super().get_queryset(request, AtividadeAprofundamento.locals)

    def tab_aguardando_deferimento(self, request, queryset):
        return queryset.filter(deferida__isnull=True)

    tab_aguardando_deferimento.short_description = 'Aguardando Avaliação'

    def get_action_bar(self, request):
        return []


admin.site.register(AtividadeAprofundamento, AtividadeAprofundamentoAdmin)


class AtividadeComplementarAdmin(ModelAdminPlus):
    list_display = ('get_ano_periodo', 'get_nome_aluno', 'tipo', 'descricao', 'get_curso', 'deferida')
    list_filter = ('tipo', 'deferida', 'aluno__curso_campus', 'aluno__matriz')
    search_fields = ('aluno__pessoa_fisica__nome_registro', 'aluno__matricula', 'aluno__pessoa_fisica__nome_social', 'descricao')
    list_display_icons = True

    def get_nome_aluno(self, obj):
        return mark_safe(f'(<a href="/edu/aluno/{obj.aluno.matricula}/">{obj.aluno.matricula}</a>) {obj.aluno.get_nome()}')

    get_nome_aluno.short_description = 'Aluno'
    get_nome_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'

    def get_ano_periodo(self, obj):
        return mark_safe(f'{obj.ano_letivo.ano}.{obj.periodo_letivo}')

    get_ano_periodo.short_description = 'Ano/Período'

    def get_curso(self, obj):
        return obj.aluno.curso_campus

    get_curso.short_description = 'Curso'

    def get_tabs(self, request):
        return ['tab_aguardando_deferimento']

    def get_queryset(self, request):
        return super().get_queryset(request, AtividadeComplementar.locals)

    def tab_aguardando_deferimento(self, request, queryset):
        return queryset.filter(deferida__isnull=True)

    tab_aguardando_deferimento.short_description = 'Aguardando Avaliação'

    def get_action_bar(self, request):
        return []


admin.site.register(AtividadeComplementar, AtividadeComplementarAdmin)


class ConfiguracaoAtividadeComplementarAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    list_filter = (CustomTabListFilter,)
    list_display_icons = True
    search_fields = ('descricao',)
    ordering = ('-id',)

    def get_tabs(self, request):
        return ['tab_vinculadas', 'tab_nao_vinculadas']

    def tab_vinculadas(self, request, queryset):
        return queryset.filter(matriz__isnull=False).distinct()

    tab_vinculadas.short_description = 'Vinculadas'

    def tab_nao_vinculadas(self, request, queryset):
        return queryset.filter(matriz__isnull=True).distinct()

    tab_nao_vinculadas.short_description = 'Não Vinculadas'

    def response_add(self, request, obj):
        return httprr(
            f'/edu/configuracaoatividadecomplementar/{obj.pk}/',
            'Configuração cadastrada com sucesso. Adicione os tipos de atividades complementares.',
        )


admin.site.register(ConfiguracaoAtividadeComplementar, ConfiguracaoAtividadeComplementarAdmin)
