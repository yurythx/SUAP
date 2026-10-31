from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import Capa


@admin.register(Capa)
class CapaAdmin(ModelAdminPlus):
    list_display = ('pda', 'nome')
    search_fields = ('nome', 'pda__titulo')
    ordering = ('pda', 'nome')
    list_display_icons = True

    fieldsets = ((_('Capa'), {'fields': ('pda', 'nome', 'imagem')}),)
