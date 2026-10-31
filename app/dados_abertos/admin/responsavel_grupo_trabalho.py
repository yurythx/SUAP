from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import ResponsavelGrupoTrabalho


@admin.register(ResponsavelGrupoTrabalho)
class ResponsavelGrupoTrabalhoAdmin(ModelAdminPlus):
    list_display = ('grupo_trabalho', 'responsavel', 'ativo', 'data_cadastro')
    list_filter = ('ativo', 'grupo_trabalho')
    search_fields = ('grupo_trabalho__descricao',)
    date_hierarchy = 'data_cadastro'
    ordering = ('-data_cadastro',)
    list_display_icons = True

    fieldsets = ((_('Responsável'), {'fields': ('grupo_trabalho', 'responsavel', 'ativo', 'data_cadastro')}),)
    readonly_fields = ('data_cadastro',)
