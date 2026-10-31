from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.forms import ConvocacaoENADEForm, PeriodoConvocacaoRegenciaForm
from edu.models import ConvocacaoENADE, PeriodoConvocacaoRegencia


class ConvocacaoENADEAdmin(ModelAdminPlus):
    search_fields = ('cursos__descricao',)
    list_display = ('ano_letivo', 'tipo_convocacao', 'descricao', 'data_inscricao_ingressantes', 'data_inscricao')
    list_filter = ('ano_letivo', 'tipo_convocacao', 'areas_cursos_formacao_superior', 'cursos')
    list_display_icons = True
    list_per_page = 15
    ordering = ('-ano_letivo__ano',)
    form = ConvocacaoENADEForm

    fieldsets = (
        (
            'Dados da convocação',
            {
                'fields': (
                    'descricao',
                    ('tipo_convocacao', 'ano_letivo'),
                    'situacoes_convocadas',
                    ('data_inscricao_ingressantes',),
                    ('data_inicio_inscricao', 'data_inscricao'),
                )
            },
        ),
        (
            'Dados de curso',
            {
                'fields': (
                    'modalidades_convocadas',
                    'areas_cursos_formacao_superior',
                )
            },
        ),
        (
            'Documentos',
            {
                'fields': (
                    'portaria',
                    'edital',
                )
            },
        ),
    )


admin.site.register(ConvocacaoENADE, ConvocacaoENADEAdmin)


class PeriodoConvocacaoRegenciaAdmin(ModelAdminPlus):
    list_display = ('convocacao_enade', 'data_inicio', 'data_fim')
    list_filter = ('convocacao_enade',)
    list_display_icons = True
    list_per_page = 15
    ordering = ('-convocacao_enade__ano_letivo__ano', 'data_inicio')
    form = PeriodoConvocacaoRegenciaForm


admin.site.register(PeriodoConvocacaoRegencia, PeriodoConvocacaoRegenciaAdmin)
