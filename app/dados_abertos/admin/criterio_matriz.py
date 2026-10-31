from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import CriterioMatriz


@admin.register(CriterioMatriz)
class CriterioMatrizAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = CriterioMatriz.SEARCH_FIELDS
    ordering = ('nome',)
    list_display_icons = True

    fieldsets = ((_('Critério da Matriz'), {'fields': ('nome', 'ativo')}),)
