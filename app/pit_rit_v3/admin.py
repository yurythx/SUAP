from datetime import datetime

from django.contrib import admin, messages

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from pit_rit_v3.models import Grupo, Subgrupo, Atividade, PlanoIndividualTrabalhoV3, Configuracao


class ConfiguracaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativa')
    ordering = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(Configuracao, ConfiguracaoAdmin)


class GrupoAdmin(ModelAdminPlus):
    list_display = ('nome',)
    ordering = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(Grupo, GrupoAdmin)


class SubgrupoAdmin(ModelAdminPlus):
    list_display = ('nome', 'grupo')
    ordering = ('nome',)
    search_fields = ('nome',)
    list_filter = ('grupo',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(Subgrupo, SubgrupoAdmin)


class AtividadeAdmin(ModelAdminPlus):
    list_display = (
        'configuracao',
        'nome',
        'subgrupo__grupo',
        'subgrupo',
        'observacao',
        'carga_horaria_unitaria',
        'carga_horaria_maxima',
        'fonte_dados',
    )
    ordering = (
        'configuracao',
        'nome',
    )
    search_fields = ('nome', 'observacao')
    list_filter = ('configuracao', 'subgrupo__grupo', 'subgrupo', 'fonte_dados')
    list_display_icons = True
    export_to_xls = True


admin.site.register(Atividade, AtividadeAdmin)


class PlanoIndividualTrabalhoV3Admin(ModelAdminPlus):
    search_fields = 'professor__vinculo__pessoa__nome', 'professor__vinculo__user__username'
    list_display = (
        'professor',
        'ano_letivo',
        'periodo_letivo',
        'avaliador',
        'aprovado',
        'avaliador_relatorio',
        'relatorio_aprovado',
        'responsavel_publicacao',
        'publicado',
    )
    list_filter = (
        CustomTabListFilter,
        'ano_letivo',
        'periodo_letivo',
        'aprovado',
        'relatorio_aprovado',
        'publicado',
        'professor__vinculo__setor',
    )
    list_display_icons = True
    show_count_on_tabs = True

    actions = ('publicar',)

    def publicar(self, request, queryset):
        queryset.update(publicado=True, data_publicacao=datetime.now())
        messages.success(request, 'Os planos selecionados foram publicados com sucesso.')

    publicar.short_description = 'Publicar'

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'publicar' in actions and request.GET.get('tab') != 'tab_aguardando_publicacao':
            del actions['publicar']
        return actions

    def get_queryset(self, request):
        queryset = super().get_queryset(request, PlanoIndividualTrabalhoV3.objects)
        return queryset

    def get_tabs(self, request):
        return [
            'tab_aguardando_avaliacao',
            'tab_aguardando_avaliacao_relatorio',
            'tab_aguardando_publicacao',
            'tab_publicados',
            'tab_minhas_avaliacoes',
        ]

    def tab_aguardando_avaliacao(self, request, queryset):
        return queryset.filter(aprovado__isnull=True, data_envio__isnull=False, avaliador__vinculos__user=request.user)

    tab_aguardando_avaliacao.short_description = 'Aguardando Avaliação do Plano'

    def tab_aguardando_avaliacao_relatorio(self, request, queryset):
        return queryset.filter(
            aprovado=True, relatorio_aprovado__isnull=True, data_envio_relatorio__isnull=False, avaliador_relatorio__vinculos__user=request.user
        )

    tab_aguardando_avaliacao_relatorio.short_description = 'Aguardando Avaliação do Relatório'

    def tab_aguardando_publicacao(self, request, queryset):
        return queryset.filter(aprovado=True, relatorio_aprovado=True, publicado__isnull=True, responsavel_publicacao__vinculos__user=request.user)

    tab_aguardando_publicacao.short_description = 'Aguardando Publicação do Relatório'

    def tab_publicados(self, request, queryset):
        return queryset.filter(publicado=True, responsavel_publicacao__vinculos__user=request.user)

    tab_publicados.short_description = 'Publicados'

    def tab_minhas_avaliacoes(self, request, queryset):
        qs = queryset.filter(aprovado__isnull=False, avaliador__vinculos__user=request.user) | queryset.filter(
            relatorio_aprovado__isnull=False, avaliador_relatorio__vinculos__user=request.user
        )
        return qs.distinct()

    tab_minhas_avaliacoes.short_description = 'Minhas avaliações'


admin.site.register(PlanoIndividualTrabalhoV3, PlanoIndividualTrabalhoV3Admin)
