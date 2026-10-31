from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import RolSaberCompetencia


@admin.register(RolSaberCompetencia)
class RolSaberCompetenciaAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'numero',
        'get_requisito_display',
        'grupo',
        'titulo',
        'unidade_medida',
        'get_pontuacao_unidade',
        'item_temporal',
        'aceita_papel',
        'pontuacao_unidade_substituto',
        'ativo',
    )
    list_filter = ('ativo', 'item_temporal', 'aceita_papel', 'grupo__requisito', 'grupo')
    search_fields = ('titulo', 'descricao')
    ordering = ('grupo__requisito__numero', 'grupo__numero', 'numero')
    list_select_related = ('grupo__requisito',)
    raw_id_fields = ('grupo',)

    @admin.display(description='Requisito', ordering='grupo__requisito__numero')
    def get_requisito_display(self, obj):
        return obj.requisito_label_curto

    @admin.display(description='Pts/unidade', ordering='grupo__pontuacao_unidade')
    def get_pontuacao_unidade(self, obj):
        return obj.pontuacao_unidade
