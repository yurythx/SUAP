from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.forms import PrevisaoQuantidadeAlunosFormset
from edu.models import CenarioOferta, PrevisaoQuantidadeAlunos


class PrevisaoQuantidadeAlunosInline(admin.TabularInline):
    formset = PrevisaoQuantidadeAlunosFormset
    model = PrevisaoQuantidadeAlunos
    fields = 'matriz', 'turno', 'qtd_ingressantes', 'qtd_turmas', 'taxa_evasao_1'


class CenarioOfertaAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = 'descricao', 'uo', 'ano_letivo', 'periodo_letivo'
    list_filter = 'uo', 'ano_letivo', 'periodo_letivo'
    list_display_icons = True
    inlines = (PrevisaoQuantidadeAlunosInline,)
    exclude = ('ignorar_afastamentos',)


admin.site.register(CenarioOferta, CenarioOfertaAdmin)
