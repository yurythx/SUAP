from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from dados_abertos.models import AtualizacaoBaseDados
from djtools.contrib.admin import ModelAdminPlus


@admin.register(AtualizacaoBaseDados)
class AtualizacaoBaseDadosAdmin(ModelAdminPlus):
    """Trilha da rotina de atualização automática — somente leitura, como todo histórico."""

    list_display = ('base_dados', 'get_resultado_display', 'recursos_atualizados', 'data')
    list_filter = ('resultado',)
    search_fields = ('base_dados__titulo', 'base_dados__nome', 'detalhe')
    date_hierarchy = 'data'
    # Sem o ícone, o Django liga a 1ª coluna ao change view, negado a todos (somente leitura).
    list_display_icons = True
    readonly_fields = ('base_dados', 'resultado', 'detalhe', 'recursos_atualizados', 'data')

    @admin.display(description=_('Resultado'), ordering='resultado')
    def get_resultado_display(self, obj):
        return obj.get_resultado_display()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
