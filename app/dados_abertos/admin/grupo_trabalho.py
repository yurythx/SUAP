from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import GrupoTrabalho
from .inlines import ResponsavelGrupoTrabalhoInline


@admin.register(GrupoTrabalho)
class GrupoTrabalhoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'pda', 'situacao', 'responsaveis', 'data_cadastro', 'data_finalizado')
    list_filter = ('situacao', 'pda')
    search_fields = ('descricao', 'pda__titulo')
    date_hierarchy = 'data_cadastro'
    ordering = ('-data_cadastro',)
    inlines = [ResponsavelGrupoTrabalhoInline]
    list_display_icons = True

    fieldsets = ((_('Grupo de Trabalho'), {'fields': ('pda', 'descricao', 'situacao', 'data_cadastro', 'data_finalizado')}),)
    readonly_fields = ('data_cadastro', 'data_finalizado')

    def responsaveis(self, obj):
        html = '<ul>'
        for responsavel in obj.responsavelgrupotrabalho_set.all():
            html += f'<li>{responsavel.responsavel}</li>'
        html += '</ul>'
        return mark_safe(html)
