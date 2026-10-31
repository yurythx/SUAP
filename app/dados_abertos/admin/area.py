from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import Area


@admin.register(Area)
class AreaAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao_curta')
    search_fields = Area.SEARCH_FIELDS
    ordering = ('nome',)
    list_display_icons = True

    fieldsets = ((_('Área'), {'fields': ('nome', 'descricao')}),)

    def descricao_curta(self, obj):
        if not obj.descricao:
            return '-'
        return (obj.descricao[:60] + '…') if len(obj.descricao) > 60 else obj.descricao

    descricao_curta.short_description = _('Descrição')
