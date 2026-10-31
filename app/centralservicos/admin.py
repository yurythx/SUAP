from django.contrib import admin
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from centralservicos.forms import (
    BaseConhecimentoForm,
    CategoriaServicoForm,
    CentroAtendimentoForm,
    GestorAreaServicoForm,
    GrupoAtendimentoForm,
    GrupoInteressadoForm,
    GrupoServicoForm,
    MonitoramentoForm,
    RespostaPadraoForm,
    ServicoForm,
    TagForm,
    TarefaFormFactory,
)
from centralservicos.models import (
    AtendimentoAtribuicao,
    BaseConhecimento,
    BaseConhecimentoAnexo,
    CategoriaServico,
    CentroAtendimento,
    GestorAreaServico,
    GrupoAtendimento,
    GrupoInteressado,
    GrupoServico,
    Monitoramento,
    PerguntaAvaliacaoBaseConhecimento,
    RespostaPadrao,
    Servico,
    Tag,
    Tarefa,
    TarefaChamado,
)
from comum.models import AreaAtuacao
from djtools.contrib.admin import ModelAdminPlus, CustomTabListFilter, CompareVersionAdminPlus
from djtools.db import models
from djtools.forms.widgets import FilteredSelectMultiplePlus, TreeWidget
from djtools.templatetags.filters import format_user
from djtools.templatetags.filters.utils import format_hours, seconds_to_hours
from djtools.templatetags.tags import icon, icone
from centralservicos.templatetags import centralservicos_templatetags


class PerguntaAvaliacaoBaseConhecimentoAdmin(ModelAdminPlus):
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['area'].queryset = GestorAreaServico.minhas_areas(request.user)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(area__in=GestorAreaServico.minhas_areas(request.user)).distinct()


admin.site.register(PerguntaAvaliacaoBaseConhecimento, PerguntaAvaliacaoBaseConhecimentoAdmin)


class TagAdmin(ModelAdminPlus):
    form = TagForm
    list_filter = ('area',)
    list_display = ('nome', 'area')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['area'].queryset = GestorAreaServico.minhas_areas(request.user)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(area__in=GestorAreaServico.minhas_areas(request.user)).distinct()


admin.site.register(Tag, TagAdmin)


class GestorAreaServicoAdmin(ModelAdminPlus):
    form = GestorAreaServicoForm
    list_filter = ('area',)
    list_display = ('get_acoes', 'area', 'get_gestor')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_display_links = None

    def has_delete_permission(self, request, obj=None):
        retorno = super().has_delete_permission(request)
        if retorno and obj is not None:
            if request.user.has_perm('centralservicos.add_gestorareaservico') and obj.area in obj.minhas_areas(request.user):
                return True
        return False

    def get_gestor(self, obj):
        return mark_safe(f'<ul><li>{format_user(obj.gestor)}</li></ul>')

    get_gestor.short_description = 'Gestor'

    def get_acoes(self, obj):
        if self.request.user.has_perm('centralservicos.add_gestorareaservico') and obj.area in obj.minhas_areas(self.request.user):
            return mark_safe(icon('delete', f'/admin/centralservicos/gestorareaservico/{obj.id!s}/delete/'))
        return None

    get_acoes.short_description = 'Ações'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.has_perm('centralservicos.add_gestorareaservico'):
            form.base_fields['area'].queryset = AreaAtuacao.objects.filter(pk__in=GestorAreaServico.minhas_areas(request.user))
        return form


admin.site.register(GestorAreaServico, GestorAreaServicoAdmin)


class CentroAtendimentoAdmin(ModelAdminPlus):
    form = CentroAtendimentoForm
    search_fields = ('nome', 'area__nome')
    list_filter = ('area', 'ativo')
    list_display = ('id', 'nome', 'area', 'eh_local', 'ativo')
    list_display_icons = True
    list_per_page = 25
    readonly_fields = ('get_servicos_ativos_vinculados',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['area'].queryset = AreaAtuacao.objects.filter(pk__in=GestorAreaServico.minhas_areas(request.user))
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(area__in=GestorAreaServico.minhas_areas(request.user)).distinct()

    def get_servicos_ativos_vinculados(self, obj):
        if not obj or not obj.pk:
            return '-'
        servicos_ativos = Servico.objects.filter(centros_atendimento=obj, ativo=True)
        if not servicos_ativos.exists():
            return mark_safe('<span class="false">Nenhum</span>')
        return format_html('<ul>{}</ul>', format_html_join('', '<li>{}</li>', ((servico,) for servico in servicos_ativos)))

    get_servicos_ativos_vinculados.short_description = 'Serviços ativos vinculados (impedem a inativação)'


admin.site.register(CentroAtendimento, CentroAtendimentoAdmin)


class CategoriaServicoAdmin(ModelAdminPlus):
    form = CategoriaServicoForm
    list_filter = ('area',)
    search_fields = ('nome',)
    list_display = ('nome', 'area')
    list_display_icons = True
    list_per_page = 25
    export_to_xls = True

    def to_xls(self, request, queryset, processo):
        header = ['Código', 'Nome', 'Área']
        rows = [header]
        for obj in processo.iterate(queryset):
            row = [obj.pk, obj.nome, obj.area]
            rows.append(row)
        return rows

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        areas = GestorAreaServico.minhas_areas(request.user)
        return qs.filter(area__in=areas).distinct()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['area'].queryset = AreaAtuacao.objects.filter(pk__in=GestorAreaServico.minhas_areas(request.user))
        return form


admin.site.register(CategoriaServico, CategoriaServicoAdmin)


class GrupoServicoAdmin(ModelAdminPlus):
    form = GrupoServicoForm
    list_filter = ('categorias__area', 'categorias')
    search_fields = ('nome', 'detalhamento')
    list_display = ('nome', 'detalhamento', 'icone', 'get_categorias')
    list_display_icons = True
    list_per_page = 25
    export_to_xls = True

    def to_xls(self, request, queryset, processo):
        header = ['Código', 'Nome', 'Descrição', 'Código Categoria', 'Descrição Categoria']
        rows = [header]
        for obj in processo.iterate(queryset):
            for item in obj.categorias.all():
                row = [obj.pk, obj.nome, obj.detalhamento, item.pk, item.nome]
                rows.append(row)
        return rows

    def get_categorias(self, obj):
        lista = ['<ul>']
        for categoria in obj.categorias.all():
            lista.append(f'<li>{categoria}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_categorias.short_description = 'Categorias'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        areas = GestorAreaServico.minhas_areas(request.user)
        form.base_fields['categorias'].queryset = CategoriaServico.objects.filter(area__in=areas)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        areas = GestorAreaServico.minhas_areas(request.user)
        return qs.filter(categorias__area__in=areas).distinct()


admin.site.register(GrupoServico, GrupoServicoAdmin)


class CentroAtendimentoListFilter(admin.SimpleListFilter):
    title = 'Centro de Atendimento'
    parameter_name = 'centro_atendimento'

    def lookups(self, request, model_admin):
        meus_centros = CentroAtendimento.objects.filter(
            id__in=GrupoAtendimento.objects.filter(models.Q(atendentes=request.user) | models.Q(responsaveis=request.user))
            .order_by('centro_atendimento')
            .values_list('centro_atendimento')
            .distinct()
        )
        centros1 = [(c.id, '* ' + c.nome) for c in meus_centros]
        centros2 = []
        if request.user.is_superuser or request.user.has_group_cached(['centralservicos Administrador', 'Auditor']):
            todos_centros = CentroAtendimento.objects.exclude(id__in=meus_centros)
            centros2 = [(c.id, c.nome) for c in todos_centros]

        return centros1 + centros2

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(centros_atendimento__id=self.value())
        else:
            return queryset


class GrupoAtendimentoFilter(admin.SimpleListFilter):
    title = 'Grupo de Atendimento'
    parameter_name = 'grupo_atendimento'

    def lookups(self, request, model_admin):
        meus_grupos = GrupoAtendimento.meus_grupos(request.user).select_related('centro_atendimento')
        return [
            ('sem_grupo_ativo', '* Serviços sem grupo de atendimento ativo'),
        ] + [(f'{g.id}', f'{g.nome} ({g.centro_atendimento.nome})') for g in meus_grupos]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            if value == 'sem_grupo_ativo':
                return queryset.filter(id__in=Servico.get_servicos_ativos_sem_grupo_atendimento_ativo().values_list('id', flat=True))
            return queryset.filter(centros_atendimento__grupoatendimento__id=value)
        else:
            return queryset


class ServicoAdmin(ModelAdminPlus):
    form = ServicoForm
    list_filter = ('area', 'grupo_servico', 'tipo', 'ativo', 'interno', CentroAtendimentoListFilter, GrupoAtendimentoFilter)
    search_fields = ('nome',)
    list_display = (
        'nome',
        'tipo',
        'grupo_servico',
        'get_centros_atendimento',
        'get_publico_direcionado',
        'get_sla',
        'ativo',
        'interno',
        'opcoes',
    )
    list_display_icons = True
    list_per_page = 25
    export_to_xls = True

    fieldsets = (
        ('Dados gerais', {'fields': ('nome', 'tipo', 'area', 'grupo_servico')}),
        ('Atendimento', {'fields': ('centros_atendimento', 'sla_utilizado', 'sla_manual', 'publico_direcionado')}),
        ('Instruções para Abertura de Chamado', {'fields': ('texto_ajuda', 'texto_modelo')}),
        (
            'Configurações',
            {
                'fields': (
                    'permite_anexos',
                    'requer_numero_patrimonio',
                    'solicitar_local_atendimento',
                    'permite_abertura_terceiros',
                    'permite_telefone_adicional',
                    'nao_exibir_artigos',
                )
            },
        ),
        ('Visibilidade', {'fields': ('interno', 'ativo')}),
    )

    def opcoes(self, obj):
        botoes = [
            f'<a class="btn default" href="/centralservicos/estatisticas_servico/{obj.id}/">{icone("chart-line")} Estatísticas do serviço</a>',
            f'<a class="btn default" href="/centralservicos/listar_chamados_suporte/?servico={obj.id}&todos_status=on">{icone("concierge-bell")} {Servico.get_quantidade_chamados(obj)} chamados</a>',
        ]
        itens_li = ''.join([f'<li>{item}</li>' for item in botoes])
        return mark_safe(f'<ul class="action-bar">{itens_li}</ul>')

    opcoes.short_description = 'Opções'

    def to_xls(self, request, queryset, processo):
        header = ['Nome', 'Grupo de Serviço', 'Tipo', 'Chamados realizados']
        rows = [header]

        for obj in processo.iterate(queryset):
            row = [obj.nome, obj.grupo_servico, obj.tipo, obj.get_quantidade_chamados()]
            rows.append(row)
        return rows

    def get_centros_atendimento(self, obj):
        lista = ['<ul>']
        for centro in obj.centros_atendimento.all():
            lista.append(f'<li>{centro}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_centros_atendimento.short_description = 'Centros de Atendimento'

    def get_publico_direcionado(self, obj):
        lista = ['<ul>']
        if obj.publico_direcionado.exists():
            for publico in obj.publico_direcionado.all():
                lista.append(f'<li>{publico.nome}</li>')
        else:
            lista.append('<li>Todos</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_publico_direcionado.short_description = 'Público direcionado'

    def get_sla(self, obj: Servico) -> str:
        if obj.sla_utilizado == Servico.SLA_MANUAL:
            titulo = 'Manual'
            valor = format_hours(obj.sla_manual, '-')
        else:
            titulo = 'Automático'
            valor = format_hours(seconds_to_hours(obj.sla_automatico), '-')
        return mark_safe(f'<dl class="definition-list"><dt>{titulo}</dt><dd>{valor}</dd></dl>')

    get_sla.short_description = 'SLA'

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.pk:
            return (*self.readonly_fields, 'area')
        return self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        areas = GestorAreaServico.minhas_areas(request.user)
        grupos_servico = GrupoServico.objects.filter(categorias__area__in=areas)
        form.base_fields['grupo_servico'].queryset = grupos_servico.distinct()
        if obj and obj.id:
            form.base_fields['centros_atendimento'].queryset = CentroAtendimento.objects.filter(area=obj.area)
        else:
            form.base_fields['area'].queryset = areas
            if areas.count() == 1:
                form.base_fields['area'].initial = areas[0]
            form.base_fields['centros_atendimento'].queryset = CentroAtendimento.objects.filter(area__in=areas)
        return form

    def _eh_da_minha_area(self, request: HttpRequest, obj: Servico | None) -> bool:
        # O get_queryset lista pelos grupos de serviço (cujas categorias podem ser de outras áreas);
        # alterar ou remover exige ser gestor da área do próprio serviço.
        if obj is None or request.user.is_superuser:
            return True
        return GestorAreaServico.minhas_areas(request.user).filter(pk=obj.area_id).exists()

    def has_change_permission(self, request: HttpRequest, obj: Servico | None = None) -> bool:
        return super().has_change_permission(request, obj) and self._eh_da_minha_area(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Servico | None = None) -> bool:
        return super().has_delete_permission(request, obj) and self._eh_da_minha_area(request, obj)

    def get_queryset(self, request):
        return Servico.get_servicos_ao_atendente(request.user).prefetch_related(
            'centros_atendimento',
            'publico_direcionado',
        )


admin.site.register(Servico, ServicoAdmin)


class GrupoAtendimentoAdmin(ModelAdminPlus):
    form = GrupoAtendimentoForm
    list_filter = ('centro_atendimento__area', 'centro_atendimento', 'campus', 'ativo')
    search_fields = ('nome', 'responsaveis__first_name', 'responsaveis__last_name', 'atendentes__first_name', 'atendentes__last_name')
    list_display = (
        'nome',
        'ativo',
        'grupo_atendimento_superior',
        'campus',
        'get_responsaveis',
        'centro_atendimento',
        'get_atendentes',
        'get_servicos_ativos',
    )
    list_display_icons = True
    list_per_page = 20
    readonly_fields = ('get_servicos_ativos_vinculados',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        eh_gestor_da_central_de_servicos = GestorAreaServico.objects.filter(gestor=request.user).exists()
        if eh_gestor_da_central_de_servicos:
            areas = GestorAreaServico.minhas_areas(request.user)
        else:
            areas = GrupoAtendimento.objects.filter(Q(responsaveis=request.user) | Q(atendentes=request.user)).values_list(
                'centro_atendimento__area', flat=True
            )
        return qs.filter(centro_atendimento__area__in=areas).distinct()

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        return retorno and (not obj or obj.pode_editar(request.user))

    def get_responsaveis(self, obj):
        lista = ['<ul>']
        for user in obj.responsaveis.all():
            lista.append(f'<li>{format_user(user)}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_responsaveis.short_description = 'Responsáveis'

    def get_atendentes(self, obj):
        lista = ['<ul>']
        for user in obj.atendentes.all().order_by('first_name'):
            lista.append(f'<li>{format_user(user)}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_atendentes.short_description = 'Atendentes'

    def get_servicos_ativos(self, obj):
        servicos_ativos = Servico.objects.filter(ativo=True, centros_atendimento=obj.centro_atendimento)
        if servicos_ativos.exists():
            return servicos_ativos.count()
        else:
            return mark_safe('<span class="false">Nenhum</span>')

    get_servicos_ativos.short_description = 'Serviços Ativos'

    def get_servicos_ativos_vinculados(self, obj):
        if not obj or not obj.pk:
            return '-'
        servicos_ativos = Servico.objects.filter(centros_atendimento=obj.centro_atendimento, ativo=True)
        if not servicos_ativos.exists():
            return mark_safe('<span class="false">Nenhum</span>')
        return format_html('<ul>{}</ul>', format_html_join('', '<li>{}</li>', ((servico,) for servico in servicos_ativos)))

    get_servicos_ativos_vinculados.short_description = 'Serviços ativos vinculados (impedem a inativação)'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        if 'grupo_atendimento_superior' in form.base_fields:
            areas = GestorAreaServico.minhas_areas(request.user)
            raizes = GrupoAtendimento.objects.filter(grupo_atendimento_superior__isnull=True, centro_atendimento__area__in=areas)
            form.base_fields['grupo_atendimento_superior'].widget = TreeWidget(root_nodes=list(raizes))

        if GestorAreaServico.objects.filter(gestor=request.user).exists():
            areas = GestorAreaServico.minhas_areas(request.user)
        else:
            areas = GrupoAtendimento.objects.filter(responsaveis=request.user).values_list('centro_atendimento__area', flat=True)
        form.base_fields['centro_atendimento'].queryset = CentroAtendimento.objects.filter(area__in=areas)

        return form


admin.site.register(GrupoAtendimento, GrupoAtendimentoAdmin)


class BaseConhecimentoAnexoInline(admin.StackedInline):
    model = BaseConhecimentoAnexo
    fields = ('anexo',)
    extra = 1


class BaseConhecimentoAdmin(ModelAdminPlus, CompareVersionAdminPlus):
    form = BaseConhecimentoForm
    search_fields = ('id', 'titulo', 'resumo', 'solucao', 'tags')
    compare_template = 'centralservicos/reversion-compare/compare.html'
    object_history_template = 'centralservicos/reversion-compare/object_history.html'
    list_filter = (
        CustomTabListFilter,
        'area',
        'visibilidade',
        'grupos_atendimento',
        'servicos__grupo_servico',
        'servicos__grupo_servico__categorias',
        'servicos',
        'necessita_correcao',
        'supervisao_pendente',
        'atualizado_por',
        'ativo',
    )
    list_display = (
        'id',
        'titulo',
        'area',
        'visibilidade',
        'get_grupos_atendimento',
        'get_servicos',
        'get_supervisionado',
        'get_corrigido',
        'get_estah_disponivel_para_uso',
        'get_situacao',
    )
    list_display_icons = True
    list_per_page = 25
    show_count_on_tabs = True

    fieldsets = (
        ('Dados gerais', {'fields': ('area', 'titulo', 'resumo', 'solucao', 'tags', 'ativo')}),
        ('Visibilidade', {'fields': ('visibilidade', 'grupos_atendimento', 'servicos')}),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.pk:
            return (*self.readonly_fields, 'area')
        return self.readonly_fields

    def get_grupos_atendimento(self, obj):
        lista = ['<ul>']
        if not obj.grupos_atendimento.all().exists():
            lista.append('<li>Todos</li>')
        else:
            for grupo in obj.grupos_atendimento.all():
                lista.append(f'<li>{grupo}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_grupos_atendimento.short_description = 'Grupos de Atendimento'

    def get_servicos(self, obj):
        lista = ['<ul>']
        if not obj.servicos.all().exists():
            lista.append('<li>Todos</li>')
        else:
            for servico in obj.servicos.all():
                lista.append(f'<li>{servico}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_servicos.short_description = 'Serviços'

    def get_supervisionado(self, obj):
        if obj.supervisao_pendente:
            retorno = '<span class="status status-error">Não</span>'
        else:
            retorno = '<span class="status status-success">Sim</span>'
        return mark_safe(retorno)

    get_supervisionado.short_description = 'Supervisionado?'

    def get_corrigido(self, obj):
        if obj.necessita_correcao:
            retorno = '<span class="status status-error">Não</span>'
        else:
            retorno = '<span class="status status-success">Sim</span>'
        return mark_safe(retorno)

    get_corrigido.short_description = 'Corrigido?'

    def get_estah_disponivel_para_uso(self, obj):
        if obj.estah_disponivel_para_uso():
            retorno = '<span class="status status-success">Sim</span>'
        else:
            retorno = '<span class="status status-error">Não</span>'
        return mark_safe(retorno)

    get_estah_disponivel_para_uso.short_description = 'Disponível?'

    def get_situacao(self, obj):
        if obj.ativo:
            retorno = '<span class="status status-success">Ativo</span>'
        else:
            retorno = '<span class="status status-error">Inativo</span>'
        return mark_safe(retorno)

    get_situacao.short_description = 'Situação'

    inlines = [BaseConhecimentoAnexoInline]

    actions = ['unificar_bases', 'revisar_bases']

    def unificar_bases(self, request, queryset):
        bases = queryset.values_list('id', flat=True)
        ids = ','.join(str(id) for id in bases)
        return HttpResponseRedirect(f'/centralservicos/baseconhecimento/unificar/?bases={ids}')

    unificar_bases.short_description = 'Unificar Bases'

    def revisar_bases(self, request, queryset):
        bases = queryset.values_list('id', flat=True)
        ids = ','.join(str(id) for id in bases)
        return HttpResponseRedirect(f'/centralservicos/baseconhecimento/revisar/?bases={ids}')

    revisar_bases.short_description = 'Revisar Bases'

    def get_actions(self, request):
        actions = super().get_actions(request)
        try:
            if not request.user.has_perm('centralservicos.pode_unificar_baseconhecimento'):
                del actions['unificar_bases']
            if not request.user.has_perm('centralservicos.review_baseconhecimento'):
                del actions['revisar_bases']
        except KeyError:
            pass
        return actions

    def tab_supervisao_pendente(self, request, queryset):
        return queryset.filter(supervisao_pendente=True)

    tab_supervisao_pendente.short_description = 'Pendente de supervisão'

    def tab_necessita_correcao(self, request, queryset):
        return queryset.filter(necessita_correcao=True)

    tab_necessita_correcao.short_description = 'Pendente de correção'

    def get_tabs(self, request):
        return ['tab_supervisao_pendente', 'tab_necessita_correcao']

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if request.user.is_superuser:
            return qs
        areas = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
        meus_grupos = GrupoAtendimento.meus_grupos(request.user)
        return qs.filter(area__in=areas).filter(models.Q(grupos_atendimento__isnull=True) | models.Q(grupos_atendimento__in=meus_grupos)).distinct()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        if not request.user.has_perm('centralservicos.add_public_baseconhecimento'):
            form.base_fields['visibilidade'].choices = BaseConhecimento.VISIBILIDADE_CHOICES_PRIVADA_OU_SIGILOSA
        if 'servico' in request.GET:
            form.base_fields['servicos'].initial = [request.GET['servico']]
        if 'grupo_atendimento' in request.GET:
            form.base_fields['grupos_atendimento'].initial = [request.GET['grupo_atendimento']]
        form.base_fields['grupos_atendimento'].widget = FilteredSelectMultiplePlus('', True)
        form.base_fields['servicos'].widget = FilteredSelectMultiplePlus('', True)

        if 'area' in form.base_fields:
            areas = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(request.user)
            form.base_fields['area'].queryset = areas
            if areas.count() == 1:
                form.base_fields['area'].initial = areas[0]
            form.base_fields['servicos'].queryset = (
                Servico.objects.filter(centros_atendimento__area__in=areas).order_by('grupo_servico', 'nome').distinct()
            )
            form.base_fields['grupos_atendimento'].queryset = GrupoAtendimento.objects.filter(centro_atendimento__area__in=areas).distinct()
        else:
            form.base_fields['servicos'].queryset = (
                Servico.objects.filter(centros_atendimento__area=obj.area).order_by('grupo_servico', 'nome').distinct()
            )
            form.base_fields['grupos_atendimento'].queryset = GrupoAtendimento.objects.filter(centro_atendimento__area=obj.area).distinct()

        return form


admin.site.register(BaseConhecimento, BaseConhecimentoAdmin)


class GrupoAtendimentoFilter(admin.SimpleListFilter):
    title = 'Grupo de Atendimento'
    parameter_name = 'grupo_atendimento'

    def lookups(self, request, model_admin):
        return [(grupo.id, grupo.nome) for grupo in GrupoAtendimento.meus_grupos(request.user)]

    def queryset(self, request, queryset):
        if self.value():
            if GrupoAtendimento.meus_grupos(request.user).filter(id=self.value()).exists():
                qs = AtendimentoAtribuicao.objects.filter(grupo_atendimento__id=self.value(), cancelado_em__isnull=True)
                return queryset.filter(pk__in=qs.values('chamado'))
            else:
                return queryset.none()


class MinhasAtribuicoesFilter(admin.SimpleListFilter):
    title = 'Atribuições'
    parameter_name = 'minhas_atribuicoes'

    def lookups(self, request, model_admin):
        return (('1', 'Atribuídos a mim'), ('2', 'Atribuídos a outros'))

    def queryset(self, request, queryset):
        if self.value() == '1':
            qs = AtendimentoAtribuicao.objects.filter(atribuido_para=request.user, cancelado_em__isnull=True)
            return queryset.filter(pk__in=qs.values('chamado'))

        if self.value() == '2':
            qs = AtendimentoAtribuicao.objects.filter(cancelado_em__isnull=True).exclude(atribuido_para=request.user)
            return queryset.filter(pk__in=qs.values('chamado'))


class MonitoramentoAdmin(ModelAdminPlus):
    form = MonitoramentoForm
    search_fields = ('titulo', 'grupos__nome', 'token')
    list_filter = ('grupos__centro_atendimento__area',)
    list_display = ('titulo', 'get_grupos_atendimento', 'organizar_por_tipo', 'cadastrado_por', 'cadastrado_em')
    list_display_icons = True
    list_per_page = 25

    def get_grupos_atendimento(self, obj):
        lista = ['<ul>']
        for grupo in obj.grupos.all():
            lista.append(f'<li>{grupo}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_grupos_atendimento.short_description = 'Grupos de Atendimento'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['grupos'].queryset = GrupoAtendimento.meus_grupos(request.user).filter(ativo=True)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(grupos__in=GrupoAtendimento.meus_grupos(request.user)).distinct()


admin.site.register(Monitoramento, MonitoramentoAdmin)


class RespostaPadraoAdmin(ModelAdminPlus):
    form = RespostaPadraoForm
    search_fields = ('texto',)
    list_filter = ('atendente',)
    list_display = ('atendente', 'texto')
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.has_group_cached('centralservicos Administrador')):
            return qs.filter(atendente__id=request.user.id)
        return qs

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.atendente = request.user
        super().save_model(request, obj, form, change)


admin.site.register(RespostaPadrao, RespostaPadraoAdmin)


class GrupoInteressadoAdmin(ModelAdminPlus):
    form = GrupoInteressadoForm
    search_fields = ('titulo',)
    list_filter = ('grupo_atendimento',)
    list_display = ('titulo', 'grupo_atendimento', 'get_interessados')
    list_display_icons = True
    list_per_page = 25

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not (request.user.is_superuser or request.user.has_group_cached('centralservicos Administrador')):
            meus_grupos = GrupoAtendimento.meus_grupos(request.user)
            return qs.filter(grupo_atendimento__in=meus_grupos)
        return qs

    def get_interessados(self, obj):
        lista = ['<ul>']
        for grupo in obj.interessados.all():
            lista.append(f'<li>{grupo}</li>')
        lista.append('</ul>')
        return mark_safe('\n'.join(lista))

    get_interessados.short_description = 'Interessados'


admin.site.register(GrupoInteressado, GrupoInteressadoAdmin)


class TarefaAdmin(ModelAdminPlus):
    search_fields = Tarefa.SEARCH_FIELDS
    list_filter = ('servico', 'servico__area')
    list_display = ('titulo', 'descricao', 'servico', 'servico_area')
    list_display_icons = True
    list_per_page = 25
    show_tab_any_data = False
    show_count_on_tabs = True
    empty_queryset_message = 'Nenhum cadastro de tarefa encontrado ou a exibir.'

    def servico_area(self, obj):
        return f'{obj.servico.area}'

    servico_area.short_description = 'Área do Serviço'
    servico_area.admin_order_field = 'servico__area'

    def has_view_permission(self, request, obj=None):
        return Tarefa.pode_visualizar_cadastro_tarefas(request.user)

    def has_add_permission(self, request, obj=None):
        return Tarefa.pode_adicionar(request.user)

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar(request.user)
        return False

    def has_delete_permission(self, request, obj=None):
        if obj:
            return obj.pode_excluir(request.user)
        return False

    def get_action_bar(self, request, remove_add_button=False):
        if Tarefa.pode_adicionar(request.user):
            action_bar = super().get_action_bar(request, remove_add_button=True)
            new_add_button = {
                'label': 'Adicionar Tarefa',
                'css_class': 'success',
                'url': '/admin/centralservicos/tarefa/add/',
            }
            return [new_add_button, *action_bar]
        return super().get_action_bar(request, remove_add_button=remove_add_button)

    def get_form(self, request, obj=None, **kwargs):
        minhas_areas_como_gestor = GestorAreaServico.minhas_areas(request.user)
        formClass = TarefaFormFactory(minhas_areas_como_gestor)
        return formClass

    def get_queryset(self, request):
        return Tarefa.get_tarefas_escopo(request.user)


admin.site.register(Tarefa, TarefaAdmin)


class TarefaChamadoGrupoAtendimentoAtualFilter(admin.SimpleListFilter):
    title = 'Grupo de Atendimento atual'
    parameter_name = 'grupo_atendimento_atual'

    def lookups(self, request, model_admin):
        """disponibiliza os grupos de atendimento"""
        # grupos_atendimento = GrupoAtendimento.objects.none()
        # user_eh_gestor_central_servicos = request.user.has_group('Gestor da Central de Serviços')
        # if user_eh_gestor_central_servicos:
        #     # todos os grupos
        #     grupos_atendimento = GrupoAtendimento.objects.all()
        # else:
        #     # apenas meus grupos
        #     grupos_atendimento = GrupoAtendimento.meus_grupos(request.user)
        tarefas_chamados = model_admin.get_queryset(request)
        chamados_pks = tarefas_chamados.values_list('chamado__pk', flat=True)
        grupos_atendimento = GrupoAtendimento.objects.filter(atendimentoatribuicao__chamado__pk__in=chamados_pks).distinct()
        return [[grupo_atendimento.id, f'{grupo_atendimento}'] for grupo_atendimento in grupos_atendimento]

    def queryset(self, request, queryset):
        """filtra apenas no escopo do atendimento atual"""
        value = self.value()
        if value:
            atendimentos_do_chamado = (
                AtendimentoAtribuicao.objects.filter(
                    chamado_id=models.OuterRef('chamado__pk'),
                ).order_by('-atribuido_em')  # em ordem cronológica a partir do mais atual
            )
            return (
                queryset.annotate(
                    grupo_atendimento_atual_pk=models.Subquery(atendimentos_do_chamado[:1].values('grupo_atendimento__pk')),
                )
                .filter(grupo_atendimento_atual_pk=value)
                .distinct()
            )
        return queryset


class TarefaChamadoAdmin(ModelAdminPlus):
    search_fields = TarefaChamado.SEARCH_FIELDS
    list_filter = (CustomTabListFilter, 'situacao', 'responsavel', 'tarefa__servico', TarefaChamadoGrupoAtendimentoAtualFilter)
    list_display = ('tarefa_titulo', 'tarefa_situacao', 'responsavel', 'chamado', 'chamado_grupo_atendimento_atual')
    list_display_icons = True
    list_per_page = 25
    show_tab_any_data = False
    show_count_on_tabs = True
    empty_queryset_message = 'Nenhuma tarefa encontrada ou a exibir.'

    def has_view_permission(self, request, obj=None):
        return TarefaChamado.pode_visualizar_tarefas_vinculadas(request.user)

    def has_add_permission(self, request, obj=None):
        """apenas via views.vincular_tarefa_chamado"""
        return False

    def has_change_permission(self, request, obj=None):
        """apenas via views.editar_tarefa_chamado"""
        return False

    def tarefa_titulo(self, obj):
        return f'{obj.tarefa.titulo}'

    tarefa_titulo.short_description = 'Título'
    tarefa_titulo.admin_order_field = 'tarefa__titulo'

    def tarefa_situacao(self, obj):
        return centralservicos_templatetags.tarefa_chamado_situacao_status(obj.situacao)

    tarefa_situacao.short_description = 'Situação'
    tarefa_situacao.admin_order_field = 'situacao'

    def chamado_grupo_atendimento_atual(self, obj):
        grupo_atendimento_atual = obj.chamado.get_atendimento_atual()['grupo_atendimento']
        if grupo_atendimento_atual:
            return f'{grupo_atendimento_atual}'
        return '-'

    chamado_grupo_atendimento_atual.short_description = 'Grupo de Atendimento atual'

    def get_queryset(self, request):
        return TarefaChamado.get_tarefas_vinculadas_escopo(request.user)

    def get_tabs(self, request):
        return ['tab_todas', 'tab_ativas']

    def tab_todas(self, request, queryset):
        return queryset

    tab_todas.short_description = 'Todas'

    def tab_ativas(self, request, queryset):
        return queryset.filter(**TarefaChamado.get_tarefas_vinculadas_ativas_filtro())

    tab_ativas.short_description = 'Ativas'


admin.site.register(TarefaChamado, TarefaChamadoAdmin)
