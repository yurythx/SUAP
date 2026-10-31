from django.contrib import admin, messages

from avaliacao_cursos.forms import QuestionarioForm
from avaliacao_cursos.models import Avaliacao, AvaliacaoComponenteCurricular, Pergunta, Questionario, Resposta, Segmento
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus


class SegmentoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'forma_identificacao')
    display_icons = True


admin.site.register(Segmento, SegmentoAdmin)


class AvaliacaoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ano', 'segmentos_envolvidos', 'modalidades_avaliadas')
    list_filter = ('ano',)
    display_icons = True
    list_display_icons = True

    def segmentos_envolvidos(self, obj):
        return obj.get_segmentos()

    def modalidades_avaliadas(self, obj):
        return obj.get_modalidades()


admin.site.register(Avaliacao, AvaliacaoAdmin)


class QuestionarioAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('segmentos_respondentes', 'modalidades_avaliadas')
    list_filter = ('segmentos', 'modalidades')
    display_icons = True
    form = QuestionarioForm

    def segmentos_respondentes(self, obj):
        return obj.get_segmentos()

    def modalidades_avaliadas(self, obj):
        return obj.get_modalidades()


admin.site.register(Questionario, QuestionarioAdmin)


class RespostaAdmin(ModelAdminPlus):
    list_display = ('resposta',)
    display_icons = True
    list_display_icons = True
    actions = 'aprovar', 'reprovar'
    list_filter = CustomTabListFilter, 'aprovada'
    search_fields = ('resposta',)

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(resposta='').filter(pergunta__tipo_resposta=Pergunta.RESPOSTA_SUBJETIVA)

    def aprovar(self, request, queryset):
        queryset.update(aprovada=True)
        messages.success(request, 'Respostas aprovadas com sucesso.')

    aprovar.short_description = 'Validar respostas selecionadas'

    def reprovar(self, request, queryset):
        queryset.update(aprovada=False)
        messages.success(request, 'Respostas reprovadas com sucesso.')

    reprovar.short_description = 'Ignorar respostas selecionadas'

    def get_tabs(self, request):
        return ['tab_validacao_pendente']

    def tab_validacao_pendente(self, request, queryset):
        return queryset.filter(aprovada__isnull=True)

    tab_validacao_pendente.short_description = 'Validação Pendente'


admin.site.register(Resposta, RespostaAdmin)


class AvaliacaoComponenteCurricularAdmin(ModelAdminPlus):
    list_display = ('justificativa',)
    display_icons = True
    list_display_icons = True
    actions = 'aprovar', 'reprovar'
    list_filter = CustomTabListFilter, 'aprovada'
    search_fields = ('justificativa',)

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(justificativa='')

    def aprovar(self, request, queryset):
        queryset.update(aprovada=True)
        messages.success(request, 'Respostas aprovadas com sucessos.')

    aprovar.short_description = 'Validar respostas selecionadas'

    def reprovar(self, request, queryset):
        queryset.update(aprovada=False)
        messages.success(request, 'Respostas reprovadas com sucesso.')

    reprovar.short_description = 'Ignorar respostas selecionadas'

    def get_tabs(self, request):
        return ['tab_validacao_pendente']

    def tab_validacao_pendente(self, request, queryset):
        return queryset.filter(aprovada__isnull=True)

    tab_validacao_pendente.short_description = 'Validação Pendente'


admin.site.register(AvaliacaoComponenteCurricular, AvaliacaoComponenteCurricularAdmin)
