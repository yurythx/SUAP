from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import Nivel


@admin.register(Nivel)
class NivelAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = (
        'get_ordem_romana',
        'nome',
        'valor_iq',
        'numero_minimo_itens',
        'pontuacao_minima',
        'get_iq_requisito',
        'get_iq_equivalente',
        'get_requisitos_obrigatorios',
        'ativo',
    )
    list_filter = ('ativo',)
    search_fields = Nivel.SEARCH_FIELDS
    ordering = ('ordem', 'nome')
    filter_horizontal = ('iq_requisito', 'iq_equivalente', 'requisitos_obrigatorios')

    @admin.display(description='Ordem', ordering='ordem')
    def get_ordem_romana(self, obj):
        return obj.ordem_romana

    @admin.display(description='IQs Requisito')
    def get_iq_requisito(self, obj):
        return ', '.join([str(titulo) for titulo in obj.iq_requisito.all()])

    @admin.display(description='IQs Equivalente')
    def get_iq_equivalente(self, obj):
        return ', '.join([str(titulo) for titulo in obj.iq_equivalente.all()])

    @admin.display(description='Requisitos Obrigatórios (RN04)')
    def get_requisitos_obrigatorios(self, obj):
        return ', '.join([r.numeral_romano for r in obj.requisitos_obrigatorios.order_by('numero')]) or '—'
