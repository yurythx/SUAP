from django.contrib import admin
from django.db.models import Count
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import Licenca


@admin.register(Licenca)
class LicencaAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo_ckan', 'descricao_curta', 'bases_relacionadas')
    search_fields = Licenca.SEARCH_FIELDS
    ordering = ('nome',)
    list_display_icons = True

    fieldsets = ((_('Licença'), {'fields': ('nome', 'codigo_ckan', 'descricao')}),)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_bases_count=Count('basedados'))

    @admin.display(description=_('Bases'))
    def bases_relacionadas(self, obj):
        return getattr(obj, '_bases_count', 0)

    def descricao_curta(self, obj):
        if not obj.descricao:
            return '-'
        return (obj.descricao[:60] + '…') if len(obj.descricao) > 60 else obj.descricao

    descricao_curta.short_description = _('Descrição')
