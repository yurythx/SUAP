from datetime import datetime

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, F, Q
from django.db.models.fields.related import ManyToManyField
from django.http.response import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.template.defaultfilters import safe
from django.urls import path
from django.utils.safestring import mark_safe

from djtools.assincrono import task
from djtools.contrib.admin import ModelAdminPlus
from djtools.db.models import ManyToManyFieldPlus
from djtools.utils import httprr, render, rtr
from rh.models import UnidadeOrganizacional
from siads.forms import (
    AssociarGrupoForm,
    AssociarGrupoPermanenteForm,
    CampusForm,
    GerarSetorSiadsForm,
    GrupoAtualizarNomeForm,
    MaterialPermanenteForm,
    MaterialPermanenteSiadsForm,
    SetorSiadsForm,
    TipoSetorSiadsForm,
)
from siads.models import (
    GrupoMaterialConsumo,
    GrupoMaterialPermanente,
    MaterialConsumo,
    MaterialConsumoSiads,
    MaterialPermanente,
    MaterialPermanenteSiads,
    SetorSiads,
)
from siads.utils import FIM_LINHA, add_delimitador, trim


class StatisticaFilter(SimpleListFilter):
    title = 'Estatística'
    parameter_name = 'item'

    def lookups(self, request, model_admin):
        return (
            ('TODOS_VALIDADOS', 'Todos os itens validados'),
            ('PARCIALMENTE_VALIDADOS', 'Algum item a validar'),
            ('ZERADOS', 'Sem items associados'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'TODOS_VALIDADOS':
            queryset = queryset.filter(total=F('validados'), total__gt=0)
        elif self.value() == 'PARCIALMENTE_VALIDADOS':
            queryset = queryset.filter(total__gt=F('validados'))
        elif self.value() == 'ZERADOS':
            queryset = queryset.filter(total=0)
        return queryset


class GrupoMaterialConsumoAdmin(ModelAdminPlus):
    list_display = ('nome', 'unidade', 'get_statistica', 'opcoes')
    list_filter = ('unidade', StatisticaFilter)
    search_fields = ('nome',)

    list_display_icons = True

    def get_statistica(self, obj):
        return safe(f'<strong>{obj.validados}</strong>/{obj.total}')

    get_statistica.short_description = 'Estatistica'

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = qs.annotate(total=Count('materialconsumo'), validados=Count('materialconsumo', filter=Q(materialconsumo__validado=True)))
        return qs

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('avaliar/<int:grupo_id>/', self.url_wrap(self.avaliar), name='siads_grupo_avaliar'),
            path('avaliar/<int:material_id>/novo/', self.url_wrap(self.novo_grupo), name='siads_grupo_novo'),
            path('avaliar/<int:grupo_id>/associar/', self.url_wrap(self.associar_grupo), name='siads_grupo_associar'),
            path('atualizar/<int:grupo_id>/grupo/', self.url_wrap(self.atualizar_grupo), name='siads_grupo_atualizar'),
        ]
        return my_urls + urls

    def opcoes(self, obj):
        return mark_safe(f'<a href="/admin/siads/grupomaterialconsumo/avaliar/{obj.pk}/" class="btn default">Avaliar</a>')

    opcoes.short_description = 'Opções'
    opcoes.attrs = {'class': 'no-print'}

    @rtr()
    def avaliar(self, request, grupo_id):
        title = 'Avaliação de Materiais'

        grupo = get_object_or_404(GrupoMaterialConsumo, pk=grupo_id)

        if request.POST:
            if 'novo_grupo' in request.POST:
                if 'material' in request.POST:
                    request.session['materiais'] = request.POST.getlist('material')
                    return redirect(f'/admin/siads/grupomaterialconsumo/avaliar/{grupo_id}/associar/')
                else:
                    messages.error(request, 'Deve-se selecionar pelo menos um material.')
            else:
                for mat in request.POST.getlist('material'):
                    mat_consumo = MaterialConsumo.objects.get(pk=mat)
                    mat_consumo.validado = True
                    mat_consumo.save()

        materiais = MaterialConsumo.objects.filter(grupo=grupo)

        return locals()

    @rtr()
    def associar_grupo(self, request, grupo_id):
        title = 'Associar Grupo'

        grupo = get_object_or_404(GrupoMaterialConsumo, pk=grupo_id)
        grupos = GrupoMaterialConsumo.objects.exclude(pk=grupo_id).order_by('nome')
        materiais = MaterialConsumo.objects.filter(pk__in=request.session.get('materiais', [0]))

        form = AssociarGrupoForm(request.POST or None, grupos=grupos)

        if form.is_valid():
            novo_grupo = form.cleaned_data['grupos']
            if materiais:
                for material in materiais:
                    material.grupo = novo_grupo
                    material.validado = True
                    material.save()
                del request.session['materiais']
                messages.success(request, 'O novo grupo foi associado aos materiais.')
            else:
                messages.error(request, 'Nenhum material encontrado.')
            return redirect(f'/admin/siads/grupomaterialconsumo/avaliar/{grupo_id}/')

        return locals()

    def novo_grupo(self, request, material_id):
        material = get_object_or_404(MaterialConsumo, pk=material_id)
        grupo_anterior = material.grupo

        grupo = GrupoMaterialConsumo()
        grupo.nome = material.nome_original
        grupo.sentenca = material.nome_processado
        grupo.unidade = material.material.unidade is not None and material.material.unidade.nome or ''
        grupo.save()

        material.grupo = grupo
        material.validado = True
        material.save()

        return httprr(f'/admin/siads/grupomaterialconsumo/avaliar/{grupo_anterior.pk}/', 'Novo grupo criado.')

    @rtr()
    def atualizar_grupo(self, request, grupo_id):
        title = 'Atualizar Nome do Grupo'

        grupo = get_object_or_404(GrupoMaterialConsumo, pk=grupo_id)

        form = GrupoAtualizarNomeForm(request.POST or None, instance=grupo)

        if form.is_valid():
            grupo.nome = form.cleaned_data['nome']
            grupo.save()
            return httprr('..', 'O nome do grupo foi atualizado.')

        return locals()


admin.site.register(GrupoMaterialConsumo, GrupoMaterialConsumoAdmin)


class MaterialConsumoAdmin(admin.ModelAdmin):
    pass


admin.site.register(MaterialConsumo, MaterialConsumoAdmin)


class GrupoMaterialPermanenteAdmin(ModelAdminPlus):
    list_display = ('id', 'uo', 'nome', 'get_statistica', 'opcoes')
    list_filter = (
        'uo',
        StatisticaFilter,
    )
    search_fields = (
        'id',
        'nome',
    )

    list_display_icons = True

    def get_statistica(self, obj):
        return safe(f'<strong>{obj.validados}</strong>/{obj.total}')

    get_statistica.short_description = 'Estatistica'

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        qs = qs.annotate(total=Count('materialpermanente'), validados=Count('materialpermanente', filter=Q(materialpermanente__validado=True)))
        return qs

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('avaliar/<int:grupo_id>/', self.url_wrap(self.avaliar), name='siads_grupo_avaliar'),
            path('avaliar/<int:material_id>/novo/', self.url_wrap(self.novo_grupo), name='siads_grupo_novo'),
            path('avaliar/<int:grupo_id>/associar/', self.url_wrap(self.associar_grupo), name='siads_grupo_associar'),
            path('atualizar/<int:grupo_id>/grupo/', self.url_wrap(self.atualizar_grupo), name='siads_grupo_atualizar'),
        ]
        return my_urls + urls

    def opcoes(self, obj):
        return mark_safe(f'<a href="/admin/siads/grupomaterialpermanente/avaliar/{obj.pk}/" class="btn default">Avaliar</a>')

    opcoes.short_description = 'Opções'
    opcoes.attrs = {'class': 'no-print'}

    @rtr('avaliar_permanente.html')
    def avaliar(self, request, grupo_id):
        title = 'Avaliação de Materiais'

        grupo = get_object_or_404(GrupoMaterialPermanente, pk=grupo_id)

        if request.POST:
            if 'novo_grupo' in request.POST:
                if 'material' in request.POST:
                    request.session['materiais'] = request.POST.getlist('material')
                    return redirect(f'/admin/siads/grupomaterialpermanente/avaliar/{grupo_id}/associar/')
                else:
                    messages.error(request, 'Deve-se selecionar pelo menos um material.')
            else:
                mat_pks = request.POST.getlist('material')
                for mat in mat_pks:
                    mat_permanente = MaterialPermanente.objects.get(pk=mat)
                    for outro in MaterialPermanente.objects.filter(uo=mat_permanente.uo, nome_original=mat_permanente.nome_original).exclude(
                        pk__in=mat_pks
                    ):
                        outro.grupo = mat_permanente.grupo
                        outro.validado = True
                        outro.save()
                    mat_permanente.validado = True
                    mat_permanente.save()

        materiais = MaterialPermanente.objects.filter(grupo=grupo)

        return locals()

    @rtr('siads/associar_grupo_permanente.html')
    def associar_grupo(self, request, grupo_id):
        title = 'Associar Grupo'

        grupo = get_object_or_404(GrupoMaterialPermanente, pk=grupo_id)
        grupos = GrupoMaterialPermanente.objects.exclude(pk=grupo_id).order_by('nome')
        materiais = MaterialPermanente.objects.filter(pk__in=request.session.get('materiais', [0]))

        form = AssociarGrupoPermanenteForm(request.POST or None, grupos=grupos)

        if form.is_valid():
            novo_grupo = form.cleaned_data['grupos']
            if materiais:
                for material in materiais:
                    material.grupo = novo_grupo
                    material.validado = True
                    material.save()
                del request.session['materiais']
                messages.success(request, 'O novo grupo foi associado aos materiais.')
            else:
                messages.error(request, 'Nenhum material encontrado.')
            return redirect(f'/admin/siads/grupomaterialpermanente/avaliar/{grupo_id}/')

        return locals()

    def novo_grupo(self, request, material_id):
        material = get_object_or_404(MaterialPermanente, pk=material_id)
        grupo_anterior = material.grupo

        grupo = GrupoMaterialPermanente()
        grupo.nome = material.nome_original
        grupo.sentenca = material.nome_processado
        grupo.uo = material.uo
        grupo.save()

        material.grupo = grupo
        material.validado = True
        material.save()

        return httprr(f'/admin/siads/grupomaterialpermanente/avaliar/{grupo_anterior.pk}/', 'Novo grupo criado.')

    @rtr()
    def atualizar_grupo(self, request, grupo_id):
        title = 'Atualizar Nome do Grupo'

        grupo = get_object_or_404(GrupoMaterialPermanente, pk=grupo_id)

        form = GrupoAtualizarNomeForm(request.POST or None, instance=grupo)

        if form.is_valid():
            grupo.nome = form.cleaned_data['nome']
            grupo.save()
            return httprr('..', 'O nome do grupo foi atualizado.')

        return locals()


admin.site.register(GrupoMaterialPermanente, GrupoMaterialPermanenteAdmin)


class MaterialPermanenteAdmin(ModelAdminPlus):
    list_display = ('uo', 'grupo', 'get_entrada_descricao', 'get_extras', 'get_ajuste')
    list_filter = ('uo',)

    list_display_icons = True

    @admin.display(ordering='entrada__descricao')
    def get_entrada_descricao(self, obj):
        ret = []
        ret.append('<div>')
        ret.append(f'<div>{obj.entrada.descricao}</div>')
        ret.append(f'<span><a class="btn default" href="/almoxarifado/entrada/{obj.entrada.entrada_id}/">Acessar</a></span>')
        ret.append('</div>')
        return safe(''.join(ret))

    get_entrada_descricao.short_description = 'Entrada'

    def get_extras(self, obj):
        data = []
        data.append('<dl>')
        data.append(f'<dt>Marca</dt><dd>{obj.marca}</dd>')
        data.append(f'<dt>Modelo</dt><dd>{obj.modelo}</dd>')
        data.append(f'<dt>Fabricante</dt><dd>{obj.fabricante}</dd>')
        data.append('</dl>')
        return safe(''.join(data))

    get_extras.short_description = 'Outras Informações'

    def get_ajuste(self, obj):
        url_params = self.request.get_full_path().split('?')
        if len(url_params) > 1:
            self.request.session['filter_list'] = url_params[1]
        return safe(f'<a class="btn primary" href="/admin/siads/materialpermanente/{obj.id}/ajuste/">Ajuste</a>')

    get_ajuste.short_description = 'Ação'

    def get_list_display(self, request):
        list_display = super().get_list_display(request)

        if not request.user.has_perm('siads_pode_ajustar_permanente'):
            list_display = (item for item in list_display if item != 'get_ajuste')

        return list_display

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('<str:obj_pk>/ajuste/', self.url_wrap(self.ajuste), name='siads_materialpermanente_ajuste'),
        ]
        return my_urls + urls

    def ajuste(self, request, obj_pk):
        if not request.user.has_perm('siads_pode_ajustar_permanente'):
            raise HttpResponseForbidden('Você não tem permissão para acessar essa tela.')

        title = 'Ajuste na Entrada'
        material = get_object_or_404(MaterialPermanente, id=obj_pk)

        form = MaterialPermanenteForm(request.POST or None, instance=material)

        if form.is_valid():
            form.save()
            messages.success(request, 'Os ajustes foram salvos.')
            url_params = request.session.get('filter_list', '')

            if url_params != '':
                del request.session['filter_list']
                request.session.modified = True
                url_params = '?' + url_params

            return redirect(f'/admin/siads/materialpermanente/{url_params}')

        return render('material_permanente_form.html', ctx={'title': title, 'material': material, 'form': form}, request=request)


admin.site.register(MaterialPermanente, MaterialPermanenteAdmin)


class SetorUoFilter(SimpleListFilter):
    title = 'UO'
    parameter_name = 'item'

    def lookups(self, request, model_admin):
        uos = UnidadeOrganizacional.objects.filter(tipo__isnull=False)
        uos = uos.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)

        choices = ((uo.id, uo.sigla) for uo in uos)

        return choices

    def queryset(self, request, queryset):
        if self.value():
            queryset = queryset.filter(uo=self.value())
        return queryset


class SemSIORG(SimpleListFilter):
    title = 'Código SIORG'
    parameter_name = 'codigo_siorg'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'SIORG Preenchido'),
            ('SEM', 'SIORG não Preenchido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(uorg='')
        elif self.value() == 'SEM':
            queryset = queryset.filter(uorg='')
        return queryset


class FiltroSIORG(SimpleListFilter):
    title = 'Código SIORG'
    parameter_name = 'codigo_siorg'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'SIORG Preenchido'),
            ('SEM', 'SIORG não Preenchido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(uorg='')
        elif self.value() == 'SEM':
            queryset = queryset.filter(uorg='')
        return queryset


class FiltroChefe(SimpleListFilter):
    title = 'Chefia'
    parameter_name = 'chefe'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Chefe Definido'),
            ('SEM', 'Chefe não Definido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.filter(chefe__isnull=False)
        elif self.value() == 'SEM':
            queryset = queryset.filter(chefe__isnull=True)
        return queryset


class FiltroMunicipio(SimpleListFilter):
    title = 'Municipio'
    parameter_name = 'municipio'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Município Definido'),
            ('SEM', 'Município não Definido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(municipio='')
        elif self.value() == 'SEM':
            queryset = queryset.filter(municipio='')
        return queryset


class FiltroTelefone(SimpleListFilter):
    title = 'Telefone'
    parameter_name = 'telefone'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Telefone Definido'),
            ('SEM', 'Telefone não Definido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(telefone='')
        elif self.value() == 'SEM':
            queryset = queryset.filter(telefone='')
        return queryset


class FiltroNomeReduzido(SimpleListFilter):
    title = 'Nome Reduzido'
    parameter_name = 'nome_reduzido'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Nome Reduzido Definido'),
            ('SEM', 'Nome Reduzido não Definido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(nome_reduzido='')
        elif self.value() == 'SEM':
            queryset = queryset.filter(nome_reduzido='')
        return queryset


class SetorSiadsAdmin(ModelAdminPlus):
    list_display = ('tipo', 'uorg', 'uo', 'sigla', 'nome', 'nome_reduzido', 'chefe', 'exportavel', 'ajustado', 'opcoes')
    list_filter = ('tipo', SetorUoFilter, FiltroSIORG, FiltroChefe, FiltroMunicipio, FiltroTelefone, FiltroNomeReduzido, 'ajustado')
    list_display_icons = True

    actions = ['mark_ajustado', 'unmark_ajustado']

    export_to_xls = True
    form = SetorSiadsForm

    fieldsets_sala = (
        (None, {'fields': ('sala', 'setor_suap', 'nome', 'ajustado')}),
        (
            'Dados gerais',
            {
                'fields': ('chefe', 'uorg', 'sigla', 'nome_reduzido'),
            },
        ),
        (
            'Dados de Endereço',
            {
                'fields': ('cep', 'endereco', 'sigla_uf', 'municipio'),
            },
        ),
        (
            'Dados de Telefone',
            {
                'fields': ('ddd', 'telefone', 'ramal'),
            },
        ),
    )

    fieldsets_setor = (
        (None, {'fields': ('setor_suap', 'nome', 'ajustado')}),
        (
            'Dados gerais',
            {
                'fields': ('chefe', 'uorg', 'sigla', 'nome_reduzido'),
            },
        ),
        (
            'Dados de Endereço',
            {
                'fields': ('cep', 'endereco', 'sigla_uf', 'municipio'),
            },
        ),
        (
            'Dados de Telefone',
            {
                'fields': ('ddd', 'telefone', 'ramal'),
            },
        ),
    )

    @admin.action(description='Marcar como ajustado')
    def mark_ajustado(self, request, queryset):
        updated = queryset.update(ajustado=True)
        self.message_user(request, f'Foram ajustados {updated} registros.')

    @admin.action(description='Marcar como não ajustado')
    def unmark_ajustado(self, request, queryset):
        updated = queryset.update(ajustado=False)
        self.message_user(request, f'Foram marcados como não ajustados {updated} registros.')

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        qs = qs.select_related('uo', 'setor_suap', 'sala', 'chefe')
        return qs

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Tipo',
            'Campus',
            'Setor',
            'Sala',
            'Chefe',
            'Código da UORG',
            'Código da UG Vínculada',
            'Nome da UORG',
            'Sigla da UORG',
            'Endereço da UORG',
            'CEP da UORG',
            'DDD da UORG',
            'Telefone da UORG',
            'Ramal da UORG',
            'CPF do responsável',
            'Nome do responsável',
            'Matrícula do responsável',
            'Portaria de nomeação',
            'Código da UORG Subordinada',
            'Nome reduzido',
            'Data da criação',
            'Doc. de criação',
            'Sigla da UF',
            'Município',
            'E-mail',
            'Exportável',
            'Ajustado',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                obj.tipo,
                obj.uo,
                obj.setor_suap,
                obj.sala,
                obj.chefe,
                obj.uorg,
                obj.ug_vinvulada,
                obj.nome,
                obj.sigla,
                obj.endereco,
                obj.cep,
                obj.ddd,
                obj.telefone,
                obj.ramal,
                obj.cpf_responsavel,
                obj.nome_responsavel,
                obj.matricula_siape,
                obj.portaria,
                obj.uorg_subordinada,
                obj.nome_reduzido,
                obj.data_criacao,
                obj.numero_doc_criacao,
                obj.sigla_uf,
                obj.municipio,
                obj.email,
                obj.exportavel,
                obj.ajustado,
            ]

            rows.append(row)

        return rows

    def get_setor_ou_sala(self, obj):
        tipo = 'Setor'
        if obj.sala is not None:
            tipo = 'Sala'
        return tipo

    get_setor_ou_sala.short_description = 'Tipo'

    def get_telefone(self, obj):
        if obj.telefone == '':
            return '-'
        return f'({obj.ddd}) {obj.telefone} - {obj.ramal}'

    get_telefone.short_description = 'Telefone'

    def get_fieldsets(self, request, obj=None):
        if not obj or obj.sala is not None:
            return self.fieldsets_sala
        return self.fieldsets_setor

    def get_view_obj_items(self, obj, safe=None):
        is_safe = safe

        def _get_fieldsets(self):
            fields = [f.name for f in obj.__class__._meta.fields if f.name != 'id']
            return (('', {'fields': (fields,)}),)

        fieldsets = _get_fieldsets(self)
        max_fields_by_row = 1
        for _fieldset_name, fieldset_dict in fieldsets:
            for item in fieldset_dict['fields']:
                if isinstance(item, str):
                    continue
                if len(item) > max_fields_by_row:
                    max_fields_by_row = len(item)

        items = []
        for fieldset_name, fieldset_dict in fieldsets:
            item_dict = {'fieldset': fieldset_name, 'rows': []}
            for fieldset_fields_item in fieldset_dict['fields']:
                if isinstance(fieldset_fields_item, str):
                    fieldset_fields_item = [fieldset_fields_item]
                fields = []
                for field_name in fieldset_fields_item:
                    last_field_in_row = field_name == fieldset_fields_item[-1]
                    if last_field_in_row:
                        colspan = (max_fields_by_row - len(fieldset_fields_item)) * 2 + 1
                    else:
                        colspan = 1
                    try:
                        model_field = self.model._meta.get_field(field_name)
                        if hasattr(obj, f'get_{field_name}_display'):
                            valor = getattr(obj, f'get_{field_name}_display')
                        elif type(model_field) in [ManyToManyField, ManyToManyFieldPlus]:
                            valor = getattr(obj, field_name).all()
                            is_safe = True
                        else:
                            valor = getattr(obj, field_name)
                            is_safe = False

                        field_dict = {'label': model_field.verbose_name, 'value': valor, 'colspan': colspan, 'is_safe': is_safe}
                        fields.append(field_dict)
                    except Exception:
                        pass
                item_dict['rows'].append(fields)
            items.append(item_dict)
        return items

    def opcoes(self, obj):
        lst_opcoes = []

        if obj.exportavel:
            lst_opcoes.append({'link': f'/admin/siads/setorsiads/{obj.id}/set/nao_exportar/', 'titulo': 'Não Exportar', 'css': 'danger'})
        else:
            lst_opcoes.append({'link': f'/admin/siads/setorsiads/{obj.id}/set/exportar/', 'titulo': 'Exportar', 'css': 'success'})

        ret = []
        ret.append('<ul class="action-bar">')
        for item in lst_opcoes:
            link = item['link']
            titulo = item['titulo']
            css = item['css']
            ret.append(f'<li><a href="{link}" class="btn {css}">{titulo}</a></li>')
        ret.append('</ul>')

        return mark_safe('\n'.join(ret))

    opcoes.short_description = 'Opções'
    opcoes.attrs = {'class': 'no-print'}

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        if self.has_add_permission(request):
            items.append({'url': '/admin/siads/setorsiads/processar/dados/', 'label': 'Processar Dados', 'css_class': ''})
            items.append({'url': '/admin/siads/setorsiads/gerar/arquivo/', 'label': 'Gerar Arquivo', 'css_class': 'primary'})
        return items

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('<str:obj_pk>/set/nao_exportar/', self.url_wrap(self.set_exportar), {'export': False}, name='siads_setor_nao_exportar'),
            path('<str:obj_pk>/set/exportar/', self.url_wrap(self.set_exportar), name='siads_setor_exportar'),
            path('processar/dados/', self.url_wrap(self.processar_dados_form), name='siads_setor_processar_arquivos_form'),
            path('processar/dados/<str:tipo>/', self.url_wrap(self.processar_dados), name='siads_setor_processar_arquivos'),
            path('gerar/arquivo/', self.url_wrap(self.gerar_arquivos_form), name='siads_setor_gerar_arquivo_form'),
            path('gerar/arquivo/<str:uo_id>/<str:uasg>/', self.url_wrap(self.gerar_arquivos), name='siads_setor_gerar_arquivo'),
        ]
        return my_urls + urls

    def set_exportar(self, request, obj_pk, export=True):
        setor_siads = get_object_or_404(SetorSiads, id=obj_pk)
        setor_siads.exportavel = export
        setor_siads.save()

        messages.success(request, 'A operação foi realizada.')
        return redirect('/admin/siads/setorsiads/')

    def processar_dados_form(self, request):
        title = 'Processar Dados de Setor e Sala'

        form = TipoSetorSiadsForm(request.POST or None)

        if form.is_valid():
            tipo = form.cleaned_data['tipo']
            return redirect(f'/admin/siads/setorsiads/processar/dados/{tipo}/')

        return render('default.html', ctx={'title': title, 'form': form}, request=request)

    @task('Processar Setores', method='thread')
    def processar_dados(self, request, tipo, task=None):
        new_itens, total_itens, error_itens = SetorSiads.processar(tipo, task)

        messages.info(request, f'Foram processados {total_itens} itens.')
        messages.info(request, f'Foram processados {new_itens} novos itens.')
        messages.error(request, f'Foram foram encontrados {len(error_itens)} itens com erro.')

        task.finalize('Processamento Finalizado.')
        return redirect('/admin/siads/setorsiads/')

    def gerar_arquivos_form(self, request):
        title = 'Gerar arquivo Setor e Sala'

        form = GerarSetorSiadsForm(request.POST or None)

        if form.is_valid():
            uo_id = form.cleaned_data['uo'].id
            uasg = form.cleaned_data['uasg']
            return redirect(f'/admin/siads/setorsiads/gerar/arquivo/{uo_id}/{uasg}/')

        return render('default.html', ctx={'title': title, 'form': form}, request=request)

    def gerar_arquivos(self, request, uo_id, uasg, task=None):
        def cabecalho(fd, uasg):
            dados = []

            # Montagem do registro
            dados.append('H')  # Identificador da linha
            dados.append('UO')  # Tipo do Arquivo
            dados.append('1')  # Sequencial que identifica o número do arquivo
            dados.append('25000')  # Código do órgão implantador
            dados.append(uasg)  # Código da UASG - '170531'
            dados.append('03063892408')  # CPF do usuário que gerou o arquivo
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)

            fd.write(f'{row}\n')

        def rodape(fd, registros):
            now = datetime.now()

            dados = []

            # Montagem do registro
            dados.append('T')  # Identificador da linha
            dados.append(now.strftime('%d%m%Y%H%M%S'))  # Data Final
            dados.append(str(registros))  # Quantidade de Registros
            dados.append('FIM')  # Identificador de fim de arquivo
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        def add_registro(setor, fd):
            dados = []

            # Montagem do registro
            dados.append('D')  # Identificador da linha
            dados.append(trim(setor.uorg, 100))  # Código da UORG - A(100)
            dados.append(trim(setor.ug_vinvulada, 6))  # Código da UG Vinculada - N(6)
            dados.append(trim(setor.nome, 100))  # Nome da UORG - A(100)
            dados.append(trim(setor.sigla, 16))  # Sigla da UORG - A(16)
            dados.append(trim(setor.endereco, 60))  # Endereço da UORG - A(60)
            dados.append(trim(setor.cep, 8))  # CEP da UORG - A(8)
            dados.append(trim(setor.ddd, 4))  # DDD da UORG - A(4)
            dados.append(trim(setor.telefone, 8))  # Telefone da UORG - A(8)
            dados.append(trim(setor.ramal, 4))  # Ramal da UORG - A(4)
            dados.append(trim('', 14))  # Fax da UORG - A(14)
            dados.append(trim(setor.cpf_responsavel, 11))  # CPF do Responsável pela UORG - N(11)
            dados.append(trim(setor.nome_responsavel, 40))  # Nome do Responsável pela UORG - A(40)
            dados.append(trim(setor.matricula_siape, 12))  # Matrícula SIAPE do Responsável pela UORG - N(12)
            dados.append(trim(setor.portaria, 25))  # Número da Portaria de Nomeação do responsável pela UORG - A(25)
            dados.append(trim(setor.uorg_subordinada, 100))  # Código da UORG Subordinada - A(100)
            dados.append(trim(setor.nome_reduzido, 40))  # Nome Reduzido - A(40)
            dados.append(trim(setor.data_criacao, 8))  # Data da Criação (DDMMYYYY) - N(8)
            dados.append(trim(setor.numero_doc_criacao, 60))  # Número do Documento de Criação - A(60)
            dados.append(trim(setor.sigla_uf, 2))  # Sigla da UF - A(2)
            dados.append(trim(setor.municipio, 40))  # Municipio - A(40)
            dados.append(trim(setor.email, 50))  # E-Mail - A(50)
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        # ----------------------------------------------------------------------
        uo = get_object_or_404(UnidadeOrganizacional, id=uo_id)
        response = HttpResponse(content_type='application/text charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="uorgs.txt"'

        cabecalho(fd=response, uasg=uasg)

        setores = SetorSiads.objects.filter(uo=uo, exportavel=True)
        registros = 0

        for setor in setores:
            add_registro(setor=setor, fd=response)
            registros += 1

        rodape(registros=registros, fd=response)

        return response


admin.site.register(SetorSiads, SetorSiadsAdmin)


class FiltroContaContabil(SimpleListFilter):
    title = 'Conta Contábil'
    parameter_name = 'conta_contabil'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Conta Definida'),
            ('SEM', 'Conta não Definida'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(codigo_conta='999999999')
        elif self.value() == 'SEM':
            queryset = queryset.filter(codigo_conta='999999999')
        return queryset


class FiltroEndereco(SimpleListFilter):
    title = 'Endereço'
    parameter_name = 'endereco'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Endereço Definido'),
            ('SEM', 'Endereço não Definido'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(endereco='ZZ')
        elif self.value() == 'SEM':
            queryset = queryset.filter(endereco='ZZ')
        return queryset


class MaterialConsumoSiadsAdmin(ModelAdminPlus):
    list_display = ('uo', 'codigo_material', 'descricao', 'unidade_medida', 'codigo_conta', 'endereco', 'qtd_disponivel', 'valor_saldo')
    list_filter = ('uo', FiltroContaContabil, FiltroEndereco)

    list_display_icons = True

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': '/admin/siads/materialconsumosiads/processar/dados/', 'label': 'Processar Dados', 'css_class': ''})
            items.append({'url': '/admin/siads/materialconsumosiads/gerar/arquivo/form/', 'label': 'Gerar Arquivo', 'css_class': 'primary'})
        return items

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('processar/dados/', self.url_wrap(self.processar_dados), name='siads_materialconsumosiads_processar_arquivos'),
            path('gerar/arquivo/form/', self.url_wrap(self.gerar_arquivos_form), name='siads_materialconsumosiads_gerar_arquivo_form'),
            path('gerar/arquivo/<int:obj_pk>/', self.url_wrap(self.gerar_arquivos), name='siads_materialconsumosiads_gerar_arquivo'),
        ]
        return my_urls + urls

    @task('Processar Consumo', method='thread')
    def processar_dados(self, request, task=None):
        total, errors = MaterialConsumoSiads.processar(task=task)

        messages.info(request, f'Foram processados {total} itens.')
        messages.error(request, f'Foram foram encontrados {len(errors)} itens com erro.')

        task.finalize('Processamento Finalizado.')
        return redirect('/admin/siads/materialconsumosiads/')

    def gerar_arquivos_form(self, request, task=None):
        title = 'Geração do Arquivo de Material de Consumo'

        form = CampusForm(request.POST or None)

        if form.is_valid():
            uo_id = form.cleaned_data['campus'].id
            return redirect(f'/admin/siads/materialconsumosiads/gerar/arquivo/{uo_id}/')

        return render('default.html', ctx={'title': title, 'form': form}, request=request)

    # @task('Gerar Consumo', method='thread')
    def gerar_arquivos(self, request, obj_pk, task=None):
        def cabecalho(fd):
            dados = []

            # Montagem do registro
            dados.append('H')  # Identificador da linha
            dados.append('CO')  # Tipo do Arquivo
            dados.append('1')  # Sequencial que identifica o número do arquivo
            dados.append('25000')  # Código do órgão implantador
            dados.append('170531')  # Código da UASG
            dados.append('03063892408')  # CPF do usuário que gerou o arquivo
            dados.append('1')  # Gestão
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)

            fd.write(f'{row}\n')

        def rodape(fd, registros, total_campo7):
            now = datetime.now()

            dados = []

            # Montagem do registro
            dados.append('T')  # Identificador da linha
            dados.append(now.strftime('%d%m%Y%H%M%S'))  # Data Final
            dados.append(str(registros))  # Quantidade de Registros
            dados.append(str(total_campo7))  # Somatório do campo 7
            dados.append('FIM')  # Identificador de fim de arquivo
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        def add_registro(material, fd):
            dados = []

            # Montagem do registro
            dados.append('D')  # Identificação da linha para inclisão/alteração
            dados.append(material.codigo_material)  # Código do material de origem
            dados.append(material.descricao)  # Descrição do material
            dados.append(material.unidade_medida)  # Sigla da unidade de medida do material
            dados.append(material.codigo_conta)  # Código da conta contábil
            dados.append(material.endereco)  # Localização do material
            dados.append(material.qtd_disponivel)  # Quantidade Disponível do material
            dados.append(material.valor_saldo)  # Valor do saldo do material

            if material.estocavel:
                dados.append('TRUE')  # Se o material é estocável ou não
            else:
                dados.append('FALSE')  # Se o material é estocável ou não

            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        # ----------------------------------------------------------------------
        uo = get_object_or_404(UnidadeOrganizacional, id=obj_pk)
        response = HttpResponse(content_type='application/text charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="consumo.txt"'

        cabecalho(fd=response)

        materiais = MaterialConsumoSiads.objects.filter(uo=uo, exportavel=True)
        registros = 0
        total_campo7 = 0

        # task.count(materiais)

        # for material in task.iterate(materiais):
        for material in materiais:
            add_registro(material=material, fd=response)
            total_campo7 += material.quantidade
            registros += 1

        rodape(registros=registros, total_campo7=total_campo7, fd=response)

        messages.info(request, f'Foram gerados {registros} itens.')

        return response


admin.site.register(MaterialConsumoSiads, MaterialConsumoSiadsAdmin)


class FiltroUorg(SimpleListFilter):
    title = 'Uorg'
    parameter_name = 'uorg'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Uorg Definida'),
            ('NAO', 'Uorg não Encontrada Definida'),
            ('SEM', 'Uorg não Definida'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'NAO':
            queryset = queryset.filter(uorg='NÃO ENCONTRADO')
        elif self.value() == 'SEM':
            queryset = queryset.filter(uorg='SEM VINCULO')
        elif self.value() == 'COM':
            queryset = queryset.exclude(uorg__in=['NÃO ENCONTRADO', 'SEM VINCULO'])
        return queryset


class FiltroResponsavel(SimpleListFilter):
    title = 'Responsável'
    parameter_name = 'cpf_responsavel'

    def lookups(self, request, model_admin):
        return (
            ('COM', 'Responsável Definido'),
            ('NAO', 'Responsável não Definido'),
            ('SEM', 'Inventário sem Vínculo'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'COM':
            queryset = queryset.exclude(cpf_responsavel__in=['SETOR SIADS', 'VINCULO|SETOR'])
        elif self.value() == 'NAO':
            queryset = queryset.filter(cpf_responsavel='SETOR SIADS')
        elif self.value() == 'SEM':
            queryset = queryset.filter(cpf_responsavel='VINCULO|SETOR')
        return queryset


class MaterialPermanenteSiadsAdmin(ModelAdminPlus):
    list_display = ('uo', 'codigo_material', 'inventario', 'descricao', 'uorg', 'codigo_conta', 'cpf_responsavel', 'corresponsavel')
    list_filter = ('uo', FiltroContaContabil, FiltroUorg, FiltroResponsavel)

    list_display_icons = True

    form = MaterialPermanenteSiadsForm

    fieldsets = (
        (None, {'fields': ('codigo_material', 'descricao', 'patrimonio')}),
        (
            'Dados Disponíveis para Modificação',
            {
                'fields': ('especificacao', 'marca', 'modelo', 'fabricante', 'nr_serie'),
            },
        ),
    )

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': '/admin/siads/materialpermanentesiads/processar/dados/form/', 'label': 'Processar Dados', 'css_class': ''})
            items.append({'url': '/admin/siads/materialpermanentesiads/gerar/arquivo/form/', 'label': 'Gerar Arquivo', 'css_class': 'primary'})
        return items

    def get_urls(self):
        urls = super().get_urls()

        my_urls = [
            path('processar/dados/form/', self.url_wrap(self.processar_dados_form), name='siads_materialpermanentesiads_processar_arquivos_form'),
            path('processar/dados/<int:obj_pk>/', self.url_wrap(self.processar_dados), name='siads_materialpermanentesiads_processar_arquivos'),
            path('gerar/arquivo/form/', self.url_wrap(self.gerar_arquivos_form), name='siads_materialpermanentesiads_gerar_arquivo_form'),
            path('gerar/arquivo/<int:obj_pk>/', self.url_wrap(self.gerar_arquivos), name='siads_materialpermanentesiads_gerar_arquivo'),
        ]
        return my_urls + urls

    def processar_dados_form(self, request):
        title = 'Processamento dos Dados de Material de Permanente'

        form = CampusForm(request.POST or None)

        if form.is_valid():
            uo_id = form.cleaned_data['campus'].id
            return redirect(f'/admin/siads/materialpermanentesiads/processar/dados/{uo_id}/')

        return render('default.html', ctx={'title': title, 'form': form}, request=request)

    @task('Processar Consumo', method='thread')
    def processar_dados(self, request, obj_pk, task=None):
        uo = get_object_or_404(UnidadeOrganizacional, id=obj_pk)

        total, errors = MaterialPermanenteSiads.processar(uo=uo, task=task)

        messages.info(request, f'Foram processados {total} itens.')
        messages.error(request, f'Foram foram encontrados {len(errors)} itens com erro.')

        task.finalize('Processamento Finalizado.')
        return redirect('/admin/siads/materialpermanentesiads/')

    def gerar_arquivos_form(self, request, task=None):
        title = 'Geração do Arquivo de Material de Permanente'

        form = CampusForm(request.POST or None)

        if form.is_valid():
            uo_id = form.cleaned_data['campus'].id
            return redirect(f'/admin/siads/materialpermanentesiads/gerar/arquivo/{uo_id}/')

        return render('default.html', ctx={'title': title, 'form': form}, request=request)

    # @task('Gerar Consumo', method='thread')
    def gerar_arquivos(self, request, obj_pk, task=None):
        def cabecalho(fd):
            dados = []

            # Montagem do registro
            dados.append('H')  # Identificador da linha
            dados.append('PE')  # Tipo do Arquivo
            dados.append('1')  # Sequencial que identifica o número do arquivo
            dados.append('25000')  # Código do órgão implantador
            dados.append('170531')  # Código da UASG
            dados.append('03063892408')  # CPF do usuário que gerou o arquivo
            dados.append('1')  # Gestão
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)

            fd.write(f'{row}\n')

        def rodape(fd, registros, total_campo11):
            now = datetime.now()

            dados = []

            # Montagem do registro
            dados.append('T')  # Identificador da linha
            dados.append(now.strftime('%d%m%Y%H%M%S'))  # Data Final
            dados.append(str(registros))  # Quantidade de Registros
            dados.append(str(total_campo11))  # Somatório do campo 11
            dados.append('FIM')  # Identificador de fim de arquivo
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        def add_registro(material, fd):
            dados = []

            # Montagem do registro
            dados.append('D')  # Identificação da linha para inclisão/alteração
            dados.append(material.codigo_material)  # Código do material permanente
            dados.append(material.descricao)  # Descrição do material
            dados.append(material.codigo_conta)  # Código da conta contábil
            dados.append(material.endereco)  # Localização do material
            dados.append(material.uorg)  # Código da UORG do material
            dados.append(material.tipo)  # Restrito a bens
            dados.append(material.situacao)  # Pode ser: Bom, Recuperável, ...
            dados.append(material.tipo_plaqueta)  # Pode ser: metal, plástico, papel
            dados.append(material.dt_tombamento)  # Data de tombamento do bem
            dados.append(material.vlr_bem)  # Valor unitário do bem
            dados.append(material.forma_aquisicao)  # Forma como o bem foi adquirido
            dados.append(material.especificacao)  # Informar algum detalhe específico
            dados.append(material.dt_devolucao)  # Formato DDMMYYYY
            dados.append(material.nr_serie)  # Número de série do bem
            dados.append(material.patrimonio)  # Número patrimonial
            dados.append(material.marca)  # Marca do bem
            dados.append(material.modelo)  # Modelo do bem
            dados.append(material.fabricante)  # Fabricante do bem
            dados.append(material.garantidor)  # Responsável pela garantia
            dados.append(material.nr_contrato)  # Número do contrato de garantia
            dados.append(material.inicio_garantia)  # Data inicial da garantia
            dados.append(material.fim_garantia)  # Data final da garantia
            dados.append(material.cpf_responsavel)  # CPF do corresponsável
            dados.append(material.corresponsavel)  # Nome do corresponsável

            if material.almoxarifado:
                dados.append('TRUE')  # Se o bem está em amoxarifado
            else:
                dados.append('FALSE')  # Se o bem está em amoxarifado

            dados.append(material.dt_reavaliacao)  # Data de reavaliação
            dados.append(material.vlr_reavaliacao)  # Valor da reavaliação
            dados.append(material.vida_util)  # Vida útil
            dados.append(FIM_LINHA)  # Finalizador de linha

            row = add_delimitador(dados)
            fd.write(f'{row}\n')

        # ----------------------------------------------------------------------
        uo = get_object_or_404(UnidadeOrganizacional, id=obj_pk)
        response = HttpResponse(content_type='application/text charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="permanente.txt"'

        cabecalho(fd=response)

        materiais = MaterialPermanenteSiads.objects.filter(uo=uo, exportavel=True)
        registros = 0
        total_campo11 = 0

        # task.count(materiais)

        # for material in task.iterate(materiais):
        for material in materiais:
            add_registro(material=material, fd=response)
            total_campo11 += material.valor
            registros += 1

        rodape(registros=registros, total_campo11=total_campo11, fd=response)

        messages.info(request, f'Foram gerados {registros} itens.')

        return response


admin.site.register(MaterialPermanenteSiads, MaterialPermanenteSiadsAdmin)
