from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from rsc_tae.models import AvaliacaoAnexoRSCTae


@admin.register(AvaliacaoAnexoRSCTae)
class AvaliacaoAnexoRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'anexo',
        'get_processo',
        'situacao',
        'pontuacao_validada',
        'avaliado_por',
        'data_avaliacao',
        'data_ultima_alteracao',
        'ip_avaliacao',
    )
    search_fields = ('anexo__nome_original', 'anexo__arquivo', 'anexo__processo__vinculo__pessoa__nome')
    list_filter = ('situacao',)
    ordering = ('-data_avaliacao',)
    actions = ('excluir_selecionados',)

    @admin.action(description='Excluir selecionados')
    def excluir_selecionados(self, request, queryset):
        if not self.has_delete_permission(request):
            raise PermissionDenied

        total = queryset.count()
        queryset.delete()
        self.message_user(request, f'{total} registro(s) excluído(s) com sucesso.', level=messages.SUCCESS)

    @admin.display(description='Processo')
    def get_processo(self, obj: AvaliacaoAnexoRSCTae):
        try:
            return obj.anexo.processo
        except Exception:
            return '-'
