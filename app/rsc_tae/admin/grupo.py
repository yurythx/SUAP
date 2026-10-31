from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import GrupoSaberCompetencia


@admin.register(GrupoSaberCompetencia)
class GrupoSaberCompetenciaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'get_requisito_display',
        'numero',
        'pontuacao_unidade',
        'descricao',
        'get_qtd_itens',
    )
    list_filter = ('requisito',)
    search_fields = ('descricao',)
    ordering = ('requisito__numero', 'numero')
    list_select_related = ('requisito',)
    raw_id_fields = ('requisito',)

    @admin.display(description='Requisito', ordering='requisito__numero')
    def get_requisito_display(self, obj):
        return obj.requisito_label_curto

    @admin.display(description='Qtd. itens')
    def get_qtd_itens(self, obj):
        return obj.itens.count()
