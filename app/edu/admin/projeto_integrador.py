from django.contrib import admin
from djtools.admin import ModelAdminPlus
from django.http import HttpResponseRedirect

from edu.models import ProjetoIntegrador, AtividadeProjetoIntegrador
from edu.forms import ProjetoIntegradorForm
from edu import perms


class AtividadeProjetoIntegradorInline(admin.StackedInline):
    model = AtividadeProjetoIntegrador
    extra = 0
    fieldsets = (
        ('Dados gerais', {'fields': ('projeto_integrador', 'nome', 'descricao')}),
        ('Datas', {'fields': (('data_prevista_inicio', 'data_prevista_termino'))}),
    )


class ProjetoIntegradorAdmin(ModelAdminPlus):
    list_display_icons = True
    form = ProjetoIntegradorForm
    inlines = (AtividadeProjetoIntegradorInline,)
    list_display = (
        'get_ano_letivo',
        'get_periodo_letivo',
        'diario',
        'tema',
    )
    list_filter = (
        'diario__ano_letivo',
        'diario__periodo_letivo',
        'diario__turma__curso_campus',
        'diario__turma__curso_campus__modalidade',
        'diario__componente_curricular__componente',
        'participantes__matricula_periodo__aluno',
    )

    fieldsets = (
        ('Dados Gerais', {'fields': ('diario', 'tema', 'professores')}),
        ('Paticipantes', {'fields': ('participantes',)}),
    )

    edit_fieldsets = (('Dados gerais', {'fields': ('diario', 'tema', 'professores')}),)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.fieldsets
        return self.edit_fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request, ProjetoIntegrador.locals).select_related('diario__turma__curso_campus')

    def get_ano_letivo(self, obj):
        return obj.diario.ano_letivo

    get_ano_letivo.short_description = 'Ano letivo'

    def get_periodo_letivo(self, obj):
        return obj.diario.periodo_letivo

    get_periodo_letivo.short_description = 'Período letivo'

    def get_action_bar(self, request, remove_add_button=False):
        return []

    def response_add(self, request, obj):
        self.message_user(request, 'Projeto cadastrado com sucesso.')
        return HttpResponseRedirect(f'/edu/meu_diario/{obj.diario_id}/1/?tab=pi')

    def response_change(self, request, obj):
        self.message_user(request, 'Projeto atualizado com sucesso.')
        view = 'meu_diario' if obj.diario.professordiario_set.filter(professor__vinculo__user_id=request.user.id).exists() else 'diario'
        return HttpResponseRedirect(f'/edu/{view}/{obj.diario_id}/1/?tab=pi')

    def has_change_permission(self, request, obj=None):
        if obj:
            if (
                not obj.is_professor(request.user) and not perms.realizar_procedimentos_academicos(request.user, obj.diario.turma.curso_campus)
            ) or obj.finalizado:
                return False
        return super().has_change_permission(request, obj)


admin.site.register(ProjetoIntegrador, ProjetoIntegradorAdmin)
