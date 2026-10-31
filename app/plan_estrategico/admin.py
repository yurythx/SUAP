from collections import defaultdict

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from comum.utils import get_uo
from djtools.contrib.admin import ModelAdminPlus
from djtools.contrib.admin.filters import CustomTabListFilter
from djtools.templatetags.filters import format_money, in_group
from plan_estrategico.forms import (
    ArquivoMetaForm,
    NotaCredito,
    NotaDotacao,
    PDIForm,
    PerspectivaForm,
    PlanoAtividadePDIForm,
    PreenchimentoVariavelForm,
)
from plan_estrategico.models import (
    PDI,
    ArquivoMeta,
    Indicador,
    MovimentacaoCredito,
    NotaEmpenho,
    ObjetivoEstrategico,
    OrigemRecurso,
    OrigemRecursoProjeto,
    PeriodoPreenchimentoVariavel,
    Perspectiva,
    PlanoAtividade,
    ProjetoEstrategico,
    ProjetoPlanoAtividade,
    RequisicaoDespesa,
    RequisicaoRealocacao,
    TematicaVariavel,
    UnidadeGestora,
    Variavel,
    VariavelCampus,
)


class PDIAdmin(ModelAdminPlus):
    list_display = ('ano_inicial_pdi', 'ano_final_pdi', 'qtd_anos', 'get_documento_url', 'get_mapa_url', 'get_manual_url', 'get_acoes')
    list_display_icons = True

    form = PDIForm

    fieldsets = (
        ('Período PDI', {'fields': ('qtd_anos', 'ano_inicial_pdi', 'ano_final_pdi', 'documento', 'mapa_estrategico', 'manual')}),
        ('Faixa do Farol de Desempenho', {'fields': (('valor_faixa_vermelha'), ('valor_faixa_amarela'), ('valor_faixa_verde'))}),
    )

    def get_documento_url(self, obj):
        if obj.documento:
            return mark_safe('<a href="{}">{}</a>'.format(obj.documento.url, 'Documento PDI'))
        return '-'

    get_documento_url.short_description = 'Documento PDI'

    def get_mapa_url(self, obj):
        if obj.mapa_estrategico:
            return mark_safe(f'<a href="{obj.mapa_estrategico.url}">Mapa Estratégico</a>')
        return '-'

    get_mapa_url.short_description = 'Mapa Estratégico'

    def get_manual_url(self, obj):
        if obj.manual:
            return mark_safe(f'<a href="{obj.manual.url}">Manual</a>')
        return '-'

    get_manual_url.short_description = 'Manual Indicadores'

    def get_acoes(self, obj):
        return mark_safe('<a class="btn" href="{}">Detalhar</a>'.format(reverse_lazy('pdi_ver', kwargs={'pdi_pk': obj.pk})))

    get_acoes.short_description = 'Ações'


admin.site.register(PDI, PDIAdmin)


class PerspectivaAdmin(ModelAdminPlus):
    list_display = ('sigla', 'nome', 'descricao')
    list_display_icons = True
    list_filter = ('id',)
    search_fields = ('nome',)

    form = PerspectivaForm

    fieldsets = ((None, {'fields': ('sigla', 'nome', 'descricao')}),)


admin.site.register(Perspectiva, PerspectivaAdmin)


class ProjetoEstrategicoAdmin(ModelAdminPlus):
    list_display = ('codigo', 'nome')
    list_display_icons = True
    search_fields = ('nome',)


admin.site.register(ProjetoEstrategico, ProjetoEstrategicoAdmin)


class ObjetivoEstrategicoAdmin(ModelAdminPlus):
    list_display = ('sigla', 'descricao')
    list_display_icons = True
    search_fields = ('descricao',)


admin.site.register(ObjetivoEstrategico, ObjetivoEstrategicoAdmin)


class IndicadorAdmin(ModelAdminPlus):
    list_display = ('sigla', 'descricao', 'nivel_rede', 'tipo', 'calcular_media', 'get_tendencia')
    list_display_icons = True
    list_filter = ('nivel_rede',)
    search_fields = ('sigla', 'descricao', 'tendencia')
    avoid_short_search = False

    def get_tendencia(self, obj):
        if obj.tendencia == Indicador.DIRECAO_ALTA:
            retorno = '<i style="color: green" class="fas fa-long-arrow-alt-up"></i>'
        else:
            retorno = '<i style="color: green" class="fas fa-long-arrow-alt-down"></i>'

        return mark_safe(retorno)

    get_tendencia.short_description = 'Tendência'


admin.site.register(Indicador, IndicadorAdmin)


class TematicaVariavelAdmin(ModelAdminPlus):
    list_display = ('nome',)
    ordering = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    avoid_short_search = False


admin.site.register(TematicaVariavel, TematicaVariavelAdmin)


class VariavelAdmin(ModelAdminPlus):
    list_display = ('nome', 'sigla', 'descricao', 'tematica', 'nivel_rede', 'fonte')
    list_filter = ('tematica', 'nivel_rede')
    exclude = ['valor']
    ordering = ('sigla',)
    search_fields = ('nome', 'sigla', 'fonte', 'descricao')
    list_display_icons = True
    avoid_short_search = False
    show_count_on_tabs = True


admin.site.register(Variavel, VariavelAdmin)


class VariavelCampusAdmin(ModelAdminPlus):
    list_display = (
        'get_variavel',
        'get_situacao',
        'uo',
        'ano',
        'get_nivel',
        'get_fonte',
        'get_valor_ideal',
        'get_valor_real',
        'get_valor_trimestral',
        'data_atualizacao',
        'get_opcoes',
    )
    ordering = ('variavel__sigla', 'ano')
    list_filter = (CustomTabListFilter, 'uo', 'ano', 'variavel__fonte', 'variavel__tematica', 'situacao', 'variavel__nivel_rede')
    search_fields = ('variavel__nome', 'variavel__sigla')
    show_list_display_icons = True
    export_to_xls = True
    export_to_csv = True
    avoid_short_search = False
    actions = 'ativar_variavel', 'desativar_variavel'
    show_count_on_tabs = True
    list_display_links = None

    def get_opcoes(self, obj):
        opcoes = []
        opcoes.append('<ul class="action-bar">')
        if (
            PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento()
            and PeriodoPreenchimentoVariavel.get_em_periodo_de_preenchimento()[0].ano.ano == obj.ano
            and (
                in_group(self.request.user, 'Administrador de Planejamento Estratégico')
                or (in_group(self.request.user, 'Gestor Estratégico Local, Gestor Estratégico Sistêmico') and obj.variavel.fonte == 'Manual')
            )
        ):
            opcoes.append(f'<li><a href=/plan_estrategico/variavel/{obj.pk}/atualizar/ class="btn popup primary">Informar valor</a></li>')
        if self.request.user.has_group_cached('Administrador de Planejamento Estratégico'):
            opcoes.append(
                f'<li><a href=/plan_estrategico/variavel_ideal/{obj.pk}/atualizar/ class="btn popup primary">Atualizar valor da meta</a></li>'
            )
        opcoes.append(f'<li><a href=/plan_estrategico/ver_valores_trimestrais/{obj.pk}/ class="btn popup default">Ver valores trimestrais</a></li>')
        opcoes.append(f'<li><a href=/plan_estrategico/variavel/{obj.variavel.pk}/visualizar/ class="btn popup default">Detalhar </a></li>')
        opcoes.append('</ul>')
        return mark_safe(' '.join(opcoes))

    get_opcoes.short_description = 'Opções'

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_group_cached('Gestor Estratégico Local'):
            list_display = ('get_variavel', 'uo', 'ano', 'get_valor_real', 'get_valor_trimestral', 'data_atualizacao', 'get_opcoes')
        if request.user.has_group_cached('Gestor Estratégico Sistêmico'):
            list_display = (
                'get_variavel',
                'uo',
                'ano',
                'get_nivel',
                'get_fonte',
                'get_valor_real',
                'get_valor_trimestral',
                'data_atualizacao',
                'get_opcoes',
            )
        return list_display

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_group_cached('Gestor Estratégico Local'):
            list_filter = (CustomTabListFilter, 'uo', 'ano', 'variavel__tematica')
        if request.user.has_group_cached('Gestor Estratégico Sistêmico'):
            list_filter = (CustomTabListFilter, 'uo', 'ano', 'variavel__tematica', 'situacao', 'variavel__nivel_rede')
        return list_filter

    def get_valor_ideal(self, obj):
        if obj.valor_ideal is None:
            return mark_safe('<span class="status status-alert">Aguardando valor</span>')
        else:
            return str(obj.valor_ideal).replace('.', ',')

    get_valor_ideal.short_description = 'Valor meta'

    def get_fonte(self, obj):
        if obj.variavel.fonte:
            return obj.variavel.fonte

    get_fonte.short_description = 'Fonte'

    def get_nivel(self, obj):
        return bool(obj.variavel.nivel_rede)

    get_nivel.short_description = 'É variável de rede?'
    get_nivel.boolean = True

    def get_variavel(self, obj):
        return obj.variavel.sigla

    get_variavel.short_description = 'Variável'

    def get_valor_real(self, obj):
        if obj.valor_real is None:
            return mark_safe('<span class="status status-alert">Aguardando valor</span>')
        else:
            return str(obj.valor_real).replace('.', ',')

    get_valor_real.short_description = 'Último valor informado'

    def get_valor_trimestral(self, obj):
        if obj.variavel.fonte != 'Manual':
            return mark_safe('<span class="status status-info">Preenchimento automático</span>')
        elif obj.valor_trimestral is None:
            return mark_safe('<span class="status status-alert">Aguardando valor</span>')
        else:
            return str(obj.valor_trimestral).replace('.', ',')

    get_valor_trimestral.short_description = 'Valor acumulado'

    def get_situacao(self, obj):
        if obj.situacao == VariavelCampus.ATIVA:
            return mark_safe('<span class="status status-success">Ativa</span>')
        else:
            return mark_safe('<span class="status status-danger">Não se aplica</span>')

    get_situacao.short_description = 'Situação'

    def get_tabs(self, request):
        return ['tab_manual', 'tab_automaticas']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.has_group_cached('Gestor Estratégico Sistêmico'):
            queryset = queryset.filter(situacao=VariavelCampus.ATIVA)
            return queryset
        if request.user.has_group_cached('Gestor Estratégico Local'):
            queryset = queryset.filter(uo=get_uo(request.user), situacao=VariavelCampus.ATIVA)
            return queryset
        return queryset

    def tab_manual(self, request, queryset):
        return queryset.filter(variavel__fonte='Manual')

    tab_manual.short_description = 'Variáveis manuais'

    def tab_automaticas(self, request, queryset):
        return queryset.exclude(variavel__fonte='Manual')

    tab_automaticas.short_description = 'Variáveis automáticas'

    def get_action_bar(self, request):
        pdi = PDI.objects.all().first()
        items = super().get_action_bar(request)
        if pdi.manual:
            url_base = pdi.manual.url
            items.append({'url': url_base, 'label': 'Manual de indicadores'})
        return items

    def desativar_variavel(self, request, queryset):
        for variavel in queryset:
            if variavel.valor_real is None:
                variavel.valor_real = 0
            variavel.situacao = VariavelCampus.NAO_SE_APLICA
            variavel.save()
        messages.success(request, 'As variáveis selecionadas foram desativadas com sucesso.')

    desativar_variavel.short_description = 'Desativar variáveis selecionadas'

    def ativar_variavel(self, request, queryset):
        queryset.update(situacao=VariavelCampus.ATIVA)
        messages.success(request, 'As variáveis selecionadas foram ativadas com sucesso.')

    ativar_variavel.short_description = 'Ativar variáveis selecionadas'

    def get_actions(self, request):
        if in_group(request.user, 'Administrador de Planejamento Estratégico'):
            return super().get_actions(request)
        return []

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'Sigla',
            'Nome',
            'Área temática',
            'Situação',
            'Campi',
            'Ano',
            'É variável de rede?',
            'Fonte',
            'Valor meta',
            'Último valor informado',
            'Data da importação',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            situacao = 'Não se aplica'
            if obj.situacao == VariavelCampus.ATIVA:
                situacao = 'Ativa'

            row = [
                idx + 1,
                obj.variavel.sigla,
                obj.variavel.nome,
                obj.variavel.tematica,
                situacao,
                obj.uo,
                obj.ano,
                obj.variavel.nivel_rede,
                obj.variavel.fonte,
                obj.valor_ideal,
                obj.valor_real,
                obj.data_atualizacao,
            ]
            rows.append(row)
        return rows


admin.site.register(VariavelCampus, VariavelCampusAdmin)


class PeriodoPreenchimentoVariavelAdmin(ModelAdminPlus):
    list_display = ('ano', 'trimestre', 'data_inicio', 'data_termino')
    list_filter = ('ano',)
    list_display_icons = True

    form = PreenchimentoVariavelForm


admin.site.register(PeriodoPreenchimentoVariavel, PeriodoPreenchimentoVariavelAdmin)


class ArquivoMetaAdmin(ModelAdminPlus):
    list_display = ('arquivo', 'data_importacao', 'usuario')
    list_display_icons = True

    form = ArquivoMetaForm


admin.site.register(ArquivoMeta, ArquivoMetaAdmin)


class PlanoAtividadeAdmin(ModelAdminPlus):
    list_display = ('pdi', 'ano_base', 'data_geral_inicial', 'data_geral_final')
    list_display_icons = True

    form = PlanoAtividadePDIForm

    fieldsets = (
        (None, {'fields': ('pdi', 'ano_base', 'percentual_reserva_tecnica')}),
        ('Período de Vigência', {'fields': (('data_geral_inicial', 'data_geral_final'),)}),
        (
            'Período Pré-LOA',
            {
                'fields': (
                    ('data_orcamentario_preloa_inicial', 'data_orcamentario_preloa_final'),
                    ('data_projetos_preloa_inicial', 'data_projetos_preloa_final'),
                    ('data_atividades_preloa_inicial', 'data_atividades_preloa_final'),
                )
            },
        ),
        (
            'Período Pós-LOA',
            {
                'fields': (
                    ('data_orcamentario_posloa_inicial', 'data_orcamentario_posloa_final'),
                    ('data_projetos_posloa_inicial', 'data_projetos_posloa_final'),
                    ('data_atividades_posloa_inicial', 'data_atividades_posloa_final'),
                )
            },
        ),
    )


admin.site.register(PlanoAtividade, PlanoAtividadeAdmin)


class ProjetoPlanoAtividadeAdmin(ModelAdminPlus):
    list_display = ('projeto', 'plano_atividade')

    def delete_view(self, request, object_id, extra_context=None):
        obj = ProjetoPlanoAtividade.objects.get(id=int(object_id)).plano_atividade_id
        response = super().delete_view(request, object_id, extra_context)

        if isinstance(response, HttpResponseRedirect):
            return HttpResponseRedirect(f'/plan_estrategico/ver_plano_atividade/{obj}/?tab=projeto_estrategico')

        return response


admin.site.register(ProjetoPlanoAtividade, ProjetoPlanoAtividadeAdmin)


class AnoPlanoAtividadeFilter(SimpleListFilter):
    title = _('Ano do plano de atividade')
    parameter_name = 'ano_base'

    def lookups(self, request, model_admin):
        qs = (
            model_admin.get_queryset(request)
            .select_related('plano_atividade__ano_base')
            .values_list('plano_atividade__ano_base__id', 'plano_atividade__ano_base__ano')
            .distinct()
            .order_by('-plano_atividade__ano_base__ano')
        )
        return [(str(ano_base_id), str(ano)) for ano_base_id, ano in qs if ano is not None]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(plano_atividade__ano_base_id=self.value())
        return queryset


class OrigemRecursoRealocacaoFilter(SimpleListFilter):
    campo = None

    def __init__(self, request, params, model, model_admin):
        self.model_admin = model_admin
        super().__init__(request, params, model, model_admin)

    def get_origens_por_codigo(self, request) -> dict[str, list[int]]:
        """Mapeia o código da origem de recurso para os ids de todas as suas ocorrências."""
        ids = self.model_admin.get_queryset(request).values_list(f'{self.campo}__origem_recurso_id', flat=True).distinct()
        origens = OrigemRecurso.objects.filter(pk__in={origem_id for origem_id in ids if origem_id is not None}).select_related(
            'acao_financeira__acao', 'acao_financeira__ptres', 'gnd'
        )
        origens_por_codigo = defaultdict(list)
        for origem in origens:
            origens_por_codigo[str(origem)].append(origem.pk)
        return origens_por_codigo

    def lookups(self, request, model_admin):
        return sorted((codigo, codigo) for codigo in self.get_origens_por_codigo(request))

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{f'{self.campo}__origem_recurso__in': self.get_origens_por_codigo(request).get(self.value(), [])})
        return queryset


class OrigemRecursoConcedenteFilter(OrigemRecursoRealocacaoFilter):
    title = _('Origem de recurso concedente')
    parameter_name = 'origem_concedente'
    campo = 'origem_concedente'


class OrigemRecursoRecebedoraFilter(OrigemRecursoRealocacaoFilter):
    title = _('Origem de recurso recebedora')
    parameter_name = 'origem_recebedora'
    campo = 'origem_recebedora'


class RequisicaoRealocacaoAdmin(ModelAdminPlus):
    list_display = (
        'get_numero',
        'unidade_concedente',
        'unidade_recebedora',
        'get_atividade_concedente',
        'get_atividade_recebedora',
        'get_origem_concedente',
        'get_origem_recebedora',
        'get_valor_requisicao',
        'get_valor_aprovado',
        'get_status',
        'get_data_cadastro',
        'get_usuario',
    )
    list_display_icons = True
    list_per_page = 20
    list_filter = (
        CustomTabListFilter,
        'numero',
        'unidade_concedente',
        'unidade_recebedora',
        OrigemRecursoConcedenteFilter,
        OrigemRecursoRecebedoraFilter,
        AnoPlanoAtividadeFilter,
    )
    date_hierarchy = 'data_cadastro'
    show_count_on_tabs = True
    export_to_xls = True

    def get_queryset(self, request, manager=None, *args, **kwargs):
        queryset = super().get_queryset(request, manager, *args, **kwargs)
        return queryset.select_related(
            'origem_concedente__projeto_plano_atividade__projeto',
            'origem_concedente__origem_recurso__acao_financeira__acao',
            'origem_concedente__origem_recurso__acao_financeira__ptres',
            'origem_concedente__origem_recurso__gnd',
            'origem_recebedora__projeto_plano_atividade__projeto',
            'origem_recebedora__origem_recurso__acao_financeira__acao',
            'origem_recebedora__origem_recurso__acao_financeira__ptres',
            'origem_recebedora__origem_recurso__gnd',
        )

    def get_atividade_concedente(self, obj):
        return obj.atividade_concedente

    get_atividade_concedente.short_description = 'Atividade Concedente'

    def get_atividade_recebedora(self, obj):
        return obj.atividade_recebedora

    get_atividade_recebedora.short_description = 'Atividade Recebedora'

    def get_origem_concedente(self, obj):
        return obj.origem_concedente or '-'

    get_origem_concedente.short_description = 'Origem de Recurso Concedente'

    def get_origem_recebedora(self, obj):
        return obj.origem_recebedora or '-'

    get_origem_recebedora.short_description = 'Origem de Recurso Recebedora'

    def get_valor_requisicao(self, obj):
        return f'R$ {format_money(obj.valor_requisicao)}'

    get_valor_requisicao.admin_order_field = 'valor_requisicao'
    get_valor_requisicao.short_description = 'Valor da Requisição'

    def get_valor_aprovado(self, obj):
        return f'R$ {format_money(obj.valor_aprovado_unidade)}'

    get_valor_aprovado.admin_order_field = 'valor_aprovado_unidade'
    get_valor_aprovado.short_description = 'Valor Aprovado'

    def get_status(self, obj):
        return mark_safe(obj.get_status())

    get_status.admin_order_field = 'status'
    get_status.short_description = 'Situação'

    def get_data_cadastro(self, obj):
        return obj.data_cadastro.strftime('%d/%m/%Y %H:%M:%S')

    get_data_cadastro.admin_order_field = 'data_cadastro'
    get_data_cadastro.short_description = 'Data do Cadastro'

    def get_usuario(self, obj):
        return obj.usuario

    get_usuario.admin_order_field = 'usuario'
    get_usuario.short_description = 'Cadastrado por'

    def get_numero(self, obj):
        return obj.numero

    get_numero.admin_order_field = 'numero'
    get_numero.short_description = 'Nº da Requisição'

    def get_tabs(self, request):
        return [
            'tab_aguardando_aprovacao_gestor_ua',
            'tab_aguardando_aprovacao_gestor_ua_recebedora',
            'tab_cancelada',
            'tab_indeferida',
            'tab_deferida',
        ]

    def tab_aguardando_aprovacao_gestor_ua(self, request, queryset):
        return queryset.filter(status=RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE)

    tab_aguardando_aprovacao_gestor_ua.short_description = 'Aguardando Aprovação do Gestor de UA Concedente'

    def tab_aguardando_aprovacao_gestor_ua_recebedora(self, request, queryset):
        return queryset.filter(status=RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_RECEBEDORA)

    tab_aguardando_aprovacao_gestor_ua_recebedora.short_description = 'Aguardando Aprovação do Gestor de UA Recebedora'

    def tab_deferida(self, request, queryset):
        return queryset.filter(status=RequisicaoRealocacao.STATUS_DEFERIDA)

    tab_deferida.short_description = 'Deferida'

    def tab_indeferida(self, request, queryset):
        return queryset.filter(status=RequisicaoRealocacao.STATUS_INDEFERIDA)

    tab_indeferida.short_description = 'Indeferida'

    def tab_cancelada(self, request, queryset):
        return queryset.filter(status=RequisicaoRealocacao.STATUS_CANCELADA)

    tab_cancelada.short_description = 'Cancelada'

    def has_add_permission(self, request):
        # Evitar uso para super usuários, já que nenhum grupo tem a permissão add_requisicao.
        return False


admin.site.register(RequisicaoRealocacao, RequisicaoRealocacaoAdmin)


class OrigemRecursoFilter(SimpleListFilter):
    title = _('Origem de recurso')
    parameter_name = 'origem_recurso'

    def lookups(self, request, model_admin):
        origens_recurso = model_admin.get_queryset(request).values_list('origem_recurso_id', flat=True).distinct()
        origens = OrigemRecursoProjeto.objects.filter(pk__in=origens_recurso)
        return [
            (
                str(origem.pk),
                str(origem),
            )
            for origem in origens
            if origem is not None
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(origem_recurso=self.value())
        return queryset


class UnidadeRecebedoraFilter(admin.SimpleListFilter):
    title = 'Unidade recebedora'
    parameter_name = 'unidade_recebedora'

    def lookups(self, request, model_admin):
        qs = UnidadeGestora.objects.filter(unidade__isnull=False).distinct().order_by('setor_equivalente')
        return [(ug.pk, str(ug)) for ug in qs]

    def queryset(self, request, queryset):
        unidade_id = self.value()
        if not unidade_id:
            return queryset
        return queryset.filter(movimentacaocreditounidade__unidade_id=unidade_id).distinct()


class MovimentacaoCreditoAdmin(ModelAdminPlus):
    list_display = ('get_numero', 'get_status', 'get_tipo', 'get_data_cadastro', 'get_usuario')
    list_display_icons = True
    list_per_page = 20
    date_hierarchy = 'data_cadastro'
    show_count_on_tabs = True
    list_filter = (
        CustomTabListFilter,
        'numero',
        'tipo_requisicao',
        'projeto_estrategico__projeto',
        OrigemRecursoFilter,
        'plano_interno',
        UnidadeRecebedoraFilter,
        AnoPlanoAtividadeFilter,
    )

    def get_status(self, obj):
        return mark_safe(obj.get_status())

    get_status.admin_order_field = 'status'
    get_status.short_description = 'Situação'

    def get_data_cadastro(self, obj):
        return obj.data_cadastro.strftime('%d/%m/%Y %H:%M:%S')

    get_data_cadastro.admin_order_field = 'data_cadastro'
    get_data_cadastro.short_description = 'Data do cadastro'

    def get_usuario(self, obj):
        return obj.usuario

    get_usuario.admin_order_field = 'usuario'
    get_usuario.short_description = 'Cadastrado por'

    def get_numero(self, obj):
        return obj.numero

    get_numero.admin_order_field = 'numero'
    get_numero.short_description = 'Nº da requisição'

    def get_tipo(self, obj):
        return obj.get_tipo_requisicao_display()

    get_tipo.admin_order_field = 'tipo'
    get_tipo.short_description = 'Tipo'

    def has_add_permission(self, request):
        # Evitar uso para super usuários, já que nenhum grupo tem a permissão add_requisicao.
        return False

    def get_tabs(self, request):
        return [
            'tab_aguardando_analise_gos',
            'tab_aguardando_ciencia_gestor_macroprocesso',
            'tab_rejeitada',
            'tab_aguardando_validacao_sistema',
            'tab_inconsistentes',
            'tab_cancelada',
            'tab_concluida',
        ]

    def tab_aguardando_analise_gos(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_AGUARDANDO_ANALISE_GOS)

    tab_aguardando_analise_gos.short_description = 'Aguardando análise do Gestor Orçamentário'

    def tab_aguardando_ciencia_gestor_macroprocesso(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_AGUARDANDO_CIENCIA_GESTOR_MACROPROCESSO)

    tab_aguardando_ciencia_gestor_macroprocesso.short_description = 'Indeferida - Aguardando ciência do Gestor de Macroprocesso'

    def tab_rejeitada(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_REJEITADA)

    tab_rejeitada.short_description = 'Indeferida - Gestor de Macroprocesso Ciente'

    def tab_aguardando_validacao_sistema(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_AGUARDANDO_VALIDACAO_SISTEMA)

    tab_aguardando_validacao_sistema.short_description = 'Aguardando validação do SIAFI'

    def tab_inconsistentes(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_INCONSISTENTE)

    tab_inconsistentes.short_description = 'Inconsistentes'

    def tab_concluida(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_CONCLUIDA)

    tab_concluida.short_description = 'Concluídas'

    def tab_cancelada(self, request, queryset):
        return queryset.filter(status=MovimentacaoCredito.STATUS_CANCELADA)

    tab_cancelada.short_description = 'Canceladas'


admin.site.register(MovimentacaoCredito, MovimentacaoCreditoAdmin)


class RequisicaoDespesaAdmin(ModelAdminPlus):
    list_display = ('get_numero', 'get_status', 'get_tipo', 'get_unidadegestora', 'get_data_cadastro', 'get_usuario')
    list_display_icons = True
    list_per_page = 20
    date_hierarchy = 'data_cadastro'
    show_count_on_tabs = True
    list_filter = (
        CustomTabListFilter,
        'numero',
        'tipo_requisicao',
        'macroprocesso__projeto',
        OrigemRecursoFilter,
        'atividade',
        'unidade_gestora',
        AnoPlanoAtividadeFilter,
    )

    def get_status(self, obj):
        return mark_safe(obj.get_status())

    get_status.admin_order_field = 'status'
    get_status.short_description = 'Situação'

    def get_data_cadastro(self, obj):
        return obj.data_cadastro.strftime('%d/%m/%Y %H:%M:%S')

    get_data_cadastro.admin_order_field = 'data_cadastro'
    get_data_cadastro.short_description = 'Data do cadastro'

    def get_usuario(self, obj):
        return obj.usuario

    get_usuario.admin_order_field = 'usuario'
    get_usuario.short_description = 'Cadastrado por'

    def get_numero(self, obj):
        return obj.numero

    get_numero.admin_order_field = 'numero'
    get_numero.short_description = 'Nº da requisição'

    def get_unidadegestora(self, obj):
        if obj.unidade_gestora:
            return obj.unidade_gestora.setor_equivalente
        return None

    get_unidadegestora.admin_order_field = 'unidade_gestora'
    get_unidadegestora.short_description = 'Unidade Gestora'

    def get_macroprocesso(self, obj):
        return obj.macroprocesso

    get_macroprocesso.admin_order_field = 'macroprocesso'
    get_macroprocesso.short_description = 'Macroprocesso'

    def get_tipo(self, obj):
        return obj.get_tipo_requisicao_display()

    get_tipo.admin_order_field = 'tipo'
    get_tipo.short_description = 'Tipo'

    def has_add_permission(self, request):
        # Evitar uso para super usuários, já que nenhum grupo tem a permissão add_requisicao.
        return False

    def get_tabs(self, request):
        return [
            'tab_cadastrada',
            'tab_aguardando_emissao_cdo',
            'tab_aguardando_anuencia',
            'tab_aguardando_autorizacao',
            'tab_aguardando_emissao_empenho',
            'tab_aguardando_processo_licitatorio',
            'tab_aguardando_validacao',
            'tab_inconsistentes',
            'tab_concluidas',
            'tab_canceladas',
        ]

    def tab_cadastrada(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_CADASTRADA)

    tab_cadastrada.short_description = 'Cadastradas'

    def tab_aguardando_emissao_cdo(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_CDO)

    tab_aguardando_emissao_cdo.short_description = 'Aguardando emissão CDO'

    def tab_aguardando_anuencia(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA)

    tab_aguardando_anuencia.short_description = 'Aguardando anuência'

    def tab_aguardando_autorizacao(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO)

    tab_aguardando_autorizacao.short_description = 'Aguardando autorização'

    def tab_aguardando_emissao_empenho(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO)

    tab_aguardando_emissao_empenho.short_description = 'Aguardando emissão de empenho'

    def tab_aguardando_processo_licitatorio(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_PROCESSO_LICITATORIO)

    tab_aguardando_processo_licitatorio.short_description = 'Aguardando processo licitatório'

    def tab_aguardando_validacao(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)

    tab_aguardando_validacao.short_description = 'Aguardando validação do SIAFI'

    def tab_inconsistentes(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_INCONSISTENTE)

    tab_inconsistentes.short_description = 'Inconsistentes'

    def tab_concluidas(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_CONCLUIDA)

    tab_concluidas.short_description = 'Concluídas'

    def tab_canceladas(self, request, queryset):
        return queryset.filter(status=RequisicaoDespesa.STATUS_CANCELADA)

    tab_canceladas.short_description = 'Canceladas'


admin.site.register(RequisicaoDespesa, RequisicaoDespesaAdmin)


class NotaEmpenhoAdmin(ModelAdminPlus):
    search_fields = ('numero_empenho',)
    list_display = ('numero_empenho', 'requisicao')
    list_display_icons = True


admin.site.register(NotaEmpenho, NotaEmpenhoAdmin)


class NotaCreditoAdmin(ModelAdminPlus):
    search_fields = ('numero', 'movimentacao__numero')
    list_display = (
        'get_movimentacao_numero',
        'get_tipo',
        'get_origem',
        'get_pi',
        'get_total_requisicao',
        'get_status_movimentacao',
        'numero',
        'valor',
    )
    list_filter = ('movimentacao__numero',)
    list_display_icons = True
    export_to_xls = True

    def get_status_movimentacao(self, obj):
        return mark_safe(obj.movimentacao.get_status())

    get_status_movimentacao.admin_order_field = 'situacao da RM'
    get_status_movimentacao.short_description = 'Situação da RM'

    def get_movimentacao_numero(self, obj):
        return mark_safe(obj.movimentacao.numero)

    get_movimentacao_numero.admin_order_field = 'RM'
    get_movimentacao_numero.short_description = 'RM'

    def get_origem(self, obj):
        return mark_safe(obj.movimentacao.origem_recurso)

    get_origem.admin_order_field = 'Origem de recurso'
    get_origem.short_description = 'Origem de recurso'

    def get_pi(self, obj):
        return mark_safe(obj.movimentacao.plano_interno)

    get_pi.admin_order_field = 'Plano interno'
    get_pi.short_description = 'Plano interno'

    def get_total_requisicao(self, obj):
        return mark_safe(obj.movimentacao.get_total_unidades())

    get_total_requisicao.admin_order_field = 'total'
    get_total_requisicao.short_description = 'Total da Requisição'

    def get_tipo(self, obj):
        return obj.movimentacao.get_tipo_requisicao_display()

    get_tipo.admin_order_field = 'tipo'
    get_tipo.short_description = 'Tipo'


admin.site.register(NotaCredito, NotaCreditoAdmin)


class NotaDotacaoAdmin(ModelAdminPlus):
    search_fields = ('numero', 'movimentacao__numero')
    list_display = (
        'get_movimentacao_numero',
        'get_tipo',
        'get_origem',
        'get_pi',
        'get_total_requisicao',
        'get_status_movimentacao',
        'unidade_atendida',
        'numero',
        'valor',
    )
    list_display_icons = True
    export_to_xls = True

    def get_status_movimentacao(self, obj):
        return mark_safe(obj.movimentacao.get_status())

    get_status_movimentacao.admin_order_field = 'situacao da RM'
    get_status_movimentacao.short_description = 'Situação da RM'

    def get_movimentacao_numero(self, obj):
        return mark_safe(obj.movimentacao.numero)

    get_movimentacao_numero.admin_order_field = 'RM'
    get_movimentacao_numero.short_description = 'RM'

    def get_origem(self, obj):
        return mark_safe(obj.movimentacao.origem_recurso)

    get_origem.admin_order_field = 'Origem de recurso'
    get_origem.short_description = 'Origem de recurso'

    def get_pi(self, obj):
        return mark_safe(obj.movimentacao.plano_interno)

    get_pi.admin_order_field = 'Plano interno'
    get_pi.short_description = 'Plano interno'

    def get_total_requisicao(self, obj):
        return mark_safe(obj.movimentacao.get_total_unidades())

    get_total_requisicao.admin_order_field = 'total'
    get_total_requisicao.short_description = 'Total da RM'

    def get_tipo(self, obj):
        return obj.movimentacao.get_tipo_requisicao_display()

    get_tipo.admin_order_field = 'tipo'
    get_tipo.short_description = 'Tipo'


admin.site.register(NotaDotacao, NotaDotacaoAdmin)
