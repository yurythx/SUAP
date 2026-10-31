from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import VersaoPDA


@admin.register(VersaoPDA)
class VersaoPDAAdmin(ModelAdminPlus):
    list_display = (
        'pda',
        'numero_formatado',
        'tipo',
        'situacao_no_momento',
        'criado_por',
        'data_criacao',
    )
    list_filter = (
        'tipo',
        'situacao_no_momento',
        'pda',
    )
    search_fields = (
        'pda__titulo',
        'justificativa',
    )
    list_display_icons = True
    ordering = ('-data_criacao',)

    fieldsets = (
        (_('Versão'), {'fields': ('pda', 'major', 'minor', 'patch', 'tipo')}),
        (_('Contexto'), {'fields': ('situacao_no_momento', 'justificativa', 'dados_snapshot')}),
    )
