from django.contrib import admin
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import SorteioAvaliadorRSCTae


@admin.register(SorteioAvaliadorRSCTae)
class SorteioAvaliadorRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'processo',
        'avaliador_sorteado',
        'avaliador_substituido',
        'get_motivo',
        'realizado_por_vinculo',
        'data_sorteio',
    )
    list_display_icons = True
    list_filter = ('motivo',)
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'avaliador_sorteado__pessoa__nome',
        'avaliador_substituido__pessoa__nome',
    )
    ordering = ('-data_sorteio',)
    readonly_fields = (
        'processo',
        'avaliador_sorteado',
        'avaliador_substituido',
        'motivo',
        'justificativa',
        'realizado_por_vinculo',
        'data_sorteio',
    )

    @admin.display(description='Motivo')
    def get_motivo(self, obj):
        if obj.motivo == SorteioAvaliadorRSCTae.MOTIVO_INICIAL:
            return format_html('<span class="status status-info">Sorteio inicial</span>')
        return format_html('<span class="status status-warning">{}</span>', obj.get_motivo_display())

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
