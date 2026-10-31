from datetime import datetime

from django.conf import settings
from django.contrib import admin, messages
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from djtools.contrib.admin.filters.tab import CustomTabListFilter
from djtools.models import EmailEnviadoLog, PushSubscription, Task
from djtools.templatetags.filters import in_group
from djtools.utils import httprr, send_notification
from comum.models import Vinculo
from suap import celery_app as app


class PushSubscriptionAdmin(ModelAdminPlus):
    list_filter = ('user',)
    list_display = 'user', 'device', 'data'
    list_display_icons = True
    actions = ('testar_envio', 'testar_envio_via_notificacao_suap')

    def testar_envio(self, request, queryset):
        data_hora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        for obj in queryset:
            obj.notify('SUAP', f'Mensagem enviada em {data_hora}')
        messages.success(request, 'Notificação enviada com sucesso.')

    testar_envio.short_description = 'Testar notificação'

    def testar_envio_via_notificacao_suap(self, request, queryset):
        data_hora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        vinculos = Vinculo.objects.filter(user__in=queryset.values_list('user', flat=True))
        send_notification('SUAP', f'Mensagem enviada em {data_hora}', None, vinculos)
        messages.success(request, 'Notificação enviada com sucesso.')

    testar_envio_via_notificacao_suap.short_description = 'Testar via notificação SUAP'


admin.site.register(PushSubscription, PushSubscriptionAdmin)


class TaskAdmin(ModelAdminPlus):
    list_display = ('id', 'type', 'user', 'start', 'get_progress', 'end', 'get_message', 'total', 'partial')
    ordering = ('-start',)
    list_filter = [CustomTabListFilter, 'type']
    search_fields = ('user__username', 'uuid')
    show_count_on_tabs = True
    list_display_icons = True

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('limpar_fila/', self.admin_site.admin_view(self.limpar_fila), name='limpar_fila')]
        return my_urls + urls

    def limpar_fila(self, request):
        if request.user.is_superuser:
            app.control.purge()
            return httprr('..', 'A fila de execução do celery foi resetada.', tag='success')
        else:
            return httprr('..', 'Você não tem permissão para fazer isso.', tag='error')

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.is_superuser:
            list_filter = [*list_filter, 'user']
        return list_filter

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if in_group(request.user, 'Desenvolvedor'):
            return qs
        return qs.filter(user=request.user)

    def get_message(self, obj):
        if in_group(self.request.user, 'Desenvolvedor'):
            return obj.message
        if obj.error:
            return 'Erro ao processar esta tarefa.'
        else:
            return obj.message

    get_message.short_description = 'Situação'

    def get_tabs(self, request):
        return ['tab_em_execucao']

    def tab_em_execucao(self, request, queryset):
        return queryset.filter(end__isnull=True)

    tab_em_execucao.short_description = 'Em Execução'

    def has_view_permission(self, request, obj=None):
        if obj:
            return in_group(request.user, 'Desenvolvedor') or obj.user == request.user
        else:
            return True

    def get_action_bar(self, request):
        items = super().get_action_bar(request, remove_add_button=True)
        if request.user.is_superuser:
            items.append({'url': '/admin/djtools/task/limpar_fila/', 'label': 'Limpar Fila de Execução', 'css_class': 'danger'})
        return items

    def get_progress(self, obj):
        return mark_safe(f"""<div class="progress"><p>{obj.percent}%</p></div>""")

    get_progress.short_description = 'Progresso'


admin.site.register(Task, TaskAdmin)


class EmailEnviadoLogAdmin(ModelAdminPlus):
    list_display = ('id', 'assunto', 'destinatarios', 'data')
    ordering = ('-data',)
    search_fields = ('assunto', 'destinatarios', 'conteudo')
    date_hierarchy = 'data'
    list_display_icons = True
    safe_view = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from comum.models import Configuracao

        opensearch_configurado = bool(Configuracao.get_valor_por_chave('djtools', 'opensearch_host'))
        if opensearch_configurado and settings.EMAIL_LOGGING != 'db':
            return httprr('/djtools/email_logs/')
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(EmailEnviadoLog, EmailEnviadoLogAdmin)
