from django.contrib import admin
from django.urls import path
from django.utils.safestring import mark_safe
from django_celery_beat.admin import PeriodicTaskAdmin

from djtools.contrib.admin import ModelAdminPlus
from djtools.utils import httprr

from .forms import AgendamentoForm
from .models import Agendamento, Crontab, Intervalo, ResultadoExecucao


class ResultadoExecucaoAdmin(ModelAdminPlus):
    list_display = ('id', 'command_name', 'args', 'kwargs', 'datetime_start', 'datetime_end', 'get_status_display', 'task_id', 'get_opcoes')
    list_filter = ('status', 'datetime_start', 'datetime_end')
    ordering = ('-datetime_start',)
    search_fields = ('command_name',)
    list_display_icons = True
    safe_view = True

    def get_urls(self):
        new_urls = [path('<str:obj_pk>/cancelar/', self.cancelar)]
        return new_urls + super().get_urls()

    def cancelar(self, request, obj_pk):
        obj = self.get_object(request, obj_pk)
        if request.user.is_superuser:
            obj.revoke()
            return httprr('/admin/beat/resultadoexecucao/', 'A tarefa agendada foi cancelada.', tag='success')
        else:
            return httprr('/admin/beat/resultadoexecucao/', 'Você não tem permissão para fazer isso.', tag='error')

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        if obj.status in [ResultadoExecucao.STATUS_PENDING, ResultadoExecucao.STATUS_RUNNING] and self.request.user.is_superuser:
            texto += f'<li><a href="/admin/beat/resultadoexecucao/{obj.pk:d}/cancelar/" class="btn danger"><span class="fas fa-trash" aria-hidden="true"></span>Cancelar execução</a></li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def get_status_display(self, obj):
        return obj.get_status_display()

    get_status_display.short_description = 'Status'
    get_status_display.admin_order_field = 'status'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(ResultadoExecucao, ResultadoExecucaoAdmin)


admin.site.register(Intervalo, ModelAdminPlus)
admin.site.register(Crontab, ModelAdminPlus)


class AgendamentoAdmin(PeriodicTaskAdmin, ModelAdminPlus):
    list_display = ('name', 'enabled', 'scheduler', 'start_time', 'last_run_at', 'one_off')
    form = AgendamentoForm

    fieldsets = (
        (
            'Geral',
            {
                'fields': ('name', 'regtask', 'enabled', 'description'),
            },
        ),
        (
            'Argumentos',
            {
                'fields': ('args', 'kwargs'),
            },
        ),
        (
            'Agendamento',
            {
                'fields': ('interval', 'crontab', 'start_time', 'last_run_at', 'one_off'),
            },
        ),
        (
            'Opções de Execução',
            {
                'fields': ('expires', 'expire_seconds'),
            },
        ),
    )


admin.site.register(Agendamento, AgendamentoAdmin)
