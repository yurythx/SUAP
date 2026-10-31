from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import MarcacaoPDA


@admin.register(MarcacaoPDA)
class MarcacaoPDAAdmin(ModelAdminPlus):
    list_display = ('marcacao_display', 'template_base', 'data_atualizacao')
    search_fields = MarcacaoPDA.SEARCH_FIELDS
    ordering = ('marcacao',)
    list_display_icons = True

    fieldsets = (
        (_('Marcação'), {'fields': ('marcacao', 'template_base')}),
        (_('Metadados'), {'fields': ('data_cadastro', 'data_atualizacao'), 'classes': ('collapse',)}),
    )

    readonly_fields = ('data_cadastro', 'data_atualizacao')

    @admin.display(description=_('Marcação'))
    def marcacao_display(self, obj):
        """Exibe a marcação formatada como código."""
        return format_html(
            '<code style="background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-family: monospace;"> {} </code>', obj.marcacao
        )
