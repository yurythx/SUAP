from abc import ABCMeta, abstractmethod

from django.contrib import admin
from django.contrib.admin import SimpleListFilter

from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_money
from tesouro_gerencial.models import (
    GRU,
    RAP,
    AcaoGoverno,
    ClassificacaoInstitucional,
    DocumentoEmpenho,
    DocumentoEmpenhoEspecifico,
    DocumentoEmpenhoItem,
    DocumentoLiquidacao,
    DocumentoLiquidacaoItem,
    DocumentoPagamento,
    DocumentoPagamentoItem,
    EsferaOrcamentaria,
    FonteRecurso,
    HistoricoImportacao,
    Importacao,
    NaturezaDespesa,
    NotaCredito,
    NotaCreditoItem,
    NotaDotacao,
    NotaDotacaoItem,
    PlanoInterno,
    ProgramaTrabalhoResumido,
    RAPItem,
    ReceitaGRU,
    SubElementoNaturezaDespesa,
    TipoDocumentoEmpenhoEspecifico,
    UnidadeGestora,
)

admin.site.register(ClassificacaoInstitucional)
admin.site.register(EsferaOrcamentaria)
admin.site.register(AcaoGoverno)
admin.site.register(ProgramaTrabalhoResumido)
admin.site.register(PlanoInterno)
admin.site.register(FonteRecurso)
admin.site.register(NaturezaDespesa)
admin.site.register(SubElementoNaturezaDespesa)
admin.site.register(GRU)


@admin.register(UnidadeGestora)
class UnidadeGestoraAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('codigo', 'nome', 'uo')
    search_fields = ('codigo', 'nome')
    list_filter = ('uo',)


class SimpleListFilterExclude(SimpleListFilter, metaclass=ABCMeta):
    @abstractmethod
    def get_model(self):
        return

    @abstractmethod
    def get_filter(self):
        return

    def lookups(self, request, model_admin):
        return [(item.codigo, str(item)) for item in self.get_model().objects.order_by('codigo')]

    def queryset(self, request, queryset):
        if self.value():
            args = {self.get_filter(): self.value()}
            return queryset.exclude(**args)


class UnidadeOrcamentariaExclude(SimpleListFilterExclude):
    title = 'Unidade Orçamentaria(exceto)'
    parameter_name = 'unidade_orcamentaria_exclude'

    def get_model(self):
        return ClassificacaoInstitucional

    def get_filter(self):
        return 'unidade_orcamentaria__codigo'


class AcaoGovernoExclude(SimpleListFilterExclude):
    title = 'Ação Governo(exceto)'
    parameter_name = 'acao_governo_exclude'

    def get_model(self):
        return AcaoGoverno

    def get_filter(self):
        return 'acao_governo_original'


class NaturesaDespesaExclude(SimpleListFilterExclude):
    title = 'Naturesa de Despesa(exceto)'
    parameter_name = 'naturesa_despesa_exclude'

    def get_model(self):
        return NaturezaDespesa

    def get_filter(self):
        return 'naturesa_despesa_original'


class FonteRecursoExclude(SimpleListFilterExclude):
    title = 'Fonte de Recurso(exceto)'
    parameter_name = 'fonte_recurso_exclude'

    def get_model(self):
        return FonteRecurso

    def get_filter(self):
        return 'fonte_recurso_original'


@admin.register(TipoDocumentoEmpenhoEspecifico)
class TipoDocumentoEmpenhoEspecificoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    list_display = ('descricao', 'aplicar_calculo')
    search_fields = ['descricao']


@admin.register(DocumentoEmpenhoEspecifico)
class DocumentoEmpenhoEspecificoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    list_display = ('documento_empenho', 'tipo', 'observacao')
    search_fields = ['documento_empenho__numero']


@admin.register(RAP)
class RAPAdmin(ModelAdminPlus):
    search_fields = ['numero']
    export_to_xls = True
    list_display_icons = False
    list_display_links = None
    list_display = (
        'numero',
        'ano',
        'unidade_orcamentaria',
        'acao_governo_original',
        'fonte_recurso_original',
        'naturesa_despesa_original',
        'grupo_despesa_original',
        'get_subitem_original',
        'get_valor',
    )
    list_filter = (
        'ano',
        'responsavel_ug',
        'unidade_orcamentaria',
        'acao_governo',
        'naturesa_despesa_original',
        'grupo_despesa_original',
        UnidadeOrcamentariaExclude,
        AcaoGovernoExclude,
        NaturesaDespesaExclude,
        FonteRecursoExclude,
    )
    show_count_on_tabs = True

    def get_valor(self, obj):
        return f'R$ {format_money(obj.get_valor())}'

    get_valor.short_description = 'valor'

    def get_subitem_original(self, obj):
        return ', '.join(obj.itens.values_list('subitem_original', flat=True))

    get_subitem_original.short_description = 'SubItem'


@admin.register(RAPItem)
class RAPItemAdmin(ModelAdminPlus):
    search_fields = ['rap__numero']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'rap',
        'subitem',
        'valor_proc_inscrito',
        'valor_proc_reinscrito',
        'valor_proc_cancelado',
        'valor_proc_pago',
        'valor_nao_proc_inscrito',
        'valor_nao_proc_reinscrito',
        'valor_nao_proc_cancelado',
        'valor_nao_proc_liquidado',
        'valor_nao_proc_pago',
    )
    list_filter = (
        'rap',
        'subitem',
    )


@admin.register(ReceitaGRU)
class ReceitaGRUAdmin(ModelAdminPlus):
    export_to_xls = True
    list_display_icons = False
    list_display_links = None
    list_display = ('gru', 'ano', 'emitente_ug', 'get_valor')
    list_filter = ('ano', 'gru', 'emitente_ug')
    show_count_on_tabs = True

    def get_valor(self, obj):
        return f'R$ {format_money(obj.get_valor())}'

    get_valor.short_description = 'valor'


class DocumentoAdmin(ModelAdminPlus):
    search_fields = ['numero']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'numero',
        'data_emissao',
        'unidade_orcamentaria',
        'acao_governo_original',
        'fonte_recurso_original',
        'naturesa_despesa_original',
        'grupo_despesa_original',
        'get_subitem_original',
        'get_valor',
    )
    list_filter = (
        'tipo',
        'responsavel_ug',
        'unidade_orcamentaria',
        'acao_governo',
        'naturesa_despesa_original',
        'grupo_despesa_original',
        UnidadeOrcamentariaExclude,
        AcaoGovernoExclude,
        NaturesaDespesaExclude,
        FonteRecursoExclude,
    )
    show_count_on_tabs = True
    date_hierarchy = 'data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.get_valor())}'

    get_valor.short_description = 'valor'

    def get_subitem_original(self, obj):
        return ', '.join(obj.itens.values_list('subitem_original', flat=True))

    get_subitem_original.short_description = 'SubItem'


@admin.register(DocumentoEmpenho)
class DocumentoEmpenhoAdmin(DocumentoAdmin):
    search_fields = ['numero', 'documento_empenho_inicial__numero']


@admin.register(DocumentoEmpenhoItem)
class DocumentoEmpenhoItemAdmin(ModelAdminPlus):
    search_fields = ['documento_empenho__numero', 'documento_empenho__documento_empenho_inicial__numero', 'valor']
    export_to_xls = True
    list_display_icons = False
    list_display = ('get_documento_empenho_inicial', 'documento_empenho', 'subitem', 'get_valor', 'subitem_original', 'evento')
    list_filter = (
        'documento_empenho__documento_empenho_inicial',
        'documento_empenho',
        'subitem',
    )
    show_count_on_tabs = True
    date_hierarchy = 'documento_empenho__data_emissao'

    def get_documento_empenho_inicial(self, obj):
        return obj.documento_empenho.documento_empenho_inicial

    get_documento_empenho_inicial.short_description = 'Documento Empenho Inicial'
    get_documento_empenho_inicial.admin_order_field = 'documento_empenho__documento_empenho_inicial__numero'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.valor)}'

    get_valor.short_description = 'Valor'
    get_valor.admin_order_field = 'valor'


admin.site.register(DocumentoLiquidacao, DocumentoAdmin)


@admin.register(DocumentoLiquidacaoItem)
class DocumentoLiquidacaoItemAdmin(ModelAdminPlus):
    search_fields = ['documento_empenho_inicial__numero', 'documento_liquidacao__numero', 'valor']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'documento_empenho_inicial',
        'documento_liquidacao',
        'subitem',
        'evento',
        'get_valor',
        'subitem_original',
    )
    list_filter = (
        'documento_empenho_inicial',
        'documento_liquidacao',
        'subitem',
        'evento',
    )
    show_count_on_tabs = True
    date_hierarchy = 'documento_liquidacao__data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.valor)}'

    get_valor.short_description = 'Valor'
    get_valor.admin_order_field = 'valor'


admin.site.register(DocumentoPagamento, DocumentoAdmin)


@admin.register(DocumentoPagamentoItem)
class DocumentoPagamentoItemAdmin(ModelAdminPlus):
    search_fields = ['documento_empenho_inicial__numero', 'documento_pagamento__numero', 'valor']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'documento_empenho_inicial',
        'documento_pagamento',
        'subitem',
        'get_valor',
        'subitem_original',
    )
    list_filter = (
        'documento_empenho_inicial',
        'documento_pagamento',
        'subitem',
    )
    show_count_on_tabs = True
    date_hierarchy = 'documento_pagamento__data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.valor)}'

    get_valor.short_description = 'Valor'
    get_valor.admin_order_field = 'valor'


@admin.register(HistoricoImportacao)
class HistoricoImportacaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    list_display = ('data',)
    date_hierarchy = 'data'


@admin.register(Importacao)
class ImportacaoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display_links = None
    list_display = ('data_email', 'assunto_email', 'tipo', 'qtd')
    search_fields = ('assunto_email', 'tipo')
    date_hierarchy = 'data_email'


@admin.register(NotaCredito)
class NotaCreditoAdmin(ModelAdminPlus):
    search_fields = ['numero']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'numero',
        'data_emissao',
        'conta_contabil',
        'unidade_orcamentaria',
        'emitente_ci',
        'emitente_ug',
        'favorecido_ug',
        'get_valor',
    )
    list_filter = (
        'conta_contabil',
        'unidade_orcamentaria',
        'emitente_ci',
        'emitente_ug',
        'favorecido_ug',
    )
    show_count_on_tabs = True
    date_hierarchy = 'data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.get_valor())}'

    get_valor.short_description = 'valor'


@admin.register(NotaCreditoItem)
class NotaCreditoItemAdmin(ModelAdminPlus):
    search_fields = ['nota_credito__numero', 'valor']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'nota_credito',
        'ptres',
        'plano_interno',
        'get_valor',
    )
    list_filter = (
        'nota_credito',
        'esfera_orcamentaria',
        'acao_governo',
        'responsavel_ug',
        'ptres',
        'plano_interno',
        'fonte_recurso',
        'subitem',
    )
    show_count_on_tabs = True
    date_hierarchy = 'nota_credito__data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.valor)}'

    get_valor.short_description = 'Valor'
    get_valor.admin_order_field = 'valor'


@admin.register(NotaDotacao)
class NotaDotacaoAdmin(ModelAdminPlus):
    search_fields = ['numero']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'numero',
        'executora_ug',
        'data_emissao',
        'observacao',
        'especie',
        'acao_governo',
        'ptres',
        'grupo_despesa_original',
        'fonte_recurso',
        'get_valor',
    )
    list_filter = (
        'executora_ug',
        'acao_governo',
        'ptres',
        'fonte_recurso',
    )
    show_count_on_tabs = True
    date_hierarchy = 'data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.get_valor())}'

    get_valor.short_description = 'valor'


@admin.register(NotaDotacaoItem)
class NotaDotacaoItemAdmin(ModelAdminPlus):
    search_fields = ['nota_dotacao__numero', 'valor']
    export_to_xls = True
    list_display_icons = False
    list_display = (
        'nota_dotacao',
        'responsavel_ug',
        'detalhamento',
        'evento',
        'plano_interno',
        'get_valor',
        'get_valor_liquido',
    )
    list_filter = (
        'nota_dotacao',
        'responsavel_ug',
        'evento',
        'plano_interno',
    )
    show_count_on_tabs = True
    date_hierarchy = 'nota_dotacao__data_emissao'

    def get_valor(self, obj):
        return f'R$ {format_money(obj.valor)}'

    get_valor.short_description = 'Valor'
    get_valor.admin_order_field = 'valor'

    def get_valor_liquido(self, obj):
        return f'R$ {format_money(obj.valor_liquido)}'

    get_valor_liquido.short_description = 'Valor'
    get_valor_liquido.admin_order_field = 'valor'
