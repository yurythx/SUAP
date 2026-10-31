from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..forms import TopicoDocumentoPDAForm
from ..models import TopicoDocumentoPDA


@admin.register(TopicoDocumentoPDA)
class TopicoDocumentoPDAAdmin(ModelAdminPlus):
    list_display = ('titulo', 'pda', 'ordem', 'data_atualizacao')
    list_filter = ('pda',)
    search_fields = ('titulo', 'conteudo')
    ordering = ('pda', 'ordem', 'titulo')
    form = TopicoDocumentoPDAForm
    list_display_icons = True

    fieldsets = (
        (_('Tópico'), {'fields': ('pda', 'titulo', 'conteudo', 'ordem')}),
        (_('Metadados'), {'fields': ('data_atualizacao',), 'classes': ('collapse',)}),
    )
    readonly_fields = ('data_atualizacao',)
