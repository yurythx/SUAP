from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import PDAEtapa


@admin.register(PDAEtapa)
class PDAEtapaAdmin(ModelAdminPlus):
    """Auditoria das etapas dispensadas (puladas) por PDA. Somente leitura."""

    list_display = (
        'pda',
        'etapa',
        'pulada_por',
        'data_pulada',
    )
    list_filter = ('etapa',)
    search_fields = (
        'pda__titulo',
        'etapa__titulo',
        'justificativa',
    )
    ordering = ('-data_pulada',)
    list_select_related = ('pda', 'etapa', 'pulada_por')
    readonly_fields = (
        'pda',
        'etapa',
        'justificativa',
        'pulada_por',
        'data_pulada',
        'ip',
        'user_agent',
    )

    fieldsets = (
        (
            _('Dispensa de etapa'),
            {'fields': ('pda', 'etapa', 'justificativa', 'pulada_por', 'data_pulada', 'ip', 'user_agent')},
        ),
    )

    def has_add_permission(self, request):
        return False
