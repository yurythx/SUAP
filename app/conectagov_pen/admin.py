from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon

from .forms import MapeamentoTiposDocumentoForm, TipoDocumentoPENForm
from .models import DocumentoProcessoBarramento, HipoteseLegalPEN, MapeamentoTiposDocumento, ProcessoBarramento, TipoDocumentoPEN, TramiteBarramento


class TipoDocumentoPENAdmin(ModelAdminPlus):
    list_display = ('nome', 'observacao')
    search_fields = ('nome',)
    list_display_icons = True
    form = TipoDocumentoPENForm


admin.site.register(TipoDocumentoPEN, TipoDocumentoPENAdmin)


class MapeamentoTiposDocumentoAdmin(ModelAdminPlus):
    list_display = ('get_tipo_doc_suap', 'get_tipo_doc_barramento_pen')
    search_fields = ('tipo_doc_suap__nome', 'tipo_doc_suap__nome')
    list_display_icons = True
    form = MapeamentoTiposDocumentoForm

    def get_tipo_doc_suap(self, obj):
        return obj.tipo_doc_suap.nome

    def get_tipo_doc_barramento_pen(self, obj):
        return obj.tipo_doc_barramento_pen.nome


admin.site.register(MapeamentoTiposDocumento, MapeamentoTiposDocumentoAdmin)


class TramiteBarramentoAdmin(ModelAdminPlus):
    list_display = (
        'remetente_externo_estrutura_descricao',
        'destinatario_externo_estrutura_descricao',
        'data_hora_encaminhamento',
        'status',
        'retorno_situacao',
        'get_nre',
        'get_processo',
        'get_criado_no_suap',
        'id_tramite_barramento',
        'get_hashs_documentos_recebidos',
    )
    search_fields = (
        'processo_barramento__nre_barramento_pen',
        'processo_barramento__processo__numero_protocolo',
        'processo_barramento__processo__numero_protocolo_fisico',
    )
    list_filter = ('status', 'processo_barramento__processo', 'data_hora_encaminhamento')
    list_display_icons = False
    list_display_links = None

    actions_on_top = False
    actions_on_bottom = False

    def get_processo(self, obj):
        if obj.processo_barramento.processo:
            return mark_safe(
                f'<a href="{obj.processo_barramento.processo.get_absolute_url()} " target="_blank">{obj.processo_barramento.processo}</a>'
            )
        return '-'

    get_processo.allow_tags = True
    get_processo.short_description = 'Processo'

    def get_nre(self, obj):
        return obj.processo_barramento.nre_barramento_pen

    get_nre.short_description = 'NRE Barramento'

    def get_criado_no_suap(self, obj):
        return 'Sim' if obj.processo_barramento.criado_no_suap else 'Não'

    get_criado_no_suap.short_description = 'Gerado no SUAP'
    # get_criado_no_suap.boolean = True

    def get_hashs_documentos_recebidos(self, obj):
        lista = ['<ul>']
        if obj.componentes_digitais_a_receber:
            for hash_componente in obj.componentes_digitais_a_receber:
                lista.append(f'<li>{hash_componente}</li>')
        else:
            lista.append('-')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_hashs_documentos_recebidos.short_description = 'Hash dos Componentes Recebidos/A Receber'

    def has_add_permission(self, request):
        return False

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/conectagov_pen/processar_pendencias/', 'label': 'Processar Trâmites Externos Pendentes', 'css_class': 'success'})
        return items

    def show_list_display_icons(self, obj):
        out = []
        out.append(icon('view', obj.get_absolute_url()))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = 'Ações'


admin.site.register(TramiteBarramento, TramiteBarramentoAdmin)


class HipoteseLegalPENAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'status', 'get_descricao_hipotese_suap', 'hipotese_padrao')
    search_fields = ('nome', 'descricao', 'status')
    list_display_icons = True

    actions_on_top = True
    actions_on_bottom = False

    def get_descricao_hipotese_suap(self, obj):
        return obj.hipotese_legal_suap.descricao if obj.hipotese_legal_suap else ''

    get_descricao_hipotese_suap.short_description = 'Hipótese Relacionada - SUAP'

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        items.append({'url': '/conectagov_pen/importar_hipoteses_legais_pen/', 'label': 'Importar Hipóteses Legais do PEN', 'css_class': 'success'})
        items.append({'url': '/conectagov_pen/definir_hipotese_padrao_pen/', 'label': 'Definir Hipótese Legal Padrão do PEN', 'css_class': 'primary'})
        return items


admin.site.register(HipoteseLegalPEN, HipoteseLegalPENAdmin)

admin.site.register(ProcessoBarramento)

admin.site.register(DocumentoProcessoBarramento)
