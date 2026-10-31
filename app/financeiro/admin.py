from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, StackedInlinePlus
from djtools.utils import mask_money
from financeiro.forms import (
    AcaoAnoForm,
    EventoForm,
    NotaCreditoForm,
    NotaCreditoItemForm,
    NotaEmpenhoForm,
    NotaEmpenhoItemForm,
    NotaEmpenhoListaItemForm,
    UnidadeGestoraForm,
)
from financeiro.models import (
    Acao,
    AcaoAno,
    CategoriaApropriacao,
    CategoriaEconomicaDespesa,
    ClassificacaoInstitucional,
    ElementoDespesa,
    EsferaOrcamentaria,
    EspecificacaoFonteRecurso,
    Evento,
    FonteRecurso,
    Funcao,
    GrupoFonteRecurso,
    GrupoNaturezaDespesa,
    IdentificadorResultadoPrimario,
    IdentificadorUso,
    InstrumentoLegal,
    Localizacao,
    ModalidadeAplicacao,
    ModalidadeLicitacao,
    NaturezaDespesa,
    NEItem,
    NEListaItens,
    NotaCredito,
    NotaCreditoItem,
    NotaDotacao,
    NotaDotacaoItem,
    NotaEmpenho,
    NotaSistema,
    PlanoInterno,
    Programa,
    ProgramaTrabalho,
    ProgramaTrabalhoResumido,
    SubElementoNaturezaDespesa,
    Subfuncao,
    UnidadeGestora,
    UnidadeMedida,
)


class SubElementoNaturezaDespesaAdmin(ModelAdminPlus):
    pass


admin.site.register(SubElementoNaturezaDespesa, SubElementoNaturezaDespesaAdmin)


class CategoriaEconomicaDespesaAdmin(ModelAdminPlus):
    pass


admin.site.register(CategoriaEconomicaDespesa, CategoriaEconomicaDespesaAdmin)


class GrupoNaturezaDespesaAdmin(ModelAdminPlus):
    pass


admin.site.register(GrupoNaturezaDespesa, GrupoNaturezaDespesaAdmin)


class ModalidadeAplicacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(ModalidadeAplicacao, ModalidadeAplicacaoAdmin)


class ElementoDespesaAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome', 'descricao')


admin.site.register(ElementoDespesa, ElementoDespesaAdmin)


class NaturezaDespesaAdmin(ModelAdminPlus):
    search_fields = ('codigo', 'nome')


admin.site.register(NaturezaDespesa, NaturezaDespesaAdmin)

# class SubElementoNaturezaDespesaAdmin(admin.ModelAdmin):
#
#    def get_info_natureza_despesa_nome(self, obj):
#        return obj.natureza_despesa.nome
#    get_info_natureza_despesa_nome.short_description = u'Natureza de Despesa'
#    get_info_natureza_despesa_nome.allow_tags = True
#
#    def get_info_rubrica(self, obj):
#        out = [u'<ul>']
#        for rubrica in obj.rubrica_set.all():
#            out.append(u'<li class="disabled">%s: %s</li>' % (rubrica.codigo, rubrica.nome))
#        out.append('</ul>')
#        return ''.join(out)
#    get_info_rubrica.short_description = u'Rubricas desse Subelemento'
#    get_info_rubrica.allow_tags = True
#
#    search_fields = ('codigo', 'natureza_despesa__codigo', 'nome', 'natureza_despesa__nome')
#    ordering = ['codigo']
#    form = FormSubElementoNaturezaDespesa
#    list_display = ('codigo', 'nome', 'get_info_natureza_despesa_nome', 'get_info_rubrica')
#
# admin.site.register(SubElementoNaturezaDespesa, SubElementoNaturezaDespesaAdmin)


class FuncaoAdmin(ModelAdminPlus):
    list_display = (
        'codigo',
        'nome',
    )
    search_fields = (
        'codigo',
        'nome',
    )


admin.site.register(Funcao, FuncaoAdmin)


class SubfuncaoAdmin(ModelAdminPlus):
    list_display = (
        'codigo',
        'nome',
    )
    search_fields = (
        'codigo',
        'nome',
    )


admin.site.register(Subfuncao, SubfuncaoAdmin)


class LocalizacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(Localizacao, LocalizacaoAdmin)


class IdentificadorUsoAdmin(ModelAdminPlus):
    pass


admin.site.register(IdentificadorUso, IdentificadorUsoAdmin)


class IdentificadorRescursoPrimarioAdmin(ModelAdminPlus):
    list_display = (
        'codigo',
        'nome',
    )
    search_fields = (
        'codigo',
        'nome',
    )


admin.site.register(IdentificadorResultadoPrimario, IdentificadorRescursoPrimarioAdmin)


class UnidadeGestoraAdmin(ModelAdminPlus):
    form = UnidadeGestoraForm

    list_display = ('codigo', 'nome', 'mnemonico', 'municipio', 'ativo', 'uo')
    search_fields = ('codigo', 'nome', 'mnemonico')
    list_filter = ('ativo', 'uo')


admin.site.register(UnidadeGestora, UnidadeGestoraAdmin)


class GrupoFonteRecursoAdmin(ModelAdminPlus):
    pass


admin.site.register(GrupoFonteRecurso, GrupoFonteRecursoAdmin)


class EspecificacaoFonteRecursoAdmin(ModelAdminPlus):
    pass


admin.site.register(EspecificacaoFonteRecurso, EspecificacaoFonteRecursoAdmin)


class FonteRecursoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome', 'grupo', 'especificacao')
    search_fields = ('codigo', 'nome')


admin.site.register(FonteRecurso, FonteRecursoAdmin)


class ClassificacaoInstitucionalAdmin(ModelAdminPlus):
    list_display = (
        'codigo',
        'nome',
    )
    search_fields = ('nome',)


admin.site.register(ClassificacaoInstitucional, ClassificacaoInstitucionalAdmin)


class EsferaOrcamentariaAdmin(ModelAdminPlus):
    pass


admin.site.register(EsferaOrcamentaria, EsferaOrcamentariaAdmin)


class InstrumentoLegalAdmin(ModelAdminPlus):
    pass


admin.site.register(InstrumentoLegal, InstrumentoLegalAdmin)


class ModalidadeLicitacaoAdmin(ModelAdminPlus):
    pass


admin.site.register(ModalidadeLicitacao, ModalidadeLicitacaoAdmin)


class NotaSistemaAdmin(ModelAdminPlus):
    list_display = ('numero', 'ug', 'data_emissao', 'sistema_origem')
    list_filter = ('ug', 'sistema_origem')
    date_hierarchy = 'data_emissao'


admin.site.register(NotaSistema, NotaSistemaAdmin)


class NotaEmpenhoListaItemInline(StackedInlinePlus):
    model = NEListaItens


class NotaEmpenhoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('numero', 'emitente_ug', 'natureza_despesa', 'vinculo_favorecido', 'data_emissao', 'qtd_itens', 'valor', 'get_acoes')
    list_filter = (CustomTabListFilter, 'natureza_despesa')
    date_hierarchy = 'data_emissao'
    search_fields = ('numero', 'vinculo_favorecido__pessoa__nome', 'emitente_ug__nome')

    inlines = (NotaEmpenhoListaItemInline,)
    form = NotaEmpenhoForm

    def get_view_inlines(self, request):
        return ['get_itens']

    def get_itens(self, obj):
        return obj.get_itens()

    get_itens.short_description = 'Itens empenhados'
    get_itens.columns = ['numero', 'subitem', 'descricao', 'quantidade', 'valor_unitario', 'valor_total']

    def qtd_itens(self, obj):
        return obj.get_itens().count()

    qtd_itens.short_description = 'Qtd. Itens'

    def get_tabs(self, request):
        return ['get_tab_permanente']

    def get_tab_permanente(self, request, queryset):
        return queryset.filter(natureza_despesa__codigo='449052')

    def get_acoes(self, obj):
        return mark_safe(
            '<a href="/admin/financeiro/nelistaitens/{}" class="btn success">Adicionar item</a>'.format(obj.nelistaitens_set.latest('id').id)
        )

    get_acoes.short_description = 'Ações'

    get_tab_permanente.short_description = 'Material Permanente'


admin.site.register(NotaEmpenho, NotaEmpenhoAdmin)


class NotaEmpenhoItemInline(StackedInlinePlus):
    model = NEItem
    form = NotaEmpenhoItemForm


class NotaEmpenhoListaItemAdmin(ModelAdminPlus):
    inlines = (NotaEmpenhoItemInline,)
    form = NotaEmpenhoListaItemForm


admin.site.register(NEListaItens, NotaEmpenhoListaItemAdmin)


class UnidadeMedidaAdmin(ModelAdminPlus):
    pass


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)


class ProgramaAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome')


admin.site.register(Programa, ProgramaAdmin)


class AcaoAdmin(ModelAdminPlus):
    list_display = ('get_codigo_completo', 'nome')

    fieldsets = ((None, {'fields': ('codigo_acao', 'nome', 'programa')}),)
    list_filter = ('programa__codigo',)
    search_fields = ('codigo_acao',)

    def get_codigo_completo(self, obj):
        return f'{obj.programa.codigo}.{obj.codigo_acao}'

    get_codigo_completo.short_description = 'Código'


admin.site.register(Acao, AcaoAdmin)


class ProgramaTrabalhoAdmin(ModelAdminPlus):
    list_display = ('get_codigo_completo', 'get_acao', 'get_localizacao')

    fieldsets = ((None, {'fields': ('funcao', 'subfuncao', 'acao', 'localizacao', 'municipio')}),)

    def get_codigo_completo(self, obj):
        return f'{obj.funcao.codigo}.{obj.subfuncao.codigo}.{obj.acao.codigo}.{obj.localizacao.codigo}'

    get_codigo_completo.short_description = 'Código'

    def get_acao(self, obj):
        return obj.acao.nome

    get_acao.short_description = 'Ação'

    def get_localizacao(self, obj):
        return obj.localizacao.nome

    get_localizacao.short_description = 'Localização'


admin.site.register(ProgramaTrabalho, ProgramaTrabalhoAdmin)


class ProgramaTrabalhoResumidoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'classificacao_institucional')
    list_filter = ('classificacao_institucional',)


admin.site.register(ProgramaTrabalhoResumido, ProgramaTrabalhoResumidoAdmin)


class PlanoInternoAdmin(ModelAdminPlus):
    pass


admin.site.register(PlanoInterno, PlanoInternoAdmin)


class EventoAdmin(ModelAdminPlus):
    form = EventoForm
    list_display = ('codigo', 'nome', 'descricao', 'tipo', 'ativo')
    search_fields = ('codigo', 'nome', 'descricao')


admin.site.register(Evento, EventoAdmin)


class NotaCreditoItemAdmin(ModelAdminPlus):
    pass


admin.site.register(NotaCreditoItem, NotaCreditoItemAdmin)


class NotaCreditoItemInline(StackedInlinePlus):
    model = NotaCreditoItem
    form = NotaCreditoItemForm


class NotaCreditoAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ['numero', 'emitente_ug', 'favorecido_ug']
    inlines = [NotaCreditoItemInline]
    form = NotaCreditoForm
    date_hierarchy = 'datahora_emissao'
    search_fields = ('emitente_ug__nome',)


admin.site.register(NotaCredito, NotaCreditoAdmin)


class NotaDotacaoAdmin(ModelAdminPlus):
    list_display = ('numero', 'emitente_ug', 'favorecido_ug')


admin.site.register(NotaDotacao, NotaDotacaoAdmin)


class NotaDotacaoItemAdmin(ModelAdminPlus):
    pass


admin.site.register(NotaDotacaoItem, NotaDotacaoItemAdmin)


class AcaoAnoAdmin(ModelAdminPlus):
    list_display = ('ano_base', 'acao', 'ptres', 'show_valor_capital', 'show_valor_custeio', 'get_total')
    list_filter = ('ano_base',)
    form = AcaoAnoForm

    def get_total(self, obj):
        return mask_money(obj.valor_capital + obj.valor_custeio)

    get_total.short_description = 'Total'

    def show_valor_custeio(self, obj):
        if obj.valor_custeio:
            return mark_safe(mask_money(obj.valor_custeio))
        else:
            return '-'

    show_valor_custeio.short_description = 'Valor Custeio'

    def show_valor_capital(self, obj):
        if obj.valor_capital:
            return mark_safe(mask_money(obj.valor_capital))
        else:
            return '-'

    show_valor_capital.short_description = 'Valor Capital'


admin.site.register(AcaoAno, AcaoAnoAdmin)


class CategoriaApropriacaoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao')
    ordering = ['codigo']


admin.site.register(CategoriaApropriacao, CategoriaApropriacaoAdmin)
