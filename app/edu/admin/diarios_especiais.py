from django.contrib import admin, messages
from django.shortcuts import redirect

from djtools.contrib.admin import ModelAdminPlus
from djtools.utils import httprr
from edu.forms import ConfiguracaoCreditosEspeciaisForm, DiarioEspecialForm
from edu.models import ConfiguracaoCreditosEspeciais, DiarioEspecial


class ConfiguracaoCreditosEspeciaisAdmin(ModelAdminPlus):
    list_display = ('descricao', 'quantidade_maxima_creditos_especiais', 'ativo')
    search_fields = ('descricao',)
    ordering = ('descricao',)
    export_to_xls = True
    list_per_page = 15
    list_display_icons = True

    form = ConfiguracaoCreditosEspeciaisForm
    fieldsets = ConfiguracaoCreditosEspeciaisForm.fieldsets

    def get_queryset(self, request):
        return self.model.objects.all()

    def response_add(self, request, obj):
        return httprr(
            obj.get_absolute_url(), 'Configuração cadastrada com sucesso. Adicione os tipos de atividades relacionadas e seus respectivos créditos.'
        )

    def delete_view(self, request, object_id, extra_context=None):
        configuracao = ConfiguracaoCreditosEspeciais.objects.get(pk=object_id)
        if configuracao.matriz_set.all():
            msg = 'Não é possível realizar a exclusão. Existem matrizes vinculadas a esta configuração.'
        elif configuracao.tem_alunos_vinculados():
            msg = 'Não é possível realizar a exclusão. Existem alunos com créditos especiais que utilizam esta configuracão.'
        else:
            return super().delete_view(request, object_id, extra_context)
        messages.error(request, msg)
        return redirect('..')


admin.site.register(ConfiguracaoCreditosEspeciais, ConfiguracaoCreditosEspeciaisAdmin)


class DiarioEspecialAdmin(ModelAdminPlus):
    search_fields = ('componente__descricao', 'componente__sigla', 'professores__vinculo__user__username', 'professores__vinculo__pessoa__nome')
    list_filter = ('ano_letivo', 'periodo_letivo')
    list_display = ('ano_letivo', 'periodo_letivo', 'componente', 'get_professores', 'sala', 'get_horario_aulas')
    list_display_icons = True
    form = DiarioEspecialForm

    fieldsets = (
        ('Dados gerais', {'fields': (('ano_letivo', 'periodo_letivo'), 'diretoria', 'componente')}),
        ('Centro de Aprendizagem', {'fields': ('is_centro_aprendizagem', 'descricao')}),
        ('Professores', {'fields': ('professores',)}),
        ('Participantes', {'fields': ('participantes',)}),
        ('Configuração de Horário', {'fields': ('horario_campus',)}),
    )

    def get_professores(self, obj):
        return obj.get_nomes_professores()

    get_professores.short_description = 'Professores'

    def get_horario_aulas(self, obj):
        return obj.get_horario_aulas()

    get_horario_aulas.short_description = 'Horários de Aula'

    def get_queryset(self, request):
        qs = super().get_queryset(request, DiarioEspecial.locals).select_related('ano_letivo')
        return qs


admin.site.register(DiarioEspecial, DiarioEspecialAdmin)
