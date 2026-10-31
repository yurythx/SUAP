from django.contrib import admin
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import httprr, permission_required, rtr
from materiais.forms import MaterialFormFactory
from materiais.models import Categoria, CategoriaDescritor, Material, MaterialTag, Requisicao, UnidadeMedida


class RequisicaoAdmin(ModelAdminPlus):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('materiais.add_material'):
            return qs
        else:
            return qs.filter(usuario_solicitante=request.user)

    def show_pk(self, obj):
        return mark_safe(f'<a href="/materiais/requisicao/{obj.pk}/">{obj.pk}</a>')

    show_pk.short_description = 'ID'

    list_display = ['show_pk', 'status', 'usuario_solicitante', 'requerimento']
    list_filter = ['status']
    list_display_links = []
    fields = ['requerimento']


admin.site.register(Requisicao, RequisicaoAdmin)


class MaterialTagAdmin(ModelAdminPlus):
    pass


admin.site.register(MaterialTag, MaterialTagAdmin)


class UnidadeMedidaAdmin(ModelAdminPlus):
    pass


admin.site.register(UnidadeMedida, UnidadeMedidaAdmin)


class CategoriaDescritorInline(admin.TabularInline):
    model = CategoriaDescritor
    extra = 3


class CategoriaAdmin(ModelAdminPlus):
    list_display = ['codigo_completo', 'descricao', 'sub_elemento_nd', 'validade']
    list_filter = ['sub_elemento_nd', 'sub_elemento_nd__natureza_despesa']
    search_fields = ['descricao', 'codigo_completo']
    inlines = [CategoriaDescritorInline]


admin.site.register(Categoria, CategoriaAdmin)


class MaterialAdmin(ModelAdminPlus):
    list_display = ('id', 'categoria', 'codigo_catmat', 'descricao', 'show_especificacao_e_descritores', 'show_acoes')
    list_display_icons = True
    list_filter = (CustomTabListFilter, 'categoria', 'tags')
    search_fields = ('descricao', 'especificacao', 'codigo_catmat')
    export_to_xls = True
    show_count_on_tabs = True

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('<int:material_pk>/', permission_required('materiais.change_material')(self.admin_site.admin_view(self.material_cadastrar_editar))),
            path('add/', permission_required('materiais.change_material')(self.admin_site.admin_view(self.material_cadastrar_editar))),
        ]
        return my_urls + urls

    @rtr()
    def material_cadastrar_editar(self, request, material_pk=None):
        title = 'Adicionar Material'
        instance = None
        args = {}
        if material_pk:  # edição
            material = Material.objects.get(pk=material_pk)
            args = {'material': material}
            instance = material

        elif 'categoria' in request.GET:  # cadastro
            args = {'categoria': Categoria.objects.get(pk=request.GET['categoria'])}

        FormClass = MaterialFormFactory(**args)
        form = FormClass(request.POST or None, instance=instance)

        if form.is_valid():
            form.save()
            return httprr(f'/admin/materiais/material/{form.instance.pk}/', 'Material adicionado com sucesso.')

        return locals()

    def show_acoes(self, obj):
        return mark_safe(
            f'<ul class=action-bar><li><a href="/materiais/materialcotacao/{obj.id}/" class="btn success" title=u"Adicionar Cotação">Adicionar Cotação</a></li> <li><a href="/materiais/visualizar_materialcotacoes/{obj.id}/" class="btn" title=u"Gerenciar Cotações">Gerenciar Cotações</a></li></ul>'
        )

    show_acoes.short_description = 'Opções'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        items.append({'url': '/admin/materiais/requisicao/add/', 'label': 'Requisitar Cadastro de Material'})
        return items

    def show_especificacao_e_descritores(self, obj):
        descritores = []
        for d in obj.materialdescritor_set.all():
            descritores.append(f'{d.categoria_descritor.descricao}: {d.descricao}')

        cotacoes = []
        for c in obj.materialcotacao_set.all():
            cotacoes.append(f'<span>{c.valor}</span>')

        return mark_safe(
            '{}<br/><br/><i style="color: #666">{}</i><br/><b>Cotações: </b><i>{}</i>'.format(
                obj.especificacao, '| '.join(descritores), ', '.join(cotacoes)
            )
        )

    def get_tabs(self, request):
        return ['tab_ativos', 'tab_inativos', 'tab_any_data']

    def tab_ativos(self, request, queryset):
        return queryset.filter(ativo=True)

    tab_ativos.short_description = 'Ativos'

    def tab_inativos(self, request, queryset):
        return queryset.filter(ativo=False)

    tab_inativos.short_description = 'Inativos'

    def to_xls(self, request, queryset, processo):
        header = ['ID', 'Categoria', 'CATMAT', 'Descrição', 'Especificação', 'Unidade de Medida', 'Qtd. Cotações', 'Ativo']
        rows = [header]
        for m in processo.iterate(queryset):
            row = [m.id, m.categoria, m.codigo_catmat, m.descricao, m.especificacao, m.unidade_medida, m.materialcotacao_set.count(), m.ativo]
            rows.append(row)
        return rows

    show_especificacao_e_descritores.admin_order_field = 'especificacao'
    show_especificacao_e_descritores.short_description = 'Especificação e Descritores'


admin.site.register(Material, MaterialAdmin)
