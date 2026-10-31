import datetime
import operator
from functools import reduce

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import format_html

from djtools.contrib.admin import ModelAdminPlus, StackedInlinePlus, TabularInlinePlus
from djtools.forms import ReadOnlyField
from djtools.templatetags.filters import format_datetime
from licenca_capacitacao.forms import AnexosEditalForm, AnexosPedidoLicCapacitacaoSubmissaoForm
from licenca_capacitacao.models import (
    AnexosEdital,
    AnexosPedidoLicCapacitacaoSubmissao,
    CadastroDesistencia,
    CalculoAquisitivoUsofrutoServidorEdital,
    CalculosGeraisServidorEdital,
    CodigoAfastamentoCapacitacao,
    CodigoAfastamentoNaoContabilizaExercicio,
    CodigoLicencaCapacitacao,
    EditalLicCapacitacao,
    MotivoLicencaCapacitacao,
    PedidoLicCapacitacao,
    PedidoLicCapacitacaoServidor,
    PeriodoPedidoLicCapacitacao,
    ServidorDataInicioExercicioAjustada,
    SituacaoContabilizaExercicio,
    SolicitacaoAlteracaoDados,
    SolicitacaoAlteracaoDadosAdicionar,
    SolicitacaoAlteracaoDataInicioExercicio,
    SolicitacaoAlteracaoDataInicioExercicioAdicionar,
)
from licenca_capacitacao.utils import eh_servidor, get_e


class AnexosEditalLicCapacitacaoInline(StackedInlinePlus):
    model = AnexosEdital
    form = AnexosEditalForm


@admin.register(EditalLicCapacitacao)
class EditalLicCapacitacaoAdmin(ModelAdminPlus):
    list_display = ('ano', 'titulo', 'situacao_atual_html', 'ativo', 'get_periodo_inscricao', 'get_opcoes')
    list_display_icons = True
    ordering = ('ano', '-id')
    readonly_fields = ('ativo',)

    inlines = [AnexosEditalLicCapacitacaoInline]

    def get_periodo_inscricao(self, obj):
        if obj.periodo_submissao_inscricao_inicio and obj.periodo_submissao_inscricao_final:
            return format_html(
                f'{format_datetime(obj.periodo_submissao_inscricao_inicio)} a {format_datetime(obj.periodo_submissao_inscricao_final)}'
            )
        return '-'

    get_periodo_inscricao.short_description = 'Período de Inscrição'
    get_periodo_inscricao.admin_order_field = 'periodo_submissao_inscricao_inicio'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_edital_servidor', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Se for da gestao visualiza lista todos (inclusive os inativos)
        # Se nao for lista apenas os ativos
        if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
            qs = qs.filter(ativo=True)
        return qs

    def get_fieldsets(self, request, obj=None):
        fieldsets_geral = (
            (
                'Dados gerais',
                {
                    'fields': (
                        'ano',
                        'titulo',
                        'descricao',
                        'ativo',
                        'periodo_abrangencia_inicio',
                        'periodo_abrangencia_final',
                        'qtd_max_periodos_por_pedido',
                        'processamento_externo',
                        'bloqueia_pedido_servidor_nao_apto',
                    )
                },
            ),
            (
                'Calendário',
                {
                    'fields': (
                        'periodo_submissao_inscricao_inicio',
                        'periodo_submissao_inscricao_final',
                        'periodo_resultado_parcial_inicio',
                        'periodo_resultado_parcial_final',
                        'periodo_recurso_resultado_parcial_inicio',
                        'periodo_recurso_resultado_parcial_final',
                        'periodo_desistencia_inicio',
                        'periodo_desistencia_final',
                        'periodo_resultado_final_inicio',
                        'periodo_resultado_final_final',
                        'periodo_submissao_segunda_etapa_inicio',
                        'periodo_submissao_segunda_etapa_final',
                    )
                },
            ),
        )

        fieldsets_parametros = (
            (
                'Parâmetros',
                {
                    'fields': (
                        'total_taes_em_exercicio',
                        'total_docentes_em_exercicio',
                        'total_geral_em_exercicio',
                        'percentual_limite_servidores_em_lic_capacitacao',
                        'qtd_limite_servidores_em_lic_capacitacao_por_dia',
                        'qtd_limite_taes_em_lic_capacitacao_por_dia',
                        'qtd_limite_docentes_em_lic_capacitacao_por_dia',
                    )
                },
            ),
        )

        if not obj:
            fieldsets = fieldsets_geral
        else:
            fieldsets = fieldsets_geral + fieldsets_parametros

        return fieldsets

    def save_model(self, request, obj, form, change):
        # - parametros do edital
        #   - quando alterar os parametros deve dizer se ja tem submissoes cadastradas
        #   - se já existem sugere recalcular
        if change:
            if PedidoLicCapacitacao.get_pedidos_para_processamento(obj).exists():
                edital_dados_ant = EditalLicCapacitacao.objects.get(id=obj.id)
                if (
                    edital_dados_ant.percentual_limite_servidores_em_lic_capacitacao != obj.percentual_limite_servidores_em_lic_capacitacao
                    or edital_dados_ant.total_taes_em_exercicio != obj.total_taes_em_exercicio
                    or edital_dados_ant.total_docentes_em_exercicio != obj.total_docentes_em_exercicio
                    or edital_dados_ant.total_geral_em_exercicio != obj.total_geral_em_exercicio
                    or edital_dados_ant.qtd_limite_servidores_em_lic_capacitacao_por_dia != obj.qtd_limite_servidores_em_lic_capacitacao_por_dia
                    or edital_dados_ant.qtd_limite_taes_em_lic_capacitacao_por_dia != obj.qtd_limite_taes_em_lic_capacitacao_por_dia
                    or edital_dados_ant.qtd_limite_docentes_em_lic_capacitacao_por_dia != obj.qtd_limite_docentes_em_lic_capacitacao_por_dia
                ):
                    messages.error(
                        request,
                        format_html(
                            'Você alterou um mais parâmetros do edital que podem influênciar no resultado Parcial ou Final. <b>Considere recalcular parâmetros do edital e os processamentos.</b>'
                        ),
                    )

        ret = super().save_model(request, obj, form, change)

        if not change:
            EditalLicCapacitacao.calcular_parametros(obj)

        return ret

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        if EditalLicCapacitacao.eh_perfil_gestao(self.request.user):
            texto += '<li><a href="{}" class="btn default">Visualizar como Gestão</a></li>'.format(reverse('visualizar_edital_gestao', args=[obj.id]))
        texto += '</ul>'
        return format_html(texto)

    get_opcoes.short_description = 'Opções'

    def changelist_view(self, request, extra_context=None):
        if EditalLicCapacitacao.eh_perfil_gestao(request.user):
            self.list_display = ('id', 'ano', 'titulo', 'situacao_atual_html', 'ativo', 'get_periodo_inscricao', 'get_opcoes')
        else:
            self.list_display = ('id', 'ano', 'titulo', 'situacao_atual_html', 'ativo', 'get_periodo_inscricao')
        return super().changelist_view(request, extra_context)


@admin.register(MotivoLicencaCapacitacao)
class MotivoLicencaCapacitacaoAdmin(ModelAdminPlus):
    pass


class PeriodoPedidoInline(TabularInlinePlus):
    model = PeriodoPedidoLicCapacitacao
    exclude = ('aquisitivo_uso_fruto', 'qtd_dias_total')

    def get_max_num(self, request, obj=None, **kwargs):
        if request.GET.get('edital'):
            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
        else:
            edital = obj.edital
        return edital.qtd_max_periodos_por_pedido

    def has_delete_permission(self, request, obj=None):
        retorno = super().has_delete_permission(request, obj)
        if request.GET.get('edital'):
            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
        else:
            edital = obj.edital
        if edital.qtd_max_periodos_por_pedido == 1:
            return False
        return retorno


class AnexosPedidoLicCapacitacaoSubmissaoInline(StackedInlinePlus):
    model = AnexosPedidoLicCapacitacaoSubmissao
    form = AnexosPedidoLicCapacitacaoSubmissaoForm


class PedidoLicCapacitacaoCategoriaFilter(admin.SimpleListFilter):
    title = 'Categoria'
    parameter_name = 'fc'

    def lookups(self, request, model_admin):
        return [('docente', 'Docente'), ('tecnico_administrativo', 'Técnico-Administrativo')]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'docente':
                return queryset.filter(eh_docente=True)
            elif self.value() == 'tecnico_administrativo':
                return queryset.filter(eh_tecnico_administrativo=True)


class PedidoLicCapacitacaoSituacaoPedidoFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'agp'

    def lookups(self, request, model_admin):
        return [('todos', 'Todos'), ('para_processamento', 'Apenas os aptos para processamento'), ('todos_submetidos', 'Todos os submetidos')]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'todos':
                return queryset.all()
            elif self.value() == 'para_processamento':
                return queryset.filter(id__in=PedidoLicCapacitacao.get_pedidos_para_processamento().values_list('id'))
            elif self.value() == 'todos_submetidos':
                return queryset.filter(id__in=PedidoLicCapacitacao.get_pedidos_submetidos().values_list('id'))


@admin.register(PedidoLicCapacitacao)
class PedidoLicCapacitacaoAdmin(ModelAdminPlus):
    change_form_template = 'licenca_capacitacao/templates/admin/change_form_pedidoliccapacitacao.html'
    change_list_template = 'licenca_capacitacao/templates/admin/change_list_sem_add.html'

    inlines = [PeriodoPedidoInline]  # , AnexosPedidoLicCapacitacaoSubmissaoInline]

    list_display = (
        'get_edital_servidor',
        'get_categoria',
        'get_situacao_atual_html',
        'get_lista_periodos_pedido_html',
        'aprovado_resultado_parcial',
        'ordem_classificacao_resultado_parcial',
        'aprovado_resultado_final',
        'ordem_classificacao_resultado_final',
        'aprovado_em_definitivo',
        'desistencia',
        'cancelado_pela_gestao',
    )

    list_display_icons = True

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')
    list_filter = (
        PedidoLicCapacitacaoSituacaoPedidoFilter,
        'edital',
        'desistencia',
        PedidoLicCapacitacaoCategoriaFilter,
        'servidor__setor__uo',
        'cancelado_pela_gestao',
    )
    preserve_filters = True

    fieldsets = (
        (
            'Dados Básicos do Pedido',
            {
                'fields': (
                    'edital',
                    'servidor',
                    'motivo',
                    'modalidade',
                    'carga_horaria',
                    'cnpj_instituicao',
                    (
                        'instituicao',
                        'local',
                    ),
                    (
                        'despesa_custeio',
                        'despesa_custeio_origem',
                    ),
                    (
                        'custos_diarias_passagens',
                        'custos_diarias_passagens_origem',
                    ),
                    'acao',
                    'outros_detalhes',
                )
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if not obj:
            form.base_fields['servidor'].initial = request.user.get_relacionamento()
            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))

            form.base_fields['servidor'] = ReadOnlyField(label='Servidor')
            form.base_fields['servidor'].initial = request.user.get_relacionamento()
            form.base_fields['servidor'].widget.display_value = request.user.get_relacionamento()

            form.base_fields['edital'] = ReadOnlyField(label='Edital')
            form.base_fields['edital'].widget.display_value = str(edital)
            form.base_fields['edital'].initial = edital

        return form

    def has_add_permission(self, request):
        super().has_add_permission(request)
        # Somente servidor
        try:
            if request.GET.get('edital'):
                edital = EditalLicCapacitacao.objects.get(pk=request.GET.get('edital'))
                return edital.pode_cadastrar_pedido(user=request.user)
        except Exception:
            pass
        return False

    def has_change_permission(self, request, obj=None):
        super().has_change_permission(request, obj=obj)
        # Somente servidor
        if obj and obj.edital:
            servidor_pode = obj.pode_editar(user=request.user)
            if not servidor_pode:
                if obj.pode_visualizar(user=request.user):
                    return HttpResponseRedirect(f'/licenca_capacitacao/visualizar_pedido_servidor/{obj.id}')
                else:
                    return False
        return True

    def has_view_permission(self, request, obj=None):
        super().has_view_permission(request, obj=obj)
        # Somente gestao
        return EditalLicCapacitacao.eh_perfil_gestao(request.user)

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_pedido_gestao', args=[obj_pk]))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # Apenas servidor
        pedido = PedidoLicCapacitacao.objects.get(id=object_id)

        extra_context = extra_context or {}
        extra_context['title'] = f'Pedido de Licença Capacitação ao {pedido.edital} - {pedido.servidor}'

        extra_context['pode_submeter'] = pedido.pode_submeter(request.user)
        extra_context['pode_desfazer_submissao'] = pedido.pode_desfazer_submissao(request.user)
        extra_context['pode_cancelar'] = pedido.pode_cancelar(request.user)
        extra_context['pode_descancelar'] = pedido.pode_descancelar(request.user)

        extra_context['pedido'] = pedido

        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        # Somente gestao
        if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
            raise PermissionDenied
        extra_context = extra_context or {}
        extra_context['title'] = 'Lista de Pedidos de Licença Capacitação'
        return super().changelist_view(request, extra_context)

    def response_change(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_pedido_servidor', args=[obj.id]))

    def response_add(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_pedido_servidor', args=[obj.id]))

    def get_edital_servidor(self, obj):
        return format_html(f'{obj.servidor}<br><i>{obj.edital}</i>')

    get_edital_servidor.short_description = 'Edital/Servidor'

    def get_situacao_atual_html(self, obj):
        return obj.situacao_atual_html

    get_situacao_atual_html.short_description = 'Situação atual'

    def get_lista_periodos_pedido_html(self, obj):
        return obj.get_lista_periodos_pedido_html()

    get_lista_periodos_pedido_html.short_description = 'Parcelas'

    def get_categoria(self, obj):
        if obj.eh_tecnico_administrativo:
            return 'Técnico-Administrativo'
        elif obj.eh_docente:
            return 'Docente'
        else:
            return 'Indefinido'

    get_categoria.short_description = 'Categoria'

    def get_queryset(self, request):
        # Apenas os pedidos que foram submetidos
        qs = super().get_queryset(request)
        # if not request.user.is_superuser:
        #    qs = qs.filter(id__in=PedidoLicCapacitacao.get_pedidos_para_processamento(None).values_list('id', flat=True))
        return qs


@admin.register(PedidoLicCapacitacaoServidor)
class PedidoLicCapacitacaoServidorAdmin(ModelAdminPlus):
    change_form_template = 'licenca_capacitacao/templates/admin/change_form_pedidoliccapacitacao.html'
    change_list_template = 'licenca_capacitacao/templates/admin/change_list_sem_add.html'

    inlines = [PeriodoPedidoInline]  # , AnexosPedidoLicCapacitacaoSubmissaoInline]

    list_display = (
        'get_edital_servidor',
        'get_situacao_atual_html',
        'get_lista_periodos_pedido_html',
        'aprovado_resultado_parcial',
        'ordem_classificacao_resultado_parcial',
        'aprovado_resultado_final',
        'ordem_classificacao_resultado_final',
        'aprovado_em_definitivo',
        'desistencia',
    )

    list_display_icons = True

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')
    list_filter = ('edital',)
    preserve_filters = True

    fieldsets = (
        (
            'Dados Básicos do Pedido',
            {
                'fields': (
                    'edital',
                    'servidor',
                    'motivo',
                    'modalidade',
                    'carga_horaria',
                    'cnpj_instituicao',
                    (
                        'instituicao',
                        'local',
                    ),
                    (
                        'despesa_custeio',
                        'despesa_custeio_origem',
                    ),
                    (
                        'custos_diarias_passagens',
                        'custos_diarias_passagens_origem',
                    ),
                    'acao',
                    'outros_detalhes',
                )
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        form.base_fields['outros_detalhes'].widget.attrs.update(
            {
                'placeholder': 'Favor preencher com informações sobre a "Descrição sucinta dos objetivos do seu setor" e "Descrição sucinta das suas atividades".'
            }
        )

        if not obj:
            form.base_fields['servidor'].initial = request.user.get_relacionamento()
            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))

            form.base_fields['servidor'] = ReadOnlyField(label='Servidor')
            form.base_fields['servidor'].initial = request.user.get_relacionamento()
            form.base_fields['servidor'].widget.display_value = request.user.get_relacionamento()

            form.base_fields['edital'] = ReadOnlyField(label='Edital')
            form.base_fields['edital'].widget.display_value = str(edital)
            form.base_fields['edital'].initial = edital

        return form

    def has_add_permission(self, request):
        # Somente servidor
        try:
            if request.GET.get('edital'):
                edital = EditalLicCapacitacao.objects.get(pk=request.GET.get('edital'))
                return edital.pode_cadastrar_pedido(user=request.user)
        except Exception:
            pass
        return False

    def has_change_permission(self, request, obj=None):
        # Somente servidor
        if obj and obj.edital:
            return obj.pode_editar(user=request.user)
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # Apenas servidor
        pedido = PedidoLicCapacitacao.objects.get(id=object_id)

        extra_context = extra_context or {}
        extra_context['title'] = f'Pedido de Licença Capacitação ao {pedido.edital} - {pedido.servidor}'

        extra_context['pode_submeter'] = pedido.pode_submeter(request.user)
        extra_context['pode_desfazer_submissao'] = pedido.pode_desfazer_submissao(request.user)
        extra_context['pode_cancelar'] = pedido.pode_cancelar(request.user)
        extra_context['pode_descancelar'] = pedido.pode_descancelar(request.user)

        extra_context['pedido'] = pedido

        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        # Somente gestao
        if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
            raise PermissionDenied
        extra_context = extra_context or {}
        extra_context['title'] = 'Lista de Pedidos de Licença Capacitação'
        return super().changelist_view(request, extra_context)

    def response_change(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_pedido_servidor', args=[obj.id]))

    def response_add(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_pedido_servidor', args=[obj.id]))

    def get_edital_servidor(self, obj):
        return format_html(f'{obj.servidor}<br><i>{obj.edital}</i>')

    get_edital_servidor.short_description = 'Edital/Servidor'

    def get_situacao_atual_html(self, obj):
        return obj.situacao_atual_html

    get_situacao_atual_html.short_description = 'Situação atual'

    def get_lista_periodos_pedido_html(self, obj):
        return obj.get_lista_periodos_pedido_html()

    get_lista_periodos_pedido_html.short_description = 'Parcelas'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not eh_servidor(request.user):
            return qs
        qs = qs.filter(servidor=request.user.get_relacionamento())
        return qs


@admin.register(PeriodoPedidoLicCapacitacao)
class PeriodoPedidoLicCapacitacaoAdmin(ModelAdminPlus):
    list_display = ('pedido', 'data_inicio', 'data_termino', 'qtd_dias_total')
    list_filter = ('pedido__edital',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not EditalLicCapacitacao.eh_perfil_gestao(request.user):
            raise PermissionDenied
        extra_context = extra_context or {}
        extra_context['title'] = 'Lista de Pedidos e Parcelas de Licença Capacitação'
        return super().changelist_view(request, extra_context)


@admin.register(CalculoAquisitivoUsofrutoServidorEdital)
class CalculoAquisitivoUsofrutoServidorEditalAdmin(ModelAdminPlus):
    list_display = ('get_edital_servidor', 'inicio_aquisitivo', 'final_aquisitivo_na_patrica', 'ativo_pelo_edital')
    list_filter = ('edital', 'servidor')
    list_display_icons = True
    readonly_fields = ('edital', 'servidor')

    def get_edital_servidor(self, obj):
        return format_html(f'{obj.servidor}<br><i>{obj.edital}</i>')

    get_edital_servidor.short_description = 'Edital/Servidor'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # So altera se for da gestao e o pedido tiver processamento que possa ser alterado
        gestao = False
        if obj and obj.edital:
            gestao = CalculoAquisitivoUsofrutoServidorEdital.pode_editar(request.user, obj.edital, False)
        return gestao

    def has_view_permission(self, request, obj=None):
        return EditalLicCapacitacao.eh_perfil_gestao(request.user)

    def get_queryset(self, request):
        # Apenas os pedidos que foram submetidos
        qs = super().get_queryset(request)
        qs = qs.filter(ativo_pelo_edital=True)
        queues = [
            Q(edital=ed, servidor=se)
            for ed, se in PedidoLicCapacitacao.objects.filter(situacao=PedidoLicCapacitacao.SUBMETIDO).values_list('edital', 'servidor')
        ]
        query = reduce(operator.or_, queues)
        return qs.filter(query).distinct()


@admin.register(CalculosGeraisServidorEdital)
class CalculosGeraisServidorEditalAdmin(ModelAdminPlus):
    list_display = ('get_edital_servidor', 'inicio_exercicio')
    list_filter = ('edital', 'servidor')
    list_display_icons = True
    readonly_fields = ('edital', 'servidor')

    def get_edital_servidor(self, obj):
        return format_html(f'{obj.servidor}<br><i>{obj.edital}</i>')

    get_edital_servidor.short_description = 'Edital/Servidor'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # So altera se for da gestao e o pedido tiver processamento que possa ser alterado
        gestao = False
        if obj and obj.edital:
            gestao = CalculosGeraisServidorEdital.pode_editar(request.user, obj.edital, False)
        return gestao

    def has_view_permission(self, request, obj=None):
        return EditalLicCapacitacao.eh_perfil_gestao(request.user)

    def get_queryset(self, request):
        # Apenas os pedidos que foram submetidos
        qs = super().get_queryset(request)
        calculos_que_podem_ser_alterados = []
        calculos = qs
        servidores_calculo = qs.values_list('edital', 'servidor', named=True).distinct()
        for c in servidores_calculo:
            if EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(c.edital, c.servidor):
                cl = calculos.filter(edital=c.edital, servidor=c.servidor)
                for e in cl:
                    calculos_que_podem_ser_alterados.append(e.id)
        if calculos_que_podem_ser_alterados:
            qs = qs.filter(id__in=calculos_que_podem_ser_alterados)
        else:
            return CalculosGeraisServidorEdital.objects.none()
        return qs


@admin.register(SolicitacaoAlteracaoDataInicioExercicio)
class SolicitacaoAlteracaoDataInicioExercicioAdmin(ModelAdminPlus):
    # Utilizado apenas pela Gestão

    list_display = (
        'id',
        'edital',
        'servidor',
        'data_cadastro',
        'get_situacao_display',
        'data_suap',
        'justificativa',
        'data_solicitada',
        'parecer_gestao',
        'data_hora_parecer',
        'usuario_parecer',
    )

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')
    list_filter = ('edital',)

    list_display_icons = True

    change_form_template = 'licenca_capacitacao/templates/admin/change_form_analisa_pedido_dt_ini.html'
    change_list_template = 'licenca_capacitacao/templates/admin/change_list_sem_add.html'

    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor', 'data_cadastro')}),
        ('Solicitação do servidor', {'fields': ('justificativa', 'data_suap', 'data_solicitada')}),
        (
            'Parecer da gestão',
            {
                'fields': (
                    'situacao',
                    'usuario_parecer',
                    'data_informada_parecer',
                    'parecer_gestao',
                )
            },
        ),
    )

    def get_situacao_display(self, obj):
        return obj.get_situacao_html()

    get_situacao_display.short_description = 'Situação'

    def get_readonly_fields(self, request, obj=None):
        return ('edital', 'servidor', 'justificativa', 'data_suap', 'data_solicitada', 'data_cadastro')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Analisar solicitação de alteração de data de início de exercício'
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        try:
            edital = EditalLicCapacitacao.objects.get(id=request.GET.get('edital__id__exact'))
            SolicitacaoAlteracaoDataInicioExercicio.pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(request.user, edital, True)
        except Exception as e:
            messages.error(request, get_e(e))
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        obj.usuario_parecer = request.user
        obj.data_hora_parecer = datetime.datetime.now()
        return super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['usuario_parecer'] = ReadOnlyField(label='Usuário do parecer')
        form.base_fields['usuario_parecer'].initial = request.user
        form.base_fields['usuario_parecer'].widget.display_value = str(request.user)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(pode_analisar=True)
        return qs

    def has_change_permission(self, request, obj=None):
        if obj and obj.edital:
            return SolicitacaoAlteracaoDataInicioExercicio.pode_analisar_solicitacao_alteracao_dt_inicio_exercicio(request.user, obj.edital, False)
        return False

    def response_change(self, request, obj):
        if 'url' in request.GET:
            return HttpResponseRedirect(request.GET.get('url'))
        return super().response_change(request, obj)


@admin.register(SolicitacaoAlteracaoDataInicioExercicioAdicionar)
class SolicitacaoAlteracaoDataInicioExercicioAdicionarAdmin(ModelAdminPlus):
    # Utilizado apenas pelo Servidor

    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor', 'data_suap')}),
        ('Solicitação do servidor', {'fields': ('justificativa', 'data_solicitada')}),
    )

    def has_add_permission(self, request):
        try:
            if request.GET.get('edital'):
                edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
                return SolicitacaoAlteracaoDataInicioExercicioAdicionar.pode_solicitar(request.user, edital, False)
        except Exception:
            return False
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if request.GET.get('edital') and not obj:
            servidor = request.user.get_relacionamento()
            form.base_fields['servidor'] = ReadOnlyField(label='Servidor')
            form.base_fields['servidor'].initial = servidor
            form.base_fields['servidor'].widget.display_value = str(servidor)

            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
            form.base_fields['edital'] = ReadOnlyField(label='Edital')
            form.base_fields['edital'].initial = edital
            form.base_fields['edital'].widget.display_value = str(edital)

            calculos = CalculosGeraisServidorEdital.objects.filter(edital=edital, servidor=servidor)[0]
            form.base_fields['data_suap'] = ReadOnlyField(label='Data obtida pelo módulo de licença capacitação')
            form.base_fields['data_suap'].initial = calculos.inicio_exercicio
            form.base_fields['data_suap'].widget.display_value = format_datetime(calculos.inicio_exercicio)

        return form

    def response_add(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_edital_servidor', args=[obj.edital.id]))


@admin.register(SolicitacaoAlteracaoDados)
class SolicitacaoAlteracaoDadosAdmin(ModelAdminPlus):
    # Utilizado apenas pela Gestão

    list_display = (
        'id',
        'edital',
        'servidor',
        'data_cadastro',
        'get_situacao_display',
        'justificativa',
        'parecer_gestao',
        'data_hora_parecer',
        'usuario_parecer',
    )

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')
    list_filter = ('edital',)

    list_display_icons = True

    change_list_template = 'licenca_capacitacao/templates/admin/change_list_sem_add.html'

    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor', 'data_cadastro')}),
        ('Solicitação do servidor', {'fields': ('justificativa',)}),
        (
            'Parecer da gestão',
            {
                'fields': (
                    'situacao',
                    'usuario_parecer',
                    'parecer_gestao',
                )
            },
        ),
    )

    def get_situacao_display(self, obj):
        return obj.get_situacao_html()

    get_situacao_display.short_description = 'Situação'

    def get_readonly_fields(self, request, obj=None):
        return ('edital', 'servidor', 'justificativa', 'data_cadastro')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Analisar solicitação de alteração de dados'
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        try:
            edital = EditalLicCapacitacao.objects.get(id=request.GET.get('edital__id__exact'))
            SolicitacaoAlteracaoDados.pode_analisar_solicitacao_alteracao(request.user, edital, True)
        except Exception as e:
            messages.error(request, get_e(e))
        return super().changelist_view(request, extra_context)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['usuario_parecer'] = ReadOnlyField(label='Usuário do parecer')
        form.base_fields['usuario_parecer'].initial = request.user
        form.base_fields['usuario_parecer'].widget.display_value = str(request.user)
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(pode_analisar=True)
        return qs

    def has_change_permission(self, request, obj=None):
        if obj and obj.edital:
            return SolicitacaoAlteracaoDados.pode_analisar_solicitacao_alteracao(request.user, obj.edital, False)
        return False

    def save_model(self, request, obj, form, change):
        obj.usuario_parecer = request.user
        obj.data_hora_parecer = datetime.datetime.now()
        return super().save_model(request, obj, form, change)


@admin.register(SolicitacaoAlteracaoDadosAdicionar)
class SolicitacaoAlteracaoDadosAdicionarAdmin(ModelAdminPlus):
    # Utilizado apenas pelo Servidor

    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor')}),
        ('Solicitação do servidor', {'fields': ('justificativa',)}),
    )

    def has_add_permission(self, request):
        try:
            if request.GET.get('edital'):
                edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
                return SolicitacaoAlteracaoDadosAdicionar.pode_solicitar(request.user, edital, False)
        except Exception:
            return False
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if request.GET.get('edital') and not obj:
            servidor = request.user.get_relacionamento()
            form.base_fields['servidor'] = ReadOnlyField(label='Servidor')
            form.base_fields['servidor'].initial = servidor
            form.base_fields['servidor'].widget.display_value = str(servidor)

            edital = get_object_or_404(EditalLicCapacitacao, pk=request.GET.get('edital'))
            form.base_fields['edital'] = ReadOnlyField(label='Edital')
            form.base_fields['edital'].initial = edital
            form.base_fields['edital'].widget.display_value = str(edital)

        return form

    def response_add(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_edital_servidor', args=[obj.edital.id]))


class CadastroDesistenciaExisteSolicitacaoFilter(admin.SimpleListFilter):
    title = 'Apenas pedidos com solicitação de desistência'
    parameter_name = 'pcsd'

    def lookups(self, request, model_admin):
        return [('Sim', 'Sim'), ('Não', 'Não')]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'Sim':
                return queryset.filter(data_solicitacao_desistencia__isnull=False)
            elif self.value() == 'Não':
                return queryset.filter(data_solicitacao_desistencia__isnull=True)


@admin.register(CadastroDesistencia)
class CadastroDesistenciaAdmin(ModelAdminPlus):
    # TODO Cadastro de desistencia
    # A solicitação de desistência não será utilizada neste primeiro edital
    # - Estamos retirando/ocultando os dados referentes a solicitação
    # - Este fluxo será revisado durante a segunda fase de homologação conforme demanda 1027

    """
    list_display = ('get_edital_servidor', 'get_situacao_atual_html', 'get_lista_periodos_pedido_html',
                    'aprovado_resultado_parcial', 'ordem_classificacao_resultado_parcial',
                    'aprovado_resultado_final', 'ordem_classificacao_resultado_final',
                    'aprovado_em_definitivo',
                    'get_solicitou_desistencia', 'desistencia')
    """

    list_display = (
        'get_edital_servidor',
        'get_situacao_atual_html',
        'get_lista_periodos_pedido_html',
        'aprovado_resultado_parcial',
        'ordem_classificacao_resultado_parcial',
        'aprovado_resultado_final',
        'ordem_classificacao_resultado_final',
        'aprovado_em_definitivo',
        'desistencia',
    )

    # list_filter = ('edital', CadastroDesistenciaExisteSolicitacaoFilter)
    list_filter = ('edital',)

    """
    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor', 'solicitacao_desistencia',
                                      'data_solicitacao_desistencia')}),
        ('Desistência', {'fields': ('parecer_desistencia', 'desistencia')}),
    )
    """
    fieldsets = (
        ('Dados básicos', {'fields': ('edital', 'servidor')}),
        ('Desistência', {'fields': ('parecer_desistencia', 'desistencia')}),
    )

    list_display_icons = True

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')

    def get_solicitou_desistencia(self, obj):
        return bool(obj.data_solicitacao_desistencia)

    get_solicitou_desistencia.short_description = 'Solicitou Desistência'
    get_solicitou_desistencia.boolean = True

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        # TODO Cadastro de desistencia
        # A solicitação de desistência não será utilizada neste primeiro edital
        # - Estamos retirando/ocultando os dados referentes a solicitação
        # - Este fluxo será revisado durante a segunda fase de homologação conforme demanda 1027

        form.base_fields['servidor'] = ReadOnlyField(label='Servidor')
        form.base_fields['servidor'].initial = obj.servidor
        form.base_fields['servidor'].widget.display_value = str(obj.servidor)

        form.base_fields['edital'] = ReadOnlyField(label='Edital')
        form.base_fields['edital'].initial = obj.edital
        form.base_fields['edital'].widget.display_value = str(obj.edital)

        # form.base_fields['solicitacao_desistencia'] = ReadOnlyField(label='Solicitação de desistência')
        # form.base_fields['solicitacao_desistencia'].initial = obj.solicitacao_desistencia
        # form.base_fields['solicitacao_desistencia'].widget.display_value = str(obj.solicitacao_desistencia) if obj.solicitacao_desistencia else '-'

        # form.base_fields['data_solicitacao_desistencia'] = ReadOnlyField(label='Data da Solicitação de desistência')
        # form.base_fields['data_solicitacao_desistencia'].initial = obj.data_solicitacao_desistencia
        # form.base_fields['data_solicitacao_desistencia'].widget.display_value = str(obj.data_solicitacao_desistencia) if obj.data_solicitacao_desistencia else '-'

        return form

    def response_change(self, request, obj):
        return HttpResponseRedirect(reverse('visualizar_edital_gestao', args=[obj.edital.id]))

    def get_edital_servidor(self, obj):
        return format_html(f'{obj.servidor}<br><i>{obj.edital}</i>')

    get_edital_servidor.short_description = 'Edital/Servidor'

    def get_situacao_atual_html(self, obj):
        return obj.situacao_atual_html

    get_situacao_atual_html.short_description = 'Situação atual'

    def get_lista_periodos_pedido_html(self, obj):
        return obj.get_lista_periodos_pedido_html()

    get_lista_periodos_pedido_html.short_description = 'Parcelas'

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if obj.desistencia:
            obj.usuario_cadastro_desistencia = request.user
            obj.data_parecer_desistencia = datetime.datetime.now()
        else:
            obj.usuario_cadastro_desistencia = None
            obj.data_parecer_desistencia = None

        try:
            CadastroDesistencia.pode_cadastrar(request.user, obj.edital, True)
        except Exception as e:
            messages.error(request, get_e(e))
            return HttpResponseRedirect(f'/licenca_capacitacao/visualizar_pedido_servidor/{obj.id}')

        return super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        # Apenas os pedidos que foram submetidos
        qs = super().get_queryset(request)
        qs = qs.filter(id__in=PedidoLicCapacitacao.get_pedidos_submetidos(None).values_list('id', flat=True))
        return qs

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Cadastrar desistência'
        return super().change_view(request, object_id, form_url, extra_context)


class PedidoLicCapacitacaoCategoriaFilter(admin.SimpleListFilter):
    title = 'Da'
    parameter_name = 'fc'

    def lookups(self, request, model_admin):
        return [('docente', 'Docente'), ('tecnico_administrativo', 'Técnico-Administrativo')]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'docente':
                return queryset.filter(eh_docente=True)
            elif self.value() == 'tecnico_administrativo':
                return queryset.filter(eh_tecnico_administrativo=True)


@admin.register(ServidorDataInicioExercicioAjustada)
class ServidorDataInicioExercicioAjustadaAdmin(ModelAdminPlus):
    list_display = ('servidor', 'data_do_ajuste', 'usuario_ajuste', 'data_inicio_exercicio', 'get_tem_solicitacao_vinculada')

    list_filter = ('servidor',)

    list_display_icons = True

    search_fields = ('servidor__matricula', 'servidor__pessoa_fisica__nome')

    def get_tem_solicitacao_vinculada(self, obj):
        return bool(obj.solicitacao_alteracao)

    get_tem_solicitacao_vinculada.short_description = 'Servidor solicitou alteração'
    get_tem_solicitacao_vinculada.boolean = True

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if not retorno:
            return False
        # Só altera se nao existe uma solicitacao_alteracao vinculada ao servidor
        return not (obj and obj.solicitacao_alteracao)

    def has_delete_permission(self, request, obj=None):
        retorno = super().has_delete_permission(request, obj)
        if not retorno:
            return False
        # Só deleta se nao existe uma solicitacao_alteracao vinculada ao servidor
        return bool(obj and not obj.solicitacao_alteracao)

    def save_model(self, request, obj, form, change):
        # So sera salvo por por este admin para os casos de o servidor nao ter feito uma solicitacao
        # - para os casos em que for feito diretamente pela gestao
        # - so pode haver uma data ajustada para o servidor (unique no model)

        obj.usuario_ajuste = request.user
        obj.data_do_ajuste = datetime.datetime.now()

        return super().save_model(request, obj, form, change)


@admin.register(CodigoLicencaCapacitacao)
class CodigoLicencaCapacitacaoAdmin(ModelAdminPlus):
    list_display = ('codigo',)

    list_display_icons = True


@admin.register(CodigoAfastamentoCapacitacao)
class CodigoAfastamentoCapacitacaoAdmin(ModelAdminPlus):
    list_display = ('codigo',)

    list_display_icons = True


@admin.register(CodigoAfastamentoNaoContabilizaExercicio)
class CodigoAfastamentoNaoContabilizaExercicioAdmin(ModelAdminPlus):
    list_display = ('codigo',)

    list_display_icons = True


@admin.register(SituacaoContabilizaExercicio)
class SituacaoContabilizaExercicioAdmin(ModelAdminPlus):
    list_display = ('codigo',)

    list_display_icons = True
