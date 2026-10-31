from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import ApontamentoCorrecaoRSCTae


@admin.register(ApontamentoCorrecaoRSCTae)
class ApontamentoCorrecaoRSCTaeAdmin(ModelAdminPlus):
    list_display_icons = True

    list_display = (
        'processo',
        'area',
        'resolvido',
        'criado_por_vinculo',
        'data_criacao',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'descricao',
    )
    list_filter = (
        'area',
        'resolvido',
        'data_criacao',
    )
    ordering = ('-data_criacao',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'processo__vinculo', 'criado_por_vinculo')
