# -------------------------------------------------------------------------------
# IFRN - Instituto Federal de Educação, Ciência e Tecnologia
# DGTI - Diretoria de Gestão da Tecnologia da Informação
# -------------------------------------------------------------------------------
# SUAP - Sistema único de Administração Pública
# -------------------------------------------------------------------------------
# Aplicativo: Orçamento
# Autor.....: José Augusto de Medeiros
# Descrição.: Aplicativo para controle do orçamento do instituto.
# -------------------------------------------------------------------------------
# Observações:
#      Termos utilizados no módulo:
#         - MTO: Manual Técnico do Orçamento
# -------------------------------------------------------------------------------

from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from djtools.utils import mask_money
from orcamento.forms import EstruturaProgramaticaFinanceiraForm
from orcamento.models import Credito, EstruturaProgramaticaFinanceira, UnidadeMedida


class EstruturaProgramaticaFinanceiraAdmin(ModelAdminPlus):
    form = EstruturaProgramaticaFinanceiraForm
    list_display = ('get_codigo_pt', 'get_programa_trabalho', 'get_unidade_medida', 'get_quantidade', 'ano_base')

    def get_unidade_medida(self, obj):
        if obj.unidade_medida:
            return obj.unidade_medida
        else:
            return '-'

    get_unidade_medida.short_description = 'Unidade de Medida'

    def get_quantidade(self, obj):
        if obj.quantidade:
            return obj.quantidade
        else:
            return '-'

    get_quantidade.short_description = 'Quantidade'

    def get_codigo_pt(self, obj):
        return obj.programa_trabalho

    get_codigo_pt.short_description = 'Código'

    def get_programa_trabalho(self, obj):
        return obj.programa_trabalho.acao.nome

    get_programa_trabalho.short_description = 'Programa de Trabalho'


admin.site.register(EstruturaProgramaticaFinanceira, EstruturaProgramaticaFinanceiraAdmin)


class CreditoAdmin(ModelAdminPlus):
    list_display = ('get_credito', 'get_epf', 'get_despesa', 'get_recurso', 'get_valor')

    def get_credito(self, obj):
        return f'{obj.epf.ano_base.ano}.{obj.epf.programa_trabalho.acao.codigo}.{obj.natureza_despesa.codigo}.{obj.fonte_recurso.codigo}'

    get_credito.short_description = 'Código'

    def get_epf(self, obj):
        return obj.epf

    get_epf.short_description = 'Estrutura Programática Financeira'

    def get_despesa(self, obj):
        return obj.natureza_despesa.codigo

    get_despesa.short_description = 'Natureza de Despesa'

    def get_recurso(self, obj):
        return obj.fonte_recurso.codigo

    get_recurso.short_description = 'Fonte de Recurso'

    def get_valor(self, obj):
        return mask_money(obj.valor)

    get_valor.short_description = 'Valor'


admin.site.register(Credito, CreditoAdmin)


class UnidadeMedidaAdmin(ModelAdminPlus):
    pass


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)

# -------------------------------------------------------------------------------
# from django import forms
# from django.contrib import admin
# from djtools.utils import mask_money
# from forms import AnoBaseForm, FonteRecursoForm, ProgramaForm
# from models import NaturezaDespesa, CategoriaEconomicaDespesa, \
#    GrupoNaturezaDespesa, ModalidadeAplicacao, ElementoDespesa, AnoBase, Programa, \
#    GrupoFonteRecurso, EspecificacaoFonteRecurso, FonteRecurso
# from orcamento.forms import AcaoForm, EstruturaProgramaticaFinanceiraForm, \
#    UnidadeMedidaForm
# from orcamento.models import Acao, EstruturaProgramaticaFinanceira, \
#    UnidadeMedida

# -------------------------------------------------------------------------------
#
# ------------------------------------------------------------------------------
# class AnoBaseAdmin(admin.ModelAdmin):
#    form = AnoBaseForm
#    search_fields = ('ano',)
#    list_display = ('icone_editar','ano',)
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(AnoBase, AnoBaseAdmin)
#
# class CategoriaEconomicaDespesaAdmin(admin.ModelAdmin):
#    search_fields = ('descricao',)
#    list_display = ('icone_editar', 'codigo','descricao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(CategoriaEconomicaDespesa, CategoriaEconomicaDespesaAdmin)
#
# class ElementoDespesaAdmin(admin.ModelAdmin):
#    search_fields = ('descricao',)
#    list_display = ('icone_editar', 'codigo','descricao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#
# admin.site.register(ElementoDespesa, ElementoDespesaAdmin)
#
# class GrupoNaturezaDespesaAdmin(admin.ModelAdmin):
#    search_fields = ('descricao',)
#    list_display = ('icone_editar', 'codigo','descricao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(GrupoNaturezaDespesa, GrupoNaturezaDespesaAdmin)
#
# class ModalidadeAplicacaoAdmin(admin.ModelAdmin):
#    search_fields = ('descricao',)
#    list_display = ('icone_editar', 'codigo','descricao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(ModalidadeAplicacao, ModalidadeAplicacaoAdmin)
#
# class NaturezaDespesaAdmin(admin.ModelAdmin):
#    exclude = ('codigo_resumo',)
#    search_fields = ('descricao',)
#    list_display = ('icone_editar', 'codigo_resumo', 'descricao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(NaturezaDespesa, NaturezaDespesaAdmin)
#
# class GrupoFonteRecursoAdmin(admin.ModelAdmin):
#    search_fields = ('grupo',)
#    list_display = ('icone_editar', 'codigo','grupo')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#
# admin.site.register(GrupoFonteRecurso, GrupoFonteRecursoAdmin)
#
# class EspecificacaoFonteRecursoAdmin(admin.ModelAdmin):
#    search_fields = ('especificacao',)
#    list_display = ('icone_editar', 'codigo','especificacao')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#
# admin.site.register(EspecificacaoFonteRecurso, EspecificacaoFonteRecursoAdmin)
#
# class FonteRecursoAdmin(admin.ModelAdmin):
#    form = FonteRecursoForm
#
#    search_fields = ('programa',)
#    list_display = ('icone_editar','codigo','descricao')
#
#    fieldsets = [
#                 (None, {'fields': ('grupo', 'especificacao', 'descricao'
#                                   )}),
#                ]
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(FonteRecurso, FonteRecursoAdmin)
#
# class ProgramaAdmin(admin.ModelAdmin):
#    form = ProgramaForm
#    search_fields = ('codigo','nome',)
#    list_display = ('icone_editar', 'codigo','nome',)
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(Programa, ProgramaAdmin)
#
# -------------------------------------------------------------------------------
# class UnidadeMedidaAdmin(admin.ModelAdmin):
#    form = UnidadeMedidaForm
#
#    search_fields = ('descricao',)
#    list_display = ('icone_editar','descricao',)
#    ordering = ('descricao',)
#
#    def icone_editar(self, obj):
#        return 'Editar' % dict(pk=obj.pk)
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)
#
# -------------------------------------------------------------------------------
# class AcaoAdmin(admin.ModelAdmin):
#    form = AcaoForm
#    search_fields = ('codigo','nome',)
#    list_display = ('icone_editar', 'codigo_completo', 'nome', 'participa_planejamento')
#    ordering = ('nome',)
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
# admin.site.register(Acao, AcaoAdmin)
#
# -------------------------------------------------------------------------------
# class EstruturaProgramaticaFinanceiraAdmin(admin.ModelAdmin):
#    form = EstruturaProgramaticaFinanceiraForm
#    list_display = ('icone_editar', 'icone_descentralizar', '__str__', 'acao_nome', 'natureza_despesa_descricao', 'fonte_recurso_descricao', 'show_valor')
#
#    def icone_editar(self, obj):
#        return 'Editar'
#    icone_editar.allow_tags = True
#    icone_editar.short_description = ''
#    icone_editar.attrs = {'width': '18px'}
#
#    def icone_descentralizar(self, obj):
#        return '<a href="/orcamento/descentralizar/%s/" class="btn">Descentralizar</a>'%(obj.pk)
#    icone_descentralizar.allow_tags = True
#    icone_descentralizar.short_description = ''
#    icone_descentralizar.attrs = {'width': '18px'}
#
#    def acao_nome(self, obj):
#        return '%s' % (obj.acao.nome)
#    acao_nome.allow_tags = True
#    acao_nome.short_description = 'Ação'
#
#    def natureza_despesa_descricao(self, obj):
#        return obj.natureza_despesa.descricao
#    natureza_despesa_descricao.allow_tags = True
#    natureza_despesa_descricao.short_description = 'Natureza de Despesa'
#
#    def fonte_recurso_descricao(self, obj):
#        return obj.fonte_recurso.descricao
#    fonte_recurso_descricao.allow_tags = True
#    fonte_recurso_descricao.short_description = 'Fonte de Recurso'
#
#    def show_valor(self, obj):
#        if obj.valor:
#            return mask_money(obj.valor)
#        else:
#            return u'-'
#    show_valor.allow_tags = True
#    show_valor.short_description = 'Valor'
#
# admin.site.register(EstruturaProgramaticaFinanceira, EstruturaProgramaticaFinanceiraAdmin)
