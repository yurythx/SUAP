from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import Requisito


@admin.register(Requisito)
class RequisitoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'numeral_romano',
        'descricao_curta',
        'descricao',
        'ativo',
        'get_qtd_grupos',
    )
    list_filter = ('ativo',)
    search_fields = ('descricao', 'descricao_curta')
    ordering = ('numero',)

    @admin.display(description='Qtd. grupos')
    def get_qtd_grupos(self, obj):
        return obj.grupos.count()
