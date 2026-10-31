from django.contrib import admin
from django.db.models.expressions import Q
from django.template.defaultfilters import slugify
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import httprr
from protocolo.forms import ProcessoFormCadastrarComTramite
from protocolo.models import Processo, TempoAnalise, TempoTramite


class OrigemProcessoListFilter(admin.SimpleListFilter):
    title = 'Origem do Processo'
    parameter_name = 'origem_processo'

    def lookups(self, request, model_admin):
        return ((None, 'Todos'), ('eletronico', 'Eletrônico'), ('fisico', 'Físico'))

    def queryset(self, request, queryset):
        if self.value():
            q_ = Q(numero_processo_eletronico__isnull=True) if self.value() == 'fisico' else Q(numero_processo_eletronico__isnull=False)
            queryset = queryset.filter(q_)
        return queryset


class ProcessoAdmin(ModelAdminPlus):
    form = ProcessoFormCadastrarComTramite
    list_display = (
        'show_numero',
        'assunto',
        'show_nome_interessado',
        'data_cadastro',
        'show_status',
        'get_descricao_orgao_atual',
        'get_descricao_responsavel_atual',
    )
    change_form_template = 'protocolo/templates/admin/protocolo/processo/change_form.html'
    list_filter = (CustomTabListFilter, 'status', 'uo', OrigemProcessoListFilter)
    list_per_page = 20
    list_display_icons = True
    ordering = ['-id']
    date_hierarchy = 'data_cadastro'
    export_to_xls = True

    def get_fieldsets(self, request, obj=None):
        fields = [
            'interessado_nome',
            'interessado_documento',
            'interessado_pf',
            'interessado_email',
            'interessado_telefone',
            'numero_documento',
            'assunto',
            'tipo',
            'palavras_chave',
        ]
        if not obj:  # Editando um processo que já existe não deve mandar o tramimete
            fields += ['tipo_encaminhamento_primeira_tramitacao']
        return [(None, {'fields': fields})]

    def response_add(self, request, obj):
        msg = f'{obj._meta.verbose_name.capitalize()} "{obj!s}" cadastrado com sucesso.'

        if request.POST['tipo_encaminhamento_primeira_tramitacao'] == 'interno':
            return httprr(f'/protocolo/processo_encaminhar_primeiro_tramite/{obj.id}/interno/', msg)
        if request.POST['tipo_encaminhamento_primeira_tramitacao'] == 'externo':
            return httprr(f'/protocolo/processo_encaminhar_primeiro_tramite/{obj.id}/externo/', msg)
        else:
            return httprr(f'{obj.get_absolute_url()}')

    def add_view(self, request, form_url='', extra_context=None):
        if not extra_context:
            extra_context = {}
        extra_context['get_uo'] = get_uo(request.user)
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if not extra_context:
            extra_context = {}
        extra_context['get_uo'] = get_uo(request.user)
        return super().change_view(request, object_id, form_url, extra_context)

    def show_numero(self, obj):
        return mark_safe(f'<span class="text-nowrap">{obj.numero_processo}</span>')

    show_numero.admin_order_field = 'numero_processo'
    show_numero.short_description = 'Número'

    def show_status(self, obj):
        if obj.tem_vinculo_com_processo_eletronico:
            return '(Processo Eletrônico)'
        else:
            return mark_safe(f'<span class="status status-{slugify(obj.get_status_display())}">{obj.get_status_display()}</span>')

    show_status.admin_order_field = 'status'
    show_status.short_description = 'Situação'

    def show_nome_interessado(self, obj):
        return obj.interessado_nome

    show_nome_interessado.admin_order_field = 'interessado_nome'
    show_nome_interessado.short_description = 'Pessoa Interessada'

    def get_descricao_responsavel_atual(self, obj):
        if obj.tem_vinculo_com_processo_eletronico:
            return '(Processo Eletrônico)'
        else:
            if obj.get_vinculo_responsavel_atual() is not None:
                return mark_safe(obj.get_vinculo_responsavel_atual().pessoa.nome)
            else:
                return '(Ninguém até o momento)'

    get_descricao_responsavel_atual.short_description = 'Responsável atual'

    def get_descricao_orgao_atual(self, obj):
        if obj.tem_vinculo_com_processo_eletronico:
            return '(Processo Eletrônico)'
        else:
            if obj.get_orgao_responsavel_atual() is not None:
                return mark_safe(obj.get_orgao_responsavel_atual())
            else:
                return '(Nenhum)'

    get_descricao_orgao_atual.short_description = 'Setor atual'

    def get_tabs(self, request):
        return request.user.has_perm('protocolo.pode_tramitar_processo') and ['tab_meus_processos'] or []

    def tab_meus_processos(self, request, queryset):
        return queryset.da_pessoafisica(request.user.get_profile()).order_by('-data_cadastro')

    tab_meus_processos.short_description = 'Meus Processos'

    def has_add_permission(self, request):
        return super().has_add_permission(request) and Configuracao.get_valor_por_chave('protocolo', 'habilitar_cadastro_manual')

    def has_change_permission(self, request, obj=None):
        if not Configuracao.get_valor_por_chave('protocolo', 'habilitar_cadastro_manual'):
            return False
        if obj and not obj.pode_editar_processo(request.user):
            return False
        return super().has_change_permission(request, obj)

    def get_queryset(self, request):
        numero_processo_busca = request.GET.get('q')
        if numero_processo_busca:
            numero_processo_busca = Processo.get_numero_formatado_from_texto_busca(numero_processo_busca)
            request.GET._mutable = True
            request.GET['q'] = numero_processo_busca
            request.GET._mutable = False

        if request.user.has_perm('protocolo.pode_tramitar_processo'):
            return super().get_queryset(request)
        else:
            return super().get_queryset(request).da_pessoafisica(request.user.get_profile()).order_by('-data_cadastro')


admin.site.register(Processo, ProcessoAdmin)


class TempoTramiteAdmin(ModelAdminPlus):
    search_fields = ['uo_origem__codigo_ug', 'uo_origem__cidade', 'uo_destino__codigo_ug', 'uo_destino__cidade']
    list_display = ('uo_origem', 'uo_destino', 'tempo_maximo')


admin.site.register(TempoTramite, TempoTramiteAdmin)


class TempoAnaliseAdmin(ModelAdminPlus):
    search_fields = ['setor__sigla', 'setor__nome', 'setor__codigo']
    list_display = ('setor', 'tempo_maximo')


admin.site.register(TempoAnalise, TempoAnaliseAdmin)
