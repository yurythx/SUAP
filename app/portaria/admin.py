from django.contrib import admin
from django.utils.safestring import mark_safe

from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from djtools.templatetags.tags import icon
from portaria.forms import SolicitacaoEntradaForm
from portaria.models import ConfiguracaoSistemaPortaria, SolicitacaoEntrada


@admin.register(ConfiguracaoSistemaPortaria)
class ConfiguracaoSistemaPortariaAdmin(ModelAdminPlus):
    list_display = ('campus', 'habilitar_camera', 'cracha_obrigatorio', 'habilitar_geracao_chave_wifi', 'url_wifi', 'limite_compartilhamento_chave')
    list_filter = ('campus', 'habilitar_camera', 'cracha_obrigatorio', 'habilitar_geracao_chave_wifi')
    list_display_icons = True
    ordering = ('campus',)


class SolicitacaoEntradaAdmin(ModelAdminPlus):
    list_display = ('get_solicitantes', 'data', 'get_hora_entrada', 'get_hora_saida', 'sala', 'atividade', 'deferida', 'cancelada', 'get_opcoes')
    list_filter = (CustomTabListFilter, 'sala', 'sala__predio', 'sala__predio__uo', 'deferida', 'cancelada')
    list_display_icons = True
    date_hierarchy = 'data'
    form = SolicitacaoEntradaForm
    ordering = ('-data', 'hora_entrada')
    search_fields = ('atividade',)
    show_count_on_tabs = True

    def has_change_permission(self, request, obj=None):
        user = request.user
        perm = super().has_change_permission(request, obj)
        if obj and (in_group(user, 'Coordenador da Sede') or (user.get_vinculo() in obj.solicitantes.all() and obj.pode_editar())):
            return True
        return perm

    def show_list_display_icons(self, obj):
        user = self.request.user
        out = []
        out.append(icon('view', obj.get_absolute_url()))
        if in_group(user, 'Coordenador da Sede') or (user.get_vinculo() in obj.solicitantes.all() and obj.pode_editar()):
            out.append(icon('edit', f'/admin/portaria/solicitacaoentrada/{obj.id}/'))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = 'Ações'

    def get_solicitantes(self, obj):
        return obj.get_solicitantes()

    get_solicitantes.short_description = 'Solicitantes'

    def get_hora_entrada(self, obj):
        return obj.hora_entrada.strftime('%H:%M:%S')

    get_hora_entrada.short_description = 'Hora de Entrada'

    def get_hora_saida(self, obj):
        return obj.hora_saida.strftime('%H:%M:%S')

    get_hora_saida.short_description = 'Hora de Saída'

    def get_opcoes(self, obj):
        user = self.request.user
        texto = '<ul class="action-bar">'
        if obj.deferida is None:
            if user.has_group_cached(['Coordenador da Sede']):
                texto += (
                    f'<li><a href="/portaria/deferir_solicitacaoentrada/{obj.pk}/" class="btn success">Deferir</a></li>'
                    f'<li><a href="/portaria/indeferir_solicitacaoentrada/{obj.pk}/" class="btn danger">Indeferir</a></li>'
                )
            if not obj.cancelada and obj.eh_solicitante(user.get_vinculo()):
                texto += f'<li><a href="/portaria/cancelar_solicitacaoentrada/{obj.pk}/" class="btn danger">Cancelar</a></li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def tab_any_data(self, request, queryset):
        return queryset.filter(sala__predio__uo=get_uo(request.user))

    tab_any_data.short_description = 'Todas'

    def tab_minhas_solicitacoes(self, request, queryset):
        return queryset.filter(solicitantes__user=request.user)

    tab_minhas_solicitacoes.short_description = 'Minhas Solicitações'

    def tab_a_validar(self, request, queryset):
        return queryset.filter(sala__predio__uo=get_uo(request.user), deferida__isnull=True, cancelada=False)

    tab_a_validar.short_description = 'A Validar'

    def get_tabs(self, request):
        tabs = ['tab_any_data', 'tab_minhas_solicitacoes']
        if request.user.has_group_cached('Coordenador da Sede'):
            tabs.append('tab_a_validar')
        return tabs


admin.site.register(SolicitacaoEntrada, SolicitacaoEntradaAdmin)
