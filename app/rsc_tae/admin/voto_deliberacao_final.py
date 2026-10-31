from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import VotoDeliberacaoFinalRSCTae


@admin.register(VotoDeliberacaoFinalRSCTae)
class VotoDeliberacaoFinalRSCTaeAdmin(ModelAdminPlus):
    list_display_icons = True

    list_display = (
        'processo',
        'deliberado_por_vinculo',
        'resultado',
        'pontuacao_final',
        'data_deliberacao',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'deliberado_por_vinculo__pessoa__nome',
    )
    list_filter = ('resultado', 'data_deliberacao')
    ordering = ('-data_deliberacao',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'processo__vinculo', 'deliberado_por_vinculo')
