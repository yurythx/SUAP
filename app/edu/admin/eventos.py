from django.contrib import admin

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, unquote
from djtools.templatetags.filters import in_group
from djtools.utils import httprr
from edu.forms import ColacaoGrauForm, EventoForm
from edu.models import ColacaoGrau, Evento


class ColacaoGrauAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_filter = (CustomTabListFilter, 'ano_letivo', 'periodo_letivo', 'diretoria')
    list_display = ('id', 'descricao', 'data_colacao', 'ano_letivo', 'periodo_letivo', 'diretoria')
    list_display_icons = True
    list_per_page = 15
    exclude = ('deferida',)
    form = ColacaoGrauForm

    def response_add(self, request, obj):
        return httprr(
            f'/edu/adicionar_alunos_colacao_grau/{obj.pk}/?ano_letivo_aluno={obj.ano_letivo.pk}&periodo_letivo_aluno={obj.periodo_letivo}',
            'Colação de Grau cadastrada com sucesso. Adicione os alunos.',
        )

    def get_tabs(self, request):
        return ['tab_agendadas', 'tab_realizadas']

    def tab_agendadas(self, request, queryset):
        return queryset.filter(deferida=False)

    tab_agendadas.short_description = 'Agendadas'

    def tab_realizadas(self, request, queryset):
        return queryset.filter(deferida=True)

    tab_realizadas.short_description = 'Realizadas'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        result = super().change_view(request, object_id, form_url, extra_context)
        if not in_group(request.user, 'Administrador Acadêmico'):
            obj = self.get_object(request, unquote(object_id))
            if obj and obj.deferida:
                return httprr('..', 'Você não tem permissão para editar uma colação de grau já deferida.', 'error')
        return result

    def get_queryset(self, request):
        return super().get_queryset(request, ColacaoGrau.locals)


admin.site.register(ColacaoGrau, ColacaoGrauAdmin)


class EventoAdmin(ModelAdminPlus):
    search_fields = ('titulo', 'descricao')
    list_filter = ('uo',)
    list_display = ('titulo', 'tipo', 'data', 'uo', 'titulo')
    list_display_icons = True
    list_per_page = 15
    date_hierarchy = 'data'
    export_to_xls = True
    form = EventoForm

    def get_queryset(self, request):
        return self.model.locals.all()

    def response_add(self, request, obj):
        return httprr(f'/edu/evento/{obj.pk}/', 'Cadastro realizado com sucesso. Por favor, adicione os participantes do evento/palestra.')

    def response_change(self, request, obj):
        return httprr(f'/edu/evento/{obj.pk}/', 'Cadastro realizado com sucesso. Por favor, adicione os participantes do evento/palestra.')


admin.site.register(Evento, EventoAdmin)
