from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from pedagogia.forms import QuestionarioMatrizForm
from pedagogia.models import ItemQuestionarioMatriz, PeriodoResposta, QuestionarioMatriz


class ItemQuestionarioMatrizInline(admin.StackedInline):
    model = ItemQuestionarioMatriz
    extra = 60


class PeriodoRespostaAdmin(ModelAdminPlus):
    list_display = ('ano', 'data_inicio', 'data_fim')
    list_display_icons = True
    search_fields = ('ano__ano',)
    list_filter = ('ano',)
    export_to_xls = True


admin.site.register(PeriodoResposta, PeriodoRespostaAdmin)


class QuestionarioMatrizAdmin(ModelAdminPlus):
    form = QuestionarioMatrizForm
    list_display = ('descricao',)
    list_display_icons = True
    export_to_xls = True
    search_fields = ('descricao', 'cursos__descricao_historico')
    list_filter = ('cursos__descricao_historico', 'cursos__modalidade')
    inlines = [ItemQuestionarioMatrizInline]


admin.site.register(QuestionarioMatriz, QuestionarioMatrizAdmin)
