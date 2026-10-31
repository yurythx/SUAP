from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import PalavraChave


@admin.register(PalavraChave)
class PalavraChaveAdmin(ModelAdminPlus):
    list_display = ('termo',)
    search_fields = PalavraChave.SEARCH_FIELDS
    ordering = ('termo',)
    list_display_icons = True

    fieldsets = ((_('Palavra-chave'), {'fields': ('termo',)}),)
