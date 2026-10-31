from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus

from rsc_tae.models import AvaliacaoProcessoRSCTae


@admin.register(AvaliacaoProcessoRSCTae)
class AvaliacaoProcessoRSCTaeAdmin(ModelAdminPlus):
    list_display = (
        'processo',
        'avaliador_vinculo',
        'pontuacao_final',
        'substituido',
        'data_finalizacao',
        'data_cadastro',
        'data_ultima_alteracao',
    )
    search_fields = (
        'processo__vinculo__pessoa__nome',
        'avaliador_vinculo__pessoa__nome',
    )
    list_filter = ('data_finalizacao', 'substituido')
    ordering = ('-data_ultima_alteracao',)
    readonly_fields = (
        'processo',
        'avaliador_vinculo',
        'pontuacao_final',
        # 'data_finalizacao',
        'motivo_indeferimento',
        'data_cadastro',
        'data_ultima_alteracao',
    )
