from django.contrib import admin
from djtools.contrib.admin import ModelAdminPlus
from edu.models import PreMatriculaInternacional, TipoInstituicaoEstrangeira
from edu.forms import PreMatriculaInternacionalForm


class TipoInstituicaoEstrangeiraAdmin(ModelAdminPlus):
    list_display = ('nome',)
    list_display_icons = True


admin.site.register(TipoInstituicaoEstrangeira, TipoInstituicaoEstrangeiraAdmin)


class PreMatriculaInternacionalAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ano_letivo', 'periodo_letivo', 'diretoria', 'matriz_curso', 'qtd_vagas')
    list_display_icons = True
    list_filter = ('ano_letivo', 'periodo_letivo', 'diretoria')
    list_per_page = 25
    search_fields = ('descricao',)
    form = PreMatriculaInternacionalForm
    fieldsets = (
        ('Dados Gerais', {'fields': ('descricao', 'diretoria', ('ano_letivo', 'periodo_letivo'))}),
        (
            'Dados da Oferta',
            {
                'fields': (
                    'matriz_curso',
                    'qtd_vagas',
                )
            },
        ),
        ('Datas', {'fields': (('data_inicio_inscricoes', 'data_termino_inscricoes', 'data_limite_correcao_inscricoes'),)}),
    )


admin.site.register(PreMatriculaInternacional, PreMatriculaInternacionalAdmin)
