from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from almoxarifado.forms import CategoriaMaterialConsumoForm, EmpenhoConsumoForm, EmpenhoForm, MaterialConsumoForm, PlanoContasAlmoxForm
from almoxarifado.models import (
    CategoriaMaterialConsumo,
    Catmat,
    Empenho,
    EmpenhoConsumo,
    MaterialConsumo,
    MovimentoAlmoxEntrada,
    MovimentoAlmoxSaida,
    PlanoContasAlmox,
    UnidadeMedida,
)
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from djtools.utils import httprr


class MovimentoAlmoxEntradaAdmin(ModelAdminPlus):
    list_display = ('id', 'tipo', 'data', 'material', 'qtd', 'estoque', 'uo', 'movimento_saida')
    search_fields = ('material__nome',)


admin.site.register(MovimentoAlmoxEntrada, MovimentoAlmoxEntradaAdmin)


class MovimentoAlmoxSaidaAdmin(ModelAdminPlus):
    list_display = ('id', 'tipo', 'data', 'material', 'qtd', 'uo', 'movimento_entrada')
    search_fields = ('material__nome',)


admin.site.register(MovimentoAlmoxSaida, MovimentoAlmoxSaidaAdmin)


class MaterialConsumoAdmin(ModelAdminPlus):
    list_display = ('codigo_catmat', 'codigo', 'nome', 'categoria', 'unidade', 'total_qtd_empenhada_na_uo', 'estoque_atual_na_uo', 'opcoes')
    list_filter = (CustomTabListFilter, 'categoria')

    search_fields = ('search',)
    list_per_page = 50
    ordering = ('nome',)
    export_to_xls = True
    export_to_csv = True
    list_display_icons = True

    fields = ('catmat', 'categoria', 'unidade', 'nome', 'observacao')

    form = MaterialConsumoForm

    def to_csv(self, request, queryset, processo):
        header = ['#', 'Código', 'Material Consumo', 'Unidade', 'Elemento Despesa', 'Qtd Empenhada no Campus', 'Estoque']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.codigo,
                obj.nome,
                obj.unidade,
                obj.categoria.nome,
                obj.get_total_qtd_empenhada(),
                obj.get_estoque_atual(get_uo(request.user)),
            ]
            rows.append(row)
        return rows

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Código', 'Material Consumo', 'Unidade', 'Elemento Despesa', 'Qtd Empenhada no Campus', 'Estoque']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.codigo,
                obj.nome,
                obj.unidade,
                obj.categoria.nome,
                obj.get_total_qtd_empenhada(get_uo(request.user)),
                obj.get_estoque_atual(get_uo(request.user)),
            ]
            rows.append(row)
        return rows

    def get_tabs(self, request):
        return ['tab_estoque_atual', 'tab_estoque_passado', 'tab_estoque_futuro']

    def tab_estoque_atual(self, request, queryset):
        return queryset.com_estoque_por_uo(get_uo(request.user))

    tab_estoque_atual.short_description = 'Estoque Atual'

    # teve estoque em meu campus
    def tab_estoque_passado(self, request, queryset):
        return queryset.teve_estoque_por_uo(get_uo(request.user))

    tab_estoque_passado.short_description = 'Estoque Passado'

    def tab_estoque_futuro(self, request, queryset):
        return queryset.com_qtd_empenhada_estoque_por_uo(get_uo(request.user))

    tab_estoque_futuro.short_description = 'Estoque Futuro'

    def opcoes(self, obj):
        return mark_safe(f'<a href="/almoxarifado/material_historico/{obj.pk}/" class="btn default">Histórico de Movimentação</a>')

    opcoes.short_description = 'Opções'
    opcoes.attrs = {'class': 'no-print'}

    def estoque_atual_na_uo(self, obj):
        return obj.get_estoque_atual(get_uo())

    estoque_atual_na_uo.short_description = 'Estoque'

    def total_qtd_empenhada_na_uo(self, obj):
        return obj.get_total_qtd_empenhada(get_uo())

    total_qtd_empenhada_na_uo.short_description = 'Qtd Empenhada no campus'

    def codigo_catmat(self, obj):
        return obj.catmat.codigo if obj.catmat else '-'

    codigo_catmat.short_description = 'CATMAT'
    codigo_catmat.admin_order_field = 'catmat__codigo'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        url_base = '/almoxarifado/gerar_etiquetas/' + '?' + request.GET.urlencode()
        items.append({'url': url_base, 'label': 'Gerar Etiquetas'})
        return items


admin.site.register(MaterialConsumo, MaterialConsumoAdmin)


class CategoriaMaterialConsumoAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'plano_contas')
    search_fields = ('nome', 'codigo')
    list_display_icons = True
    ordering = ('codigo',)

    form = CategoriaMaterialConsumoForm

    def get_fieldsets(self, request, obj=None):
        return super().get_fieldsets(request, obj)


admin.site.register(CategoriaMaterialConsumo, CategoriaMaterialConsumoAdmin)


class UnidadeMedidaAdmin(ModelAdminPlus):
    pass


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)


class EmpenhoConsumoAdmin(ModelAdminPlus):
    form = EmpenhoConsumoForm

    def response_change(self, request, obj):
        self.message_user(request, 'Item alterado com sucesso.')
        return HttpResponseRedirect(obj.empenho.get_absolute_url())


admin.site.register(EmpenhoConsumo, EmpenhoConsumoAdmin)


class EmpenhoAdmin(ModelAdminPlus):
    form = EmpenhoForm
    list_per_page = 20
    fieldsets = (
        ('Dados Principais', {'fields': (('uo', 'numero'), 'processo', 'tipo_material')}),
        ('Fornecedor', {'fields': ('tipo_pessoa', 'pessoa_fisica', 'pessoa_juridica', 'data_recebimento_empenho', 'prazo')}),
        ('Outros Dados', {'fields': (('tipo_licitacao', 'numero_pregao'), 'observacao')}),
    )

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(f'/almoxarifado/empenho/{obj.pk}/')

    def response_change(self, request, obj):
        return HttpResponseRedirect(f'/almoxarifado/empenho/{obj.pk}/')

    def delete_view(self, request, object_id, extra_context=None):
        empenho = Empenho.objects.filter(pk=object_id).first() if str(object_id).isdigit() else None
        if empenho and not empenho.can_delete():
            return httprr(empenho.get_absolute_url(), 'Impossível remover o empenho: os itens sofreram movimentações.', 'error')

        response = super().delete_view(request, object_id, extra_context)
        #         sobrescrevendo o redirect
        if isinstance(response, HttpResponseRedirect):
            return HttpResponseRedirect('/almoxarifado/empenhos/')

        return response


admin.site.register(Empenho, EmpenhoAdmin)


class PlanoContasAdmin(ModelAdminPlus):
    form = PlanoContasAlmoxForm
    search_fields = ('codigo', 'descricao')
    list_display = ('codigo', 'descricao', 'ativo', 'data_desativacao')
    ordering = ('codigo',)
    list_display_icons = True

    def get_fieldsets(self, request, obj=None):
        if in_group(request.user, ['Contador Sistêmico, Contador Administrador']):
            return super().get_fieldsets(request, obj)
        return [(None, {'fields': ('codigo', 'descricao')})]


admin.site.register(PlanoContasAlmox, PlanoContasAdmin)


class CatmatAdmin(ModelAdminPlus):
    list_display = ('codigo', 'descricao')
    search_fields = ('codigo', 'descricao')
    list_display_icons = True
    ordering = ('codigo',)


admin.site.register(Catmat, CatmatAdmin)
