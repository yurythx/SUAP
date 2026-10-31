from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus

from ..models import DeliberacaoLAI


@admin.register(DeliberacaoLAI)
class DeliberacaoLAIAdmin(ModelAdminPlus):
    """Consulta da linha do tempo do ciclo LAI. Somente leitura: eventos nascem do fluxo."""

    list_display = ('pda_base_dados', 'get_tipo_display', 'autor', 'data')
    list_filter = ('tipo', 'pda_base_dados__pda')
    search_fields = ('pda_base_dados__base_dados__titulo', 'pda_base_dados__base_dados__nome', 'texto')
    date_hierarchy = 'data'
    # Sem o ícone, o Django liga a 1ª coluna ao change view, que é negado a todos (somente leitura):
    # clicar no evento dava "permissão negada", inclusive ao superusuário.
    list_display_icons = True
    readonly_fields = ('pda_base_dados', 'tipo', 'texto', 'autor', 'data', 'ip', 'user_agent')

    def has_add_permission(self, request):
        return False  # eventos são registrados pelo fluxo, nunca à mão

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # apagar evento é apagar rastreabilidade
