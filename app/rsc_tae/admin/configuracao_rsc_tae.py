from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import ConfiguracaoRSCTae


@admin.register(ConfiguracaoRSCTae)
class ConfiguracaoRSCTaeAdmin(ModelAdminPlus):
    list_display = ('titulo',)

    fieldsets = (
        (
            'Identificação',
            {
                'fields': ('titulo',),
            },
        ),
        (
            'Configurações de quantidade de deliberações por item',
            {
                'fields': ('quantidade_deliberacoes_item',),
            },
        ),
        (
            'Prazos de SLA (dias corridos)',
            {
                'fields': (
                    'dias_prazo_preenchimento',
                    'dias_prazo_validacao_rh',
                    'dias_prazo_correcao',
                    'dias_prazo_avaliacao',
                ),
            },
        ),
        (
            'Sinalização na listagem de processos',
            {
                'fields': ('situacoes_exercicio_externo',),
                'description': 'Marcadores exibidos na coluna "Servidor" da listagem de processos, visíveis apenas ao RH sistêmico e aos membros da CRSC.',
            },
        ),
        (
            'Textos de instrução',
            {
                'fields': (
                    'texto_instrucao_preenchimento',
                    'texto_instrucao_avaliacao',
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        if ConfiguracaoRSCTae.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
