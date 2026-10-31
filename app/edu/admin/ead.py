from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.models import RateioOfertaEAD, OfertaEAD


class RateioOfertaEADAdmin(ModelAdminPlus):
    list_display = (
        'descricao',
        'percentual_gestor_tecnologico',
        'percentual_gestor_oferta',
        'percentual_ofertantes_associados',
        'percentual_receptores',
    )
    list_display_icons = True

    fieldsets = (
        ('Dados Gerais', {'fields': ('descricao',)}),
        (
            'Percentuais de Distribuição',
            {
                'fields': (
                    ('percentual_gestor_tecnologico', 'percentual_gestor_oferta'),
                    ('percentual_ofertantes_associados', 'percentual_receptores'),
                )
            },
        ),
        (
            'Pesos para Ofertantes Associados',
            {'fields': (('peso_ofertantes_associados_ch_presencial_maior_50', 'peso_ofertantes_associados_ch_presencial_meno_50'),)},
        ),
        ('Pesos para Receptores', {'fields': (('peso_receptores_ch_presencial_maior_50', 'peso_receptores_ch_presencial_meno_50'),)}),
    )


admin.site.register(RateioOfertaEAD, RateioOfertaEADAdmin)


class OfertaEADAdmin(ModelAdminPlus):
    list_display = ('descricao', 'rateio', 'gestor_tecnologico')
    list_display_icons = True
    list_filter = ('gestor_tecnologico',)

    fieldsets = (
        ('Dados Gerais', {'fields': ('descricao',)}),
        ('Dados do Rateio', {'fields': ('rateio', 'gestor_tecnologico')}),
    )


admin.site.register(OfertaEAD, OfertaEADAdmin)
