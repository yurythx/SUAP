from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import AlteracaoNivelRSCTae


@admin.register(AlteracaoNivelRSCTae)
class AlteracaoNivelRSCTaeAdmin(ModelAdminPlus):
    """Trilha de auditoria das alterações de nível pretendido — somente leitura."""

    list_display_icons = True

    list_display = (
        'processo',
        'nivel_anterior',
        'nivel_novo',
        'alterado_por_vinculo',
        'ip',
        'data_alteracao',
        'get_motivo_curto',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'processo__vinculo__pessoa__pessoafisica__servidor_set__matricula',
        'alterado_por_vinculo__pessoa__nome',
        'motivo',
    )
    list_filter = (
        'nivel_novo',
        'data_alteracao',
    )
    ordering = ('-data_alteracao',)
    readonly_fields = (
        'processo',
        'nivel_anterior',
        'nivel_novo',
        'motivo',
        'alterado_por_vinculo',
        'ip',
        'user_agent',
        'data_alteracao',
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('processo', 'nivel_anterior', 'nivel_novo', 'alterado_por_vinculo')

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description='Motivo')
    def get_motivo_curto(self, obj: AlteracaoNivelRSCTae):
        txt = (obj.motivo or '').strip()
        if not txt:
            return '-'
        return (txt[:97] + '...') if len(txt) > 100 else txt
