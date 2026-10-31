from django.contrib import admin
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.management.commands import format_time
from djtools.templatetags.filters.utils import format_datetime, format_user
from djtools.utils import httprr
from solenidades.forms import AgendamentoSolenidadeForm
from solenidades.models import AgendamentoSolenidade


@admin.register(AgendamentoSolenidade)
class AgendamentoSolenidadeAdmin(ModelAdminPlus):
    change_form_template = 'solenidades/templates/admin/solenidades/change_form.html'
    list_filter = ('deferida', 'representante', 'solicitante', 'responsavel')
    list_display_icons = True
    list_display = ('data', 'get_hora_inicio', 'local', 'descricao', 'get_representante', 'get_solicitante', 'get_opcoes')
    form = AgendamentoSolenidadeForm
    date_hierarchy = 'data'
    fieldsets = (('', {'fields': (('data', 'hora_inicio'), 'local', 'descricao')}),)

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        if request.user.has_group_cached('Operador de Gabinete Sistêmico', ignore_groups_if_superuser=False):
            return queryset.filter(cancelada=False)

        user = request.user
        uo = get_uo(user)
        queryset = queryset.filter(solicitante__setor__uo=uo)
        return queryset

    @mark_safe
    @admin.display(description='Hora de Início', ordering='hora_inicio')
    def get_hora_inicio(self, obj):
        return format_time(obj.hora_inicio)

    @mark_safe
    @admin.display(description='Reitor/Representante')
    def get_representante(self, obj):
        return format_user(obj.representante) if obj.representante else ''

    @mark_safe
    @admin.display(description='Solicitante')
    def get_solicitante(self, obj):
        return f'{format_user(obj.solicitante)} {format_datetime(obj.data_solicitacao)}'

    @mark_safe
    @admin.display(description='Opções')
    def get_opcoes(self, obj):
        if obj.cancelada:
            return ''
        opcoes = '<ul class="action-bar">'
        if self.request.user == obj.solicitante.user and not obj.deferida:
            opcoes += f'<li><a href="/solenidades/cancelar_agendamento/{obj.id}/" class="btn danger">Cancelar</a></li>'

        if self.request.user.has_group_cached('Operador de Gabinete Sistêmico', ignore_groups_if_superuser=False):
            if obj.deferida is not None:
                opcoes += f'<li><a href="/solenidades/editar_agendamento/{obj.pk}/" class="btn primary popup">Editar</a></li>'

            if obj.deferida is None or not obj.deferida:
                opcoes += f'<li><a href="/solenidades/deferir_agendamento/{obj.pk}/" class="btn success popup">Deferir</a></li>'

            if obj.deferida is None or obj.deferida:
                opcoes += f'<li><a href="/solenidades/indeferir_agendamento/{obj.pk}/" class="btn danger">Indeferir</a></li>'

        opcoes += '</ul>'
        return opcoes

    def render_change_form(self, request, context, *args, **kwargs):
        extra = {'calendario': AgendamentoSolenidade.programacao_atual()}
        context.update(extra)
        return super().render_change_form(request, context, *args, **kwargs)

    def response_add(self, request, obj, post_url_continue=None):
        if '_continue' in request.POST or '_addanother' in request.POST or 'popup' in request.POST:
            return super().response_add(request, obj)
        else:
            msg = f'{obj._meta.verbose_name} cadastrado com sucesso.'
            return httprr(f'/solenidades/ver_agendamento/{obj.pk}/', msg)

    def response_change(self, request, obj):
        if '_continue' in request.POST or '_addanother' in request.POST or 'popup' in request.POST:
            return super().response_change(request, obj)
        else:
            msg = f'{obj._meta.verbose_name} editado com sucesso.'
            return httprr(f'/solenidades/ver_agendamento/{obj.pk}/', msg)
