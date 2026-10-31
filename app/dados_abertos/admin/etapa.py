from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import Etapa


@admin.register(Etapa)
class EtapaAdmin(ModelAdminPlus):
    list_display = (
        'ordem',
        'titulo',
        'dispara_analise_lai',
        'pulavel',
        'data_atualizacao',
    )
    list_editable = ('dispara_analise_lai', 'pulavel')
    search_fields = (
        'titulo',
        'descricao',
    )
    ordering = ('ordem',)
    list_display_icons = True

    fieldsets = ((_('Etapa'), {'fields': ('ordem', 'titulo', 'descricao', 'dispara_analise_lai', 'pulavel')}),)
