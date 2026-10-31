from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from ..models import Acao


@admin.register(Acao)
class AcaoAdmin(ModelAdminPlus):
    list_display = (
        'etapa',
        'ordem',
        'titulo',
        'obrigatoria',
        'condicao_automatica',
        'data_atualizacao',
    )
    list_filter = (
        'etapa',
        'obrigatoria',
        'condicao_automatica',
    )
    search_fields = (
        'titulo',
        'descricao',
        'etapa__titulo',
    )
    ordering = ('etapa__ordem', 'ordem', 'titulo')
    list_select_related = ('etapa',)
    list_display_icons = True

    fieldsets = (
        (
            _('Ação'),
            {
                'fields': (
                    'etapa',
                    'ordem',
                    'titulo',
                    'descricao',
                    'obrigatoria',
                    'condicao_automatica',
                )
            },
        ),
    )
