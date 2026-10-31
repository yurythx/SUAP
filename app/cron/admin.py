from datetime import datetime

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe

from cron import models
from djtools import forms
from djtools.contrib.admin import ChangeListPlus, ModelAdminPlus


class NoLinkChangeList(ChangeListPlus):
    def url_for_result(self, result):
        raise NoReverseMatch


class ComandoAdmin(ModelAdminPlus):
    readonly_fields = ('nome',)
    list_display = ('nome',)
    ordering = ('nome',)

    def get_changelist(self, request, **kwargs):
        self.request = request
        return NoLinkChangeList

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        raise PermissionDenied

    def get_action_bar(self, request, remove_add_button=False):
        items = super().get_action_bar(request, remove_add_button)
        items.append({'url': reverse('atualizar_comandos'), 'label': 'Atualizar lista de comandos', 'css_class': 'success'})
        return items


class ComandoAgendamentoAdmin(ModelAdminPlus):
    list_display = ('comando', 'parametros', 'ativo', 'link_executar')
    ordering = ('comando',)

    def link_executar(self, obj):
        link = None
        if obj.ativo:
            link = '<a class="btn danger" href="{}">Executar</a>'.format(reverse('executar_comando', kwargs={'object_id': obj.id}))
        return mark_safe(link)

    link_executar.short_description = 'Ações'


class LogExecucaoAdmin(ModelAdminPlus):
    readonly_fields = ('comando', 'inicio', 'fim', 'status', 'traceback')
    list_display = ('comando', 'inicio', 'fim', 'duracao', 'status', 'visualizar')
    list_filter = ('comando', 'inicio', 'fim')
    search_fields = ('comando__comando__nome',)
    ordering = ('-fim',)
    fieldsets = (
        (None, {'fields': ('comando', 'status')}),
        ('Quando', {'fields': ('inicio', 'fim')}),
        ('Mensagens', {'fields': ('traceback', 'log')}),
    )

    def duracao(self, obj):
        if obj.fim:
            return obj.fim - obj.inicio
        now = datetime.now()
        return f'Executando a {now - obj.inicio} ...'

    duracao.short_description = 'Duração'

    def get_changelist(self, request, **kwargs):
        self.request = request
        return NoLinkChangeList

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        raise PermissionDenied

    def visualizar(self, obj):
        url_visualizar = f'<a class="btn primary" href="/cron/visualizar_execucao/{obj.id}/">Visualizar</a>'
        url_interromper = ''
        if not obj.fim:
            url_interromper = f'<a class="btn" href="/cron/interromper_comando/{obj.id}/">Interromper</a>'
        link = f'{url_visualizar} {url_interromper}'
        return mark_safe(link)

    visualizar.short_description = 'Ações'


class AgendamentoAdmin(ModelAdminPlus):
    list_display = ('nome', 'minuto', 'hora', 'dia_do_mes', 'mes', 'dia_da_semana', 'ativo')
    ordering = ('nome',)
    search_fields = ('nome',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['comandos'].queryset = models.ComandoAgendamento.objects.filter(ativo=True)
        return form


class AgendamentoDiarioAdmin(AgendamentoAdmin):
    list_display = ('nome', 'minuto', 'hora')
    fields = ('nome', 'minuto', 'hora', 'descricao', 'ativo', 'comandos')


class AgendamentoHoraEmHoraAdmin(AgendamentoAdmin):
    list_display = ('nome', 'minuto')
    fields = ('nome', 'minuto', 'hora', 'descricao', 'ativo', 'comandos')

    def get_changeform_initial_data(self, request):
        initial_data = super().get_changeform_initial_data(request)
        initial_data['hora'] = '*'
        return initial_data

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['hora'].widget = forms.HiddenInput()
        return form


class AgendamentoMensalAdmin(AgendamentoAdmin):
    list_display = ('nome', 'minuto', 'hora', 'dia_do_mes')
    fields = ('nome', 'dia_do_mes', 'ativo', 'comandos')

    def get_changeform_initial_data(self, request):
        initial_data = super().get_changeform_initial_data(request)
        initial_data['dia_do_mes'] = '1'
        return initial_data


class AgendamentoSemanalAdmin(AgendamentoAdmin):
    list_display = ('nome', 'minuto', 'hora', 'dia_da_semana')
    fields = ('nome', 'dia_da_semana', 'ativo', 'comandos')

    def get_changeform_initial_data(self, request):
        initial_data = super().get_changeform_initial_data(request)
        initial_data['dia_da_semana'] = '1'
        return initial_data


admin.site.register(models.Comando, ComandoAdmin)
admin.site.register(models.ComandoAgendamento, ComandoAgendamentoAdmin)
admin.site.register(models.LogExecucao, LogExecucaoAdmin)
admin.site.register(models.Agendamento, AgendamentoAdmin)
admin.site.register(models.AgendamentoDiario, AgendamentoDiarioAdmin)
admin.site.register(models.AgendamentoMensal, AgendamentoMensalAdmin)
admin.site.register(models.AgendamentoSemanal, AgendamentoSemanalAdmin)
admin.site.register(models.AgendamentoHoraEmHora, AgendamentoHoraEmHoraAdmin)
