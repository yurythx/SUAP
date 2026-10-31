from django.contrib import admin
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import DeliberacaoCRSCRSCTae
from rsc_tae.enums import SituacaoProcesso


@admin.register(DeliberacaoCRSCRSCTae)
class DeliberacaoCRSCRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'processo',
        'get_resultado',
        'pontuacao_final_crsc',
        'deliberado_por_vinculo',
        'finalizacao_manual',
        'data_deliberacao',
    )
    list_display_icons = True
    list_filter = ('resultado', 'finalizacao_manual')
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'deliberado_por_vinculo__pessoa__nome',
    )
    ordering = ('-data_deliberacao',)
    readonly_fields = (
        'processo',
        'deliberado_por_vinculo',
        'finalizacao_manual',
        'data_deliberacao',
        'ip_deliberacao',
        'user_agent',
        'assinatura_hash',
        'assinatura_conteudo',
    )

    fieldsets = (
        (
            None,
            {
                'fields': ('processo', 'resultado', 'pontuacao_final_crsc', 'justificativa'),
            },
        ),
        (
            'Auditoria',
            {
                'fields': (
                    'deliberado_por_vinculo',
                    'finalizacao_manual',
                    'data_deliberacao',
                    'ip_deliberacao',
                    'user_agent',
                    'assinatura_hash',
                    'assinatura_conteudo',
                ),
                'classes': ('collapse',),
            },
        ),
    )

    @admin.display(description='Resultado')
    def get_resultado(self, obj):
        if obj.resultado == SituacaoProcesso.DEFERIDO:
            return format_html('<span class="status status-success">Deferido</span>')
        return format_html('<span class="status status-error">Indeferido</span>')

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
