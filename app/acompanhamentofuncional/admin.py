from django.contrib import admin
from django.utils.safestring import mark_safe

from acompanhamentofuncional.forms import AtoAdicionarForm, AtoEditarForm, ServidorCessaoForm
from acompanhamentofuncional.models import Ato, ServidorCessao, TipoAtoConfiguracao
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus

##############################
# Cessão de Servidores
##############################


class ServidorCessaoAdmin(ModelAdminPlus):
    list_display = (
        'servidor_cedido',
        'tipo_exercicio',
        'campus_servidor',
        'instituicao_destino_info',
        'numero_portaria',
        'data_limite_retorno_info',
        'ressarcimento_mensal',
        'status_processo_info',
        'status_prazo_info',
        'dias_restantes_info',
    )
    form = ServidorCessaoForm
    list_display_icons = True
    search_fields = (
        'servidor_cedido__pessoa_fisica__nome',
        'servidor_cedido__matricula',
        'servidor_cedido__setor__uo__sigla',
        'numero_portaria',
        'observacao',
        'instituicao_destino__nome',
    )
    list_filter = (CustomTabListFilter, 'status_processo', 'status_prazo', 'tipo_exercicio', 'servidor_cedido__setor__uo', 'ressarcimento_mensal')
    show_count_on_tabs = True

    def data_limite_retorno_info(self, obj):
        if obj.data_limite_retorno:
            return obj.data_limite_retorno
        else:
            return '-'

    data_limite_retorno_info.short_description = 'Data Limite'
    data_limite_retorno_info.admin_order_field = 'data_limite_retorno'

    def campus_servidor(self, obj):
        return obj.servidor_cedido.setor.uo.sigla if obj.servidor_cedido.setor else 'Sem Setor'

    campus_servidor.short_description = 'Campus'
    campus_servidor.admin_order_field = 'servidor_cedido__setor__uo__sigla'

    def instituicao_destino_info(self, obj):
        if obj.instituicao_destino:
            return obj.instituicao_destino
        else:
            return '-'

    instituicao_destino_info.short_description = 'Instituição de Destino'
    instituicao_destino_info.admin_order_field = 'instituicao_destino'

    def get_tabs(self, request):
        return ['tab_meus_processos']

    def queryset(self, request, manager=None, *args, **kwargs):
        qs = ModelAdminPlus.get_queryset(self, request, manager, *args, **kwargs)
        usuario_logado = request.user
        if not ServidorCessao.is_servidor_rh_sistemico(usuario_logado):
            if ServidorCessao.is_servidor_rh_campus(usuario_logado):
                usuario_logado_campus_sigla = usuario_logado.get_relacionamento().setor.uo.sigla
                qs = qs.filter(servidor_cedido__setor__uo__sigla=usuario_logado_campus_sigla)
            else:
                # o usuário logado "ver" apenas os seus processos
                servidor_logado = usuario_logado.get_relacionamento()
                qs = qs.filter(servidor_cedido=servidor_logado)
        return qs

    def tab_meus_processos(self, request, queryset):
        if request.user.eh_servidor:
            servidor_logado = request.user.get_relacionamento()
            qs = queryset.filter(servidor_cedido=servidor_logado)
            return qs
        return ServidorCessao.objects.none()

    tab_meus_processos.short_description = 'Meus Processos'

    def status_processo_info(self, obj):
        return mark_safe(obj.status_processo_as_html)

    status_processo_info.short_description = 'Situação do Processo'

    def status_prazo_info(self, obj):
        return mark_safe(obj.status_prazo_as_html)

    status_prazo_info.short_description = 'Situação do Prazo'

    def dias_restantes_info(self, obj):
        return mark_safe(obj.dias_restantes_as_html)

    dias_restantes_info.short_description = 'Dias Restantes'


admin.site.register(ServidorCessao, ServidorCessaoAdmin)


#####################################
# Controle de Atos
#####################################


class AtoSituacaoPrazoFilter(admin.SimpleListFilter):
    title = 'Situação quanto ao prazo'
    parameter_name = 'situacao_prazo'

    def lookups(self, request, model_admin):
        return Ato.SITUACAO_PRAZO_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return Ato.get_atos(queryset_inicial=queryset, user_solicitante=request.user, situacao_prazo=self.value())


class AtoAdmin(ModelAdminPlus):
    list_display = ('servidor', 'tipo', 'data_ocorrencia', 'prazo_envio', 'data_limite_envio', 'situacao_envio_display', 'data_envio')
    list_filter = ('servidor', 'situacao_envio', AtoSituacaoPrazoFilter)
    list_display_icons = True
    add_form = AtoAdicionarForm
    change_form = AtoEditarForm

    def situacao_envio_display(self, obj):
        if obj.is_envio_pendente:
            status_class = 'status-pendente'
        else:
            status_class = 'status-resolvido'
        return mark_safe(f'<span class="status status-{status_class}">{obj.get_situacao_envio_display()}</span>')

    situacao_envio_display.short_description = 'Situação de envio'
    situacao_envio_display.admin_order_field = 'situacao_envio'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        return Ato.get_atos(queryset_inicial=queryset, user_solicitante=request.user)


admin.site.register(Ato, AtoAdmin)


class TipoAtoConfiguracaoAdmin(ModelAdminPlus):
    list_display = ('tipo_ato', 'prazo_envio', 'descricao')
    list_display_icons = True


admin.site.register(TipoAtoConfiguracao, TipoAtoConfiguracaoAdmin)
