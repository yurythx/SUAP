from datetime import datetime

from django.contrib import admin, messages

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from pit_rit_v2.forms import PlanoIndividualTrabalhoForm
from pit_rit_v2.models import AtividadeEnsino, AtividadeExtensao, AtividadeGestao, AtividadePesquisa, PlanoIndividualTrabalhoV2


class AtividadeEnsinoAdmin(ModelAdminPlus):
    list_display = 'descricao', 'subgrupo'
    list_filter = ('subgrupo',)
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(AtividadeEnsino, AtividadeEnsinoAdmin)


class OutrasAtividadesAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


for cls in (AtividadePesquisa, AtividadeExtensao, AtividadeGestao):
    admin.site.register(cls, OutrasAtividadesAdmin)


class PlanoIndividualTrabalhoV2Admin(ModelAdminPlus):
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
    form = PlanoIndividualTrabalhoForm
    show_count_on_tabs = True
    fieldsets = PlanoIndividualTrabalhoForm.fieldsets

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
        queryset = super().get_queryset(request, PlanoIndividualTrabalhoV2.objects)
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


admin.site.register(PlanoIndividualTrabalhoV2, PlanoIndividualTrabalhoV2Admin)
