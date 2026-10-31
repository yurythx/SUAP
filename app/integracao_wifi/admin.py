from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_
from djtools.utils import httprr
from integracao_wifi.forms import AutorizacaoDispositivoForm
from integracao_wifi.models import AutorizacaoDispositivo, TokenWifi


class TokenWifiAdmin(ModelAdminPlus):
    list_display = 'cadastrado_por', 'usuario_solicitante', 'data_solicitacao', 'validade', 'identificacao', 'chave'
    exclude = 'chave', 'cadastrado_por'
    fieldsets = (
        ('Dados da Solicitação', {'fields': ('usuario_solicitante',)}),
        ('Validade', {'fields': (('data_solicitacao', 'validade'),)}),
        ('Chave', {'fields': ('identificacao',)}),
    )
    list_display_icons = True

    def get_action_bar(self, request):
        actions = super().get_action_bar(request)
        actions.append({'url': '/integracao_wifi/gerar_tokens_wifi/', 'label': 'Gerar Tokens em Lote'})
        return actions


admin.site.register(TokenWifi, TokenWifiAdmin)


class AutorizacaoDispositivoAdmin(ModelAdminPlus):
    form = AutorizacaoDispositivoForm
    list_display = (
        'vinculo_solicitante',
        'nome_dispositivo',
        'endereco_mac_dispositivo',
        'data_validade_autorizacao',
        'get_ativa',
        'get_valida',
        'get_acoes',
    )
    list_filter = (CustomTabListFilter, 'localizacao_dispositivo', 'expirada', 'excluida', 'vinculo_solicitante')
    search_fields = ('endereco_mac_dispositivo', 'vinculo_solicitante__search', 'nome_dispositivo')
    actions = ['revogar_autorizacao', 'cancelar_autorizacao']
    change_form_template = 'integracao_wifi/templates/adminutils/change_form.html'
    list_display_icons = True

    def has_add_permission(self, request):
        qtd_maximas_dispositivos_por_usuario = Configuracao.get_valor_por_chave('integracao_wifi', 'qtd_maximas_dispositivos_por_usuario')
        if qtd_maximas_dispositivos_por_usuario:
            if request.user.has_perm('integracao_wifi.pode_escolher_prazo_extendido_iot'):
                return super().has_add_permission(request)
            return False if self.get_queryset(request).count() >= int(qtd_maximas_dispositivos_por_usuario) else super().has_add_permission(request)
        else:
            return super().has_add_permission(request)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['texto_politica_utilizacao'] = Configuracao.get_valor_por_chave('integracao_wifi', 'texto_politica_utilizacao')
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_ativa(self, obj):
        return format_(not obj.expirada)

    get_ativa.short_description = 'Ativa'
    get_ativa.admin_order_field = 'expirada'

    def get_valida(self, obj):
        return format_(not obj.excluida)

    get_valida.short_description = 'Válida'
    get_valida.admin_order_field = 'excluida'

    def get_actions(self, request):
        if not request.user.has_perm('integracao_wifi.eh_administrador_iot'):
            return {}
        else:
            return super().get_actions(request)

    def get_acoes(self, obj):
        if obj.excluida:
            return None

        html = []
        html.append('<ul class="action-bar">')
        if obj.expirada:
            html.append(f'<li><a class="btn success popup" href="/integracao_wifi/renovar_autorizacao/{obj.pk}/">Renovar</a></li>')
        else:
            html.append(f'<li><a class="btn danger" href="/integracao_wifi/revogar_autorizacao/{obj.pk}/">Revogar</a><li>')
        html.append(f'<li><a class="btn confirm" href="/integracao_wifi/cancelar_autorizacao/{obj.pk}/">Cancelar Solicitação</a></li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Ações'

    def revogar_autorizacao(self, request, queryset):
        for item in queryset:
            item.revogar_autorizacao()

        messages.success(request, 'Autorizações(s) revogada(s) com sucesso.')

    revogar_autorizacao.short_description = 'REVOGAR autorização(ões) do(s) dispositivo(s) selecionado(s)'

    def cancelar_autorizacao(self, request, queryset):
        for item in queryset:
            item.cancelar_autorizacao()

        messages.success(request, 'Autorizações(s) revogada(s) com sucesso.')

    cancelar_autorizacao.short_description = 'CANCELAR autorização(ões) do(s) dispositivo(s) selecionado(s)'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        if request.user.has_perm('integracao_wifi.eh_administrador_iot'):
            return super().get_queryset(request, manager, *args, **kwargs)

        return AutorizacaoDispositivo.objects.filter(vinculo_solicitante=request.user.get_vinculo(), excluida=False)

    def get_tabs(self, request):
        if request.user.has_perm('integracao_wifi.eh_administrador_iot'):
            return ['tab_expiradas', 'tab_canceladas']
        else:
            return []

    def tab_expiradas(self, request, queryset):
        return queryset.filter(expirada=True)

    tab_expiradas.short_description = 'Expiradas'

    def tab_canceladas(self, request, queryset):
        return queryset.filter(excluida=True)

    tab_canceladas.short_description = 'Canceladas'

    def add_view(self, *args, **kwargs):
        try:
            return super().add_view(*args, **kwargs)
        except ValidationError as e:
            return httprr('..', str(e), 'error')

    def change_view(self, *args, **kwargs):
        try:
            return super().change_view(*args, **kwargs)
        except ValidationError as e:
            return httprr('..', str(e), 'error')


admin.site.register(AutorizacaoDispositivo, AutorizacaoDispositivoAdmin)
