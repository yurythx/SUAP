from django.contrib import admin, messages
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import status
from edu.models import (
    AtividadeCurricularExtensao,
    AtividadePraticaProfissional,
    CursoCampus,
    ModalidadePraticaProfissional,
    TipoAtividadeCurricularExtensaoExtra,
)


class AtividadeCurricularExtensaoAdmin(ModelAdminPlus):
    list_display = 'get_aluno', 'get_ano_letivo', 'get_periodo_letivo', 'tipo_referencia', 'descricao', 'concluida', 'aprovada'
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'matricula_periodo__ano_letivo',
        'matricula_periodo__periodo_letivo',
        'tipo_referencia',
        'descricao',
        'concluida',
        'aprovada',
        'matricula_periodo__aluno__curso_campus',
    )
    search_fields = ('matricula_periodo__aluno__matricula', 'matricula_periodo__aluno__pessoa_fisica__nome')
    list_per_page = 15
    show_count_on_tabs = True
    actions = 'aprovar', 'rejeitar', 'cancelar_avaliacao'

    def get_aluno(self, obj):
        return obj.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_ano_letivo(self, obj):
        return obj.matricula_periodo.ano_letivo

    get_ano_letivo.short_description = 'Ano Letivo'

    def get_periodo_letivo(self, obj):
        return obj.matricula_periodo.periodo_letivo

    get_periodo_letivo.short_description = 'Período Letivo'

    def get_curso(self, obj):
        return obj.matricula_periodo.aluno.curso_campus

    get_aluno.short_description = 'Curso'

    def get_tabs(self, request):
        return ['tab_aguardando_avaliacao', 'tab_aprovadas', 'tab_rejeitadas']

    def tab_aprovadas(self, request, queryset):
        return queryset.filter(aprovada=True)

    tab_aprovadas.short_description = 'Deferidas'

    def tab_rejeitadas(self, request, queryset):
        return queryset.filter(aprovada=False)

    tab_rejeitadas.short_description = 'Indeferidas'

    def tab_aguardando_avaliacao(self, request, queryset):
        return queryset.filter(aprovada__isnull=True, concluida=True)

    tab_aguardando_avaliacao.short_description = 'Aguardando Avaliação'

    def get_actions(self, request):
        tab = request.GET.get('tab')
        actions = super().get_actions(request)
        if tab == 'tab_aguardando_avaliacao':
            actions.pop('cancelar_avaliacao')
        elif tab == 'tab_aprovadas' or tab == 'tab_rejeitadas':
            actions.pop('aprovar')
            actions.pop('rejeitar')
        else:
            actions.clear()
        return actions

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        cursos_coordenados = CursoCampus.objects.filter(coordenador=request.user.get_vinculo()).values_list('pk', flat=True)
        return queryset.filter(matricula_periodo__aluno__curso_campus__in=cursos_coordenados).exclude(
            matricula_periodo__aluno__matriz__requer_vinculacao_extensao_diarios=True
        )

    def aprovar(self, request, queryset):
        queryset.update(aprovada=True)
        messages.success(request, 'Atividade(s) deferida(s) com sucesso.')

    aprovar.short_description = 'Deferir atividades selecionadas'

    def rejeitar(self, request, queryset):
        queryset.update(aprovada=False)
        messages.success(request, 'Atividade(s) indeferida(s) com sucesso.')

    rejeitar.short_description = 'Indeferir atividades selecionadas'

    def cancelar_avaliacao(self, request, queryset):
        queryset.update(aprovada=None)
        messages.success(request, 'Cancelamento realizado com sucesso.')

    cancelar_avaliacao.short_description = 'Cancelar avaliação das atividades selecionadas'


admin.site.register(AtividadeCurricularExtensao, AtividadeCurricularExtensaoAdmin)


class TipoAtividadeCurricularExtensaoExtraAdmin(ModelAdminPlus):
    list_display = 'descricao', 'ativo'
    list_display_icons = True
    list_filter = ('ativo',)
    search_fields = ('descricao',)


admin.site.register(TipoAtividadeCurricularExtensaoExtra, TipoAtividadeCurricularExtensaoExtraAdmin)


class AtividadePraticaProfissionalAdmin(ModelAdminPlus):
    list_display = 'get_aluno', 'modalidade_pratica_profissional', 'descricao', 'get_situacao', 'carga_horaria', 'nota', 'get_opcoes'
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'matricula_periodo__ano_letivo',
        'matricula_periodo__periodo_letivo',
        'situacao',
        'modalidade_pratica_profissional',
        'matricula_periodo__aluno__curso_campus',
    )
    search_fields = ('matricula_periodo__aluno__matricula', 'descricao')

    def get_aluno(self, obj):
        return obj.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_situacao(self, obj):
        return status(obj.get_situacao_display())

    get_situacao.short_description = 'Situação'

    def get_tabs(self, request):
        return [
            'tab_aguardando_minha_avaliacao',
            'tab_aguardando_minha_reavaliacao',
            'tab_aguardando_minha_conclusao',
            'tab_sem_nota',
            'tab_minha_coordenacao',
            'tab_any_data',
        ]

    def tab_aguardando_minha_avaliacao(self, request, queryset):
        return AtividadePraticaProfissional.get_pendentes_avaliacao_coordenador(request.user, queryset)

    tab_aguardando_minha_avaliacao.short_description = 'Aguardando avaliação'

    def tab_aguardando_minha_reavaliacao(self, request, queryset):
        return AtividadePraticaProfissional.get_pendentes_reavaliacao_coordenador(request.user, queryset)

    tab_aguardando_minha_reavaliacao.short_description = 'Aguardando reavaliação'

    def tab_aguardando_minha_conclusao(self, request, queryset):
        return AtividadePraticaProfissional.get_pendentes_conclusao_coordenador(request.user, queryset)

    tab_aguardando_minha_conclusao.short_description = 'Aguardando conclusão'

    def tab_sem_nota(self, request, queryset):
        return AtividadePraticaProfissional.get_pendentes_nota_coordenador(request.user, queryset)

    tab_sem_nota.short_description = 'Aguardando lançamento de nota'

    def tab_minha_coordenacao(self, request, queryset):
        return AtividadePraticaProfissional.get_atividades_coordenador(request.user, queryset)

    tab_minha_coordenacao.short_description = 'Sob minha coordenação'

    def get_opcoes(self, obj):
        return obj.get_acoes(self.request.user, from_admin=True)

    get_opcoes.short_description = 'Opções'

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(AtividadePraticaProfissional, AtividadePraticaProfissionalAdmin)


class ModalidadePraticaProfissionalAdmin(ModelAdminPlus):
    list_display = (
        'nome',
        'ativo',
        'descricao',
    )
    ordering = (
        '-ativo',
        'nome',
    )
    search_fields = (
        'nome',
        'descricao',
    )
    list_filter = ('ativo',)
    list_display_icons = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(ModalidadePraticaProfissional, ModalidadePraticaProfissionalAdmin)
