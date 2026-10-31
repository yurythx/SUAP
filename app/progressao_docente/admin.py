# Register your models here.
from datetime import date

from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin.filters import SimpleListFilter
from django.db.models import DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Extract
from django.forms import HiddenInput
from django.utils.safestring import mark_safe

from djtools.contrib.admin.filters import CustomTabListFilter, DateRangeListFilter
from djtools.contrib.admin.options import ModelAdminPlus
from djtools.templatetags.filters.utils import in_group
from djtools.utils import httprr
from progressao_docente.forms import AvaliacaoForm, DocenteAProgredirForm, ProgressaoDocenteForm
from progressao_docente.models import (
    Avaliacao,
    AvaliacaoItem,
    ConfiguracaoProgressaoDocente,
    Criterio,
    DiscenteAptosAvaliacao,
    DocenteAProgredir,
    Formulario,
    Item,
    PontuacaoItem,
    ProgressaoDocente,
)


@admin.register(ProgressaoDocente)
class ProgressaoDocenteAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('avaliado', 'get_periodo', 'get_nivel', 'get_situacao', 'get_prazo', 'get_resultado', 'get_acoes')
    list_filter = (
        CustomTabListFilter,
        'situacao',
        'avaliado__setor__uo',
        ('data_fim_periodo', DateRangeListFilter),
    )
    search_fields = ProgressaoDocente.SEARCH_FIELDS
    form = ProgressaoDocenteForm
    show_count_on_tabs = True
    export_to_xls = True

    def to_xls(self, request, queryset, task):
        header = ['#', 'Avaliado', 'Período', 'Níveis', 'Novo nível', 'Resultado Final']
        rows = [header]
        for idx, obj in enumerate(task.iterate(queryset)):
            #
            # nível
            nivel = f'{obj.nivel_atual} a {obj.proximo_nivel}'
            novo_nivel = ''
            dados_novo_padrao = obj._get_dados_novo_padrao()
            if dados_novo_padrao:
                padrao_anterior_reenq, padrao_novo_reenq = dados_novo_padrao
                novo_nivel = f'{padrao_anterior_reenq} a {padrao_novo_reenq}'
            #
            # resultado final
            resultado_final = 'Em andamento'
            if obj.situacao in [obj.FINALIZADO, obj.CIENTE_RESULTADO] and obj.pontuacao_final_progressao:
                resultado_final = 'Não aprovado'
                if obj.pontuacao_final_progressao >= obj.MINIMO_PONTUACAO_APROVACAO:
                    resultado_final = 'Aprovado'
            #
            row = [
                idx + 1,
                f'{obj.avaliado} ({obj.avaliado.matricula})',
                self.get_periodo(obj=obj),
                nivel,
                novo_nivel,
                resultado_final,
            ]
            rows.append(row)
        return rows

    def get_tabs(self, request):
        return ['tab_a_iniciar', 'tab_iniciado', 'tab_finalizado']

    def tab_a_iniciar(self, request, queryset):
        return queryset.filter(situacao=ProgressaoDocente.A_INICIAR)

    tab_a_iniciar.short_description = 'A iniciar'

    def tab_iniciado(self, request, queryset):
        lista_situacoes = [
            ProgressaoDocente.AGUARDANDO_PREENCHIMENTO,
            ProgressaoDocente.EM_AVALIACAO,
            ProgressaoDocente.RECURSO_AVALIACAO,
            ProgressaoDocente.REAVALIACAO,
            ProgressaoDocente.AGUARDANDO_CIENCIA_RESULTADO,
            ProgressaoDocente.CIENTE_RESULTADO,
        ]
        return queryset.filter(situacao__in=lista_situacoes)

    tab_iniciado.short_description = 'Iniciado'

    def tab_finalizado(self, request, queryset):
        return queryset.filter(situacao=ProgressaoDocente.FINALIZADO)

    tab_finalizado.short_description = 'Finalizado'

    super_extra_fieldsets = (('SUPERUSERS', {'fields': ('relatorio_a_progredir', 'situacao', 'processo_eletronico')}),)
    fieldsets = (
        (
            'Dados Pessoais',
            {
                'fields': (
                    'avaliado',
                    (
                        'data_inicio_periodo',
                        'data_fim_periodo',
                    ),
                    ('nivel_atual', 'proximo_nivel'),
                    ('nivel_atual_antigo', 'proximo_nivel_antigo'),
                    'tipo',
                    (
                        'progressao_complementar',
                        'progressao_principal',
                    ),
                )
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        meus_fieldsets = self.fieldsets
        if request.user.is_superuser:
            meus_fieldsets += self.super_extra_fieldsets
        return meus_fieldsets

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm('rh.eh_rh_sistemico')

    def has_change_permission(self, request, obj=None) -> bool:
        """Restringe a edição do processo à gestão de pessoas sistêmica.

        O avaliado enxerga o próprio processo na listagem (`get_queryset` filtra por `avaliado`), mas não
        pode alterá-lo — nem quando ele é reaberto para reavaliação (issue #17156). O RH
        sistêmico e o superusuário editam em qualquer situação, inclusive com o processo finalizado.

        Args:
            request: Requisição em curso, de onde sai o usuário autenticado.
            obj: Processo sob avaliação; `None` quando o admin pergunta pela permissão
                genérica (índice, listagem, redirecionamentos pós-salvamento).

        Returns:
            `True` se o usuário puder editar o processo informado.
        """
        if request.user.is_superuser:
            return True
        return bool(obj and request.user.has_perm('rh.eh_rh_sistemico'))

    def get_list_display(self, request):
        # a coluna de prazo só faz sentido para processos em andamento (aba "Iniciado")
        list_display = super().get_list_display(request)
        if request.GET.get('tab') != 'tab_iniciado':
            list_display = tuple(coluna for coluna in list_display if coluna != 'get_prazo')
        return list_display

    def get_situacao(self, obj):
        tipo = 'info'
        if obj.situacao == ProgressaoDocente.FINALIZADO:
            tipo = 'finalizado'
        return mark_safe(f'<span class="status status-{tipo}">{obj.get_situacao_display()}</span>')

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'situacao'

    def get_prazo(self, obj):
        # prazo da etapa atual de cada avaliação ainda não concluída do processo
        linhas = []
        # itera o avaliacao_set prefetchado (ver get_queryset) e filtra em Python;
        # usar .exclude() aqui re-consultaria o banco, ignorando o prefetch (N+1).
        for avaliacao in obj.avaliacao_set.all():
            if avaliacao.situacao == Avaliacao.CONCLUIDA:
                continue
            limite = avaliacao.data_limite_etapa_atual()
            if not limite:
                continue
            dias = avaliacao.dias_restantes_etapa_atual()
            if dias < 0:
                tipo, texto = 'error', f'vencido há {abs(dias)} dia(s)'
            elif dias == 0:
                tipo, texto = 'warning', 'vence hoje'
            elif dias <= 5:
                tipo, texto = 'warning', f'faltam {dias} dia(s)'
            else:
                tipo, texto = 'info', f'faltam {dias} dia(s)'
            linhas.append(f'<span class="status status-{tipo}">{texto}</span>')
        if not linhas:
            return mark_safe('<span class="status status-info">—</span>')
        return mark_safe(''.join(linhas))

    get_prazo.short_description = 'Prazo'

    def get_periodo(self, obj):
        return mark_safe(obj.get_periodo_descricao())

    get_periodo.short_description = 'Período'

    def get_resultado(self, obj):
        return mark_safe(obj.progressao_aprovada_display())

    get_resultado.short_description = 'Resultado Final'

    def get_nivel(self, obj):
        html = f'{obj.nivel_atual} a {obj.proximo_nivel}'
        return mark_safe(html)

    get_nivel.short_description = 'Níveis'

    def get_queryset(self, request):
        # prefetch do avaliacao_set evita N+1 em get_prazo (uma query por linha na listagem)
        queryset = super().get_queryset(request).prefetch_related('avaliacao_set')
        # se superuser ou rh sistêmico, pode ver tudo
        if request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico'):
            return queryset
        # se rh campus ou operador de rh, acessar apenas registros do próprio campus
        if request.user.has_perm('rh.eh_rh_campus') or request.user.has_group('Operador de Gestão de Pessoas'):
            uo = None
            try:
                uo = request.user.get_vinculo().setor.uo
            except Exception:
                raise Exception('Não foi possível localizar o campus do servidor.')
            if uo:
                return queryset.filter(avaliado__setor__uo=uo)
        servidor = request.user.get_relacionamento()
        # mostrar as avaliações em que sou um avaliador ou avaliado
        return queryset.filter(avaliado=servidor)

    def get_acoes(self, obj):
        html = '<ul class="action-bar">'
        #
        if obj.situacao != ProgressaoDocente.A_INICIAR:
            # quando o preenchimento ou a avaliação já iniciou, a gestão de pessoas pode alterar o período da avaliação
            # este alerta servirá para informar quando essa edição for realizada, para mostrar aos usuários que existe
            # dias não cobertos pelo novo período informado, quando for o caso.
            dias_descobertos = obj._lista_dias_nao_cobertos()
            if dias_descobertos:
                return mark_safe('<p class="alert alert-warning"><strong>Atenção:</strong> Dias do interstíco descobertos.</p>')
        #
        tem_acao = False
        if obj.pode_finalizar_processo(self.request):
            tem_acao = True
            html += f'<li><a href="/progressao_docente/finalizar/{obj.pk}/" class="btn success">Finalizar</a></li>'
        #
        if obj.pode_reabrir_edicao(self.request):
            tem_acao = True
            html += f'<li><a href="/progressao_docente/reabrir_edicao/{obj.pk}/" class="btn warning confirm">Reabrir para Edição</a></li>'
        #
        if not tem_acao:
            return mark_safe("<span class='status status-warning'>Nenhuma ação disponível</span>")
        #
        html += '</ul>'
        return mark_safe(html)

    get_acoes.short_description = 'Ações'


class CriterioInline(admin.StackedInline):
    model = Criterio
    fields = (
        'order',
        'nome',
        'inicio_vigencia',
        'limite_pontos',
    )
    extra = 1


@admin.register(Formulario)
class FormularioAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('id', 'nome', 'inicio_vigencia', 'fim_vigencia', 'data_cadastro')
    search_fields = ProgressaoDocente.SEARCH_FIELDS
    inlines = [
        CriterioInline,
    ]


class ItemInline(admin.TabularInline):
    model = Item
    fields = ('nome', 'descricao', 'pontuacao_fixa', 'inicio_vigencia')
    extra = 1


@admin.register(Criterio)
class CriterioAdmin(ModelAdminPlus):
    list_display_icons = True
    search_fields = Criterio().SEARCH_FIELDS
    list_filter = ('formulario',)
    list_display = (
        'order',
        'nome',
        'formulario',
        'necessita_arquivos',
        'autoavaliacao',
        'avaliacao_discente',
        'verificar_cd',
        'inicio_vigencia',
        'fim_vigencia',
        'limite_pontos',
    )
    inlines = [
        ItemInline,
    ]


class CriterioItemCustomFilter(SimpleListFilter):
    title = 'Critério'
    parameter_name = 'criterio'

    def lookups(self, request, model_admin):
        qs_criterios = Criterio.objects.all()
        formulario_filtro = request.GET.get('criterio__formulario', None)
        if formulario_filtro:
            qs_criterios = qs_criterios.filter(formulario_id=formulario_filtro)
        return [(d.id, d.nome) for d in qs_criterios]

    def queryset(self, request, queryset):
        criterio = request.GET.get('criterio', None)
        if criterio:
            return queryset.filter(criterio_id=criterio)
        return queryset


class PontuacaoItemInline(admin.StackedInline):
    model = PontuacaoItem
    fields = ('descricao', 'pontos', 'limite_pontos')
    extra = 1


@admin.register(Item)
class ItemAdmin(ModelAdminPlus):
    list_display_icons = True
    list_filter = ('criterio__formulario', CriterioItemCustomFilter)
    search_fields = Item.SEARCH_FIELDS
    inlines = [
        PontuacaoItemInline,
    ]
    list_display = ('id', 'nome', 'get_formulario', 'criterio', 'get_pontos', 'get_limite_pontos', 'inicio_vigencia', 'fim_vigencia')

    def get_formulario(self, obj):
        return obj.criterio.formulario

    get_formulario.short_description = 'Formulário'

    def get_pontos(self, obj):
        html = '<ul>'
        for i in obj.pontuacaoitem_set.all():
            html += f'<li>{i.descricao}</li>'
        html += '</ul>'
        return mark_safe(html)

    get_pontos.short_description = 'Pontos'

    def get_limite_pontos(self, obj):
        html = '<ul>'
        for i in obj.pontuacaoitem_set.all():
            html += f'<li>{i.limite_pontos or "NA"}</li>'
        html += '</ul>'
        return mark_safe(html)

    get_limite_pontos.short_description = 'Limite de Pontos'


class CriterioPontuacaoItemCustomFilter(SimpleListFilter):
    title = 'Critério'
    parameter_name = 'criterio'

    def lookups(self, request, model_admin):
        qs_criterios = Criterio.objects.all()
        formulario_filtro = request.GET.get('item__criterio__formulario', None)
        if formulario_filtro:
            qs_criterios = qs_criterios.filter(formulario_id=formulario_filtro)
        return [(d.id, d.nome) for d in qs_criterios]

    def queryset(self, request, queryset):
        criterio = request.GET.get('criterio', None)
        if criterio:
            return queryset.filter(item__criterio_id=criterio)
        return queryset


class ItemCustomFilter(SimpleListFilter):
    title = 'Item'
    parameter_name = 'item'

    def lookups(self, request, model_admin):
        qs_item = Item.objects.all()
        criterio_filtro = request.GET.get('criterio', None)
        if criterio_filtro:
            qs_item = qs_item.filter(criterio_id=criterio_filtro)
        return [(d.id, d.nome) for d in qs_item]

    def queryset(self, request, queryset):
        item = request.GET.get('item', None)
        if item:
            return queryset.filter(item_id=item)
        return queryset


@admin.register(PontuacaoItem)
class PontuacaoItemAdmin(ModelAdminPlus):
    list_display = ('get_criterio', 'item', 'descricao', 'pontos', 'limite_pontos')
    list_display_icons = True
    search_fields = PontuacaoItem.SEARCH_FIELDS
    list_filter = ('item__criterio__formulario', CriterioPontuacaoItemCustomFilter, ItemCustomFilter)

    def get_criterio(self, obj):
        return obj.item.criterio

    get_criterio.short_description = 'Critério'


@admin.register(Avaliacao)
class AvaliacaoAdmin(ModelAdminPlus):
    list_display_icons = True
    search_fields = Avaliacao.SEARCH_FIELDS
    list_filter = (CustomTabListFilter, 'progressao', 'progressao__avaliado__setor__uo')
    list_display = ('progressao', 'get_avaliador', 'get_periodo', 'formulario', 'get_relacao_processo')
    form = AvaliacaoForm
    show_count_on_tabs = True

    fieldsets = (
        (
            None,
            {
                'fields': ('formulario', ('periodo_inicio', 'periodo_fim'), 'avaliadores', 'progressao'),
            },
        ),
    )

    def get_action_bar(self, request):
        return []

    def has_change_permission(self, request, obj=None):
        # eh_rh_sistemico = request.user.has_perm('rh.eh_rh_sistemico')
        # eh_rh_campus = request.user.has_perm('rh.eh_rh_campus')
        # if eh_rh_sistemico or eh_rh_campus:
        #     return True
        if obj:
            return obj.pode_editar_avaliacao(request)
        return False

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            fieldsets += (
                (
                    'Super Usuário',
                    {
                        'fields': (('situacao', 'preenchida', 'finalizada'),),
                    },
                ),
            )
        return fieldsets

    # método auxiliar
    def _percentual_avaliado(self, obj):
        # responsavel = self.request.user.get_vinculo()
        avaliador = obj.avaliadores.first().get_vinculo()
        if obj.percentual_avaliado(avaliador).get('qtd_total') == 0:
            return 0
        percent = (100 * obj.percentual_avaliado(avaliador).get('qtd')) / obj.percentual_avaliado(avaliador).get('qtd_total')
        return percent

    def get_tabs(self, request):
        return [
            'tab_aguardando_preenchimento',
            'tab_em_avaliacao',
            'tab_em_reavaliacao',
            'tab_aguardando_ciencia',
            'tab_em_edicao_reavaliacao',
            'tab_concluidas',
        ]

    def tab_aguardando_preenchimento(self, request, queryset):
        return queryset.filter(situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO)

    tab_aguardando_preenchimento.short_description = 'Aguardando Preenchimento'

    def tab_em_avaliacao(self, request, queryset):
        return queryset.filter(situacao=Avaliacao.EM_AVALIACAO)

    tab_em_avaliacao.short_description = 'Em Avaliação'

    def tab_em_reavaliacao(self, request, queryset):
        return queryset.filter(situacao=Avaliacao.REAVALIACAO)

    tab_em_reavaliacao.short_description = 'Reavaliação'

    def tab_aguardando_ciencia(self, request, queryset):
        return queryset.filter(situacao=Avaliacao.AGUARDANDO_CIENCIA_RESULTADO)

    tab_aguardando_ciencia.short_description = 'Aguardando Ciência de Resultado'

    def tab_em_edicao_reavaliacao(self, request, queryset):
        return queryset.filter(situacao=Avaliacao.EDITACAO_PARA_REAVALIACAO)

    tab_em_edicao_reavaliacao.short_description = 'Em edição para reavaliação'

    def tab_concluidas(self, request, queryset):
        return queryset.filter(
            situacao=Avaliacao.CONCLUIDA,
        )

    tab_concluidas.short_description = 'Concluídas'

    def get_relacao_processo(self, obj):
        servidor_logado = self.request.user.get_relacionamento()
        eh_avaliador = servidor_logado.matricula in obj.avaliadores.values_list('matricula', flat=True)
        css_classe = 'success'
        texto = 'Meu processo'
        if eh_avaliador:
            css_classe = 'info'
            texto = 'Avaliador'
        html = f"<span class='status status-{css_classe}'>{texto}</span>"
        return mark_safe(html)

    get_relacao_processo.short_description = 'Relação'

    def get_percentual_preenchimento(self, obj):
        responsavel = self.request.user.get_vinculo()
        if obj.percentual_concluido(responsavel).get('qtd_total') == 0:
            return mark_safe('<div class="progress"><p>0%</p></div>')
        percent = (100 * obj.percentual_concluido(responsavel).get('qtd')) / obj.percentual_concluido(responsavel).get('qtd_total')
        html = f'<div class="progress"><p>{int(percent)}%</p></div>'
        return mark_safe(html)

    get_percentual_preenchimento.short_description = 'Percentual'

    def get_percentual_avaliado(self, obj):
        percent = self._percentual_avaliado(obj)
        html = f'<div class="progress"><p>{int(percent)}%</p></div>'
        return mark_safe(html)

    get_percentual_avaliado.short_description = 'Percentual Avaliado'

    def get_avaliado(self, obj):
        return obj.progressao.avaliado

    get_avaliado.short_description = 'Avaliado'

    def get_avaliador(self, obj):
        return obj.avaliadores.first()

    get_avaliador.short_description = 'Avaliador'

    def get_periodo(self, obj):
        return f'{obj.periodo_inicio.strftime("%d/%m/%Y")} a {obj.periodo_fim.strftime("%d/%m/%Y")}'

    get_periodo.short_description = 'Período'

    def _tempo_restante(self, dias, etapa):
        # mesmo vocabulário da coluna "Prazo" (get_prazo), para o RH não ler duas versões do mesmo prazo
        if dias is None:
            return 'Informação indisponível'
        if dias < 0:
            return f'Prazo vencido há {abs(dias)} dia(s) para concluir {etapa}.'
        if dias == 0:
            return f'Vence hoje o prazo para concluir {etapa}.'
        return f'Restam {dias} dia(s) para concluir {etapa}.'

    def get_tempo_restante_preenchimento(self, obj):
        return self._tempo_restante(obj.get_tempo_restante_preenchimento, 'o preenchimento')

    get_tempo_restante_preenchimento.short_description = 'Tempo para preenchimento'

    def get_tempo_restante_avaliacao(self, obj):
        return self._tempo_restante(obj.get_tempo_restante_avaliacao, 'a avaliação')

    get_tempo_restante_avaliacao.short_description = 'Tempo para avaliação'

    def get_tempo_restante_edicao_reavaliacao(self, obj):
        return self._tempo_restante(obj.get_tempo_restante_edicao_reavaliacao, 'a edição para reavaliação')

    get_tempo_restante_edicao_reavaliacao.short_description = 'Tempo para edição'

    def get_tempo_restante_reavaliacao(self, obj):
        return self._tempo_restante(obj.get_tempo_restante_reavaliacao, 'a reavaliação')

    get_tempo_restante_reavaliacao.short_description = 'Tempo para reavaliação'

    def get_acoes(self, obj):
        eh_avaliador = obj.usuario_eh_avaliador(self.request.user)
        eh_dono = obj.usuario_eh_dono(self.request.user)
        html = '<ul class="action-bar">'
        tem_acao = False
        if eh_avaliador:
            if obj.situacao == Avaliacao.REAVALIACAO:
                tem_acao = True
                html += f'<li><a href="/progressao_docente/avaliacao/{obj.pk}/reavaliar/" class="btn success">Reavaliar</a></li>'
            elif obj.finalizada:
                html += '<li><span class="status status-success">Finalizada</span></li>'
            else:
                if self._percentual_avaliado(obj) == 100:
                    tem_acao = True
                    html += f'<li><a href="/progressao_docente/avaliacao/{obj.pk}/assinar_avaliacao/" class="btn primary popup">Finalizar</a></li>'
                if obj.situacao == Avaliacao.EM_AVALIACAO:
                    tem_acao = True
                    html += f'<li><a href="/progressao_docente/avaliar_processo/{obj.pk}/" class="btn success">Avaliar</a></li>'
        elif eh_dono:
            if obj.situacao in [Avaliacao.AGUARDANDO_CIENCIA_RESULTADO, Avaliacao.EDITACAO_PARA_REAVALIACAO]:
                tem_acao = True
                txt = 'Ciência de Resultado'
                if obj.situacao == Avaliacao.EDITACAO_PARA_REAVALIACAO:
                    txt = 'Editar arquivos'
                html += f'<li><a href="/progressao_docente/avaliacao/{obj.pk}/ciencia_resultado/" class="btn success">{txt}</a></li>'
            if obj.situacao == Avaliacao.AGUARDANDO_PREENCHIMENTO:
                tem_acao = True
                html += f'<li><a href="/progressao_docente/avaliacao/{obj.pk}/preencher/" class="btn success">Preencher</a></li>'

        if not tem_acao:
            return mark_safe("<span class='status status-warning'>Nenhuma ação disponível</span>")

        html += '</ul>'
        return mark_safe(html)

    get_acoes.short_description = 'Ações'

    def response_delete(self, request, obj_display, obj_id):
        return httprr('..', 'Avaliação removida com sucesso.', close_popup=True)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not obj:
            progressao_id = request.GET.get('p', None)
            if progressao_id:
                progressao_id = int(progressao_id)
                form.base_fields['progressao'].initial = progressao_id
        form.base_fields['progressao'].widget = HiddenInput()
        return form

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related('progressao', 'progressao__avaliado', 'formulario')

        # se superuser ou rh sistêmico, pode ver tudo
        if request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico'):
            return queryset
        # se rh campus, acessar apenas registros do próprio campus
        servidor = request.user.get_relacionamento()
        if request.user.has_perm('rh.eh_rh_campus') or request.user.has_group('Operador de Gestão de Pessoas'):
            uo = None
            try:
                uo = request.user.get_vinculo().setor.uo
            except Exception:
                raise Exception('Não foi possível localizar o campus do servidor.')
            if uo:
                return queryset.filter(Q(progressao__avaliado=servidor) | Q(avaliadores=servidor) | Q(progressao__avaliado__setor__uo=uo)).distinct()
        #
        return queryset.filter(Q(progressao__avaliado=servidor) | Q(avaliadores=servidor)).distinct()

    def get_list_display(self, request):
        # "tab_aguardando_preenchimento", "tab_em_avaliacao"
        list_display = super().get_list_display(request)
        tab = request.GET.get('tab')
        if tab == 'tab_aguardando_preenchimento':
            list_display += ('get_percentual_preenchimento', 'get_tempo_restante_preenchimento')
        if tab == 'tab_em_avaliacao':
            list_display += ('get_percentual_avaliado', 'get_tempo_restante_avaliacao')
        if tab == 'tab_em_reavaliacao':
            list_display += ('get_tempo_restante_reavaliacao',)
        if tab == 'tab_em_edicao_reavaliacao':
            list_display += ('get_tempo_restante_edicao_reavaliacao',)
        # if (tab in [None, "tab_any_data", "tab_em_avaliacao", "tab_em_reavaliacao"]) and request.user.has_perm('progressao_docente.pode_avaliar_processo'):
        list_display += ('get_acoes',)  # o que será renderizado na ação é de responsabilidade do método get_acoes
        return list_display


@admin.register(AvaliacaoItem)
class AvaliacaoItemAdmin(ModelAdminPlus):
    list_display_icons = True
    search_fields = AvaliacaoItem.SEARCH_FIELDS
    list_filter = (
        'avaliacao',
        'item__criterio',
        'responsavel',
        'responsavel_avaliacao',
    )
    list_display = (
        'item',
        'get_progressao',
        'responsavel',
        'responsavel_avaliacao',
        'deferimento',
        'pontuacao',
        'pontuacao_form',
    )
    actions = ('deletar',)

    def get_progressao(self, obj):
        html = f"""
        <div><strong>{obj.avaliacao.progressao}</strong></div>
        <div><small>{obj.avaliacao.formulario}</small></div>
        """
        return mark_safe(html)

    get_progressao.short_description = 'Dados da Progressão'

    def deletar(self, request, queryset):
        try:
            if request.user.is_superuser:
                queryset.delete()
                messages.success(request, 'Ação realizada com sucesso.')
            else:
                raise PermissionError('Você não pode executar essa operação.')
        except Exception as ex:
            messages.error(request, ex)

    deletar.short_description = 'Apagar Avaliação do Item'


@admin.register(ConfiguracaoProgressaoDocente)
class ConfiguracaoProgressaoDocenteAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('descricao',)

    def has_add_permission(self, request):
        return not ConfiguracaoProgressaoDocente.objects.exists()

    fieldsets = (
        (
            'Descrição',
            {'fields': ('descricao',)},
        ),
        (
            'Aguardando Preenchimento',
            {
                'fields': (
                    'tempo_preenchimento',
                    'txt_preenchimento',
                    'txt_tempo_preenchimento_acabando',
                )
            },
        ),
        (
            'Em Avaliação',
            {
                'fields': (
                    'tempo_avaliacao',
                    'txt_avaliacao',
                    'txt_tempo_avaliacao_acabando',
                )
            },
        ),
        (
            'Ciência de Resultado',
            {
                'fields': (
                    'tempo_ciencia',
                    'txt_alerta_ciencia',
                )
            },
        ),
        (
            'Edição/Adição para Reavaliação',
            {
                'fields': (
                    'tempo_adicao_edicao',
                    'txt_alerta_edicao_adicao_reavaliacao',
                )
            },
        ),
        (
            'Em Reavaliação',
            {
                'fields': (
                    'tempo_reavaliacao',
                    'txt_alerta_reavaliacao',
                )
            },
        ),
    )


class DiscenteAptosAvaliacaoAdmin(ModelAdminPlus):
    list_display = ('progressao', 'avaliacao', 'matricula', 'nome', 'get_avaliacao_positiva', 'avaliacao_realizada', 'nao_reconhece_docente')
    list_filter = ('progressao', 'avaliacao', 'avaliacao_realizada')
    search_fields = ('nome', 'matricula', 'progressao__avaliado__pessoa_fisica__nome', 'progressao__avaliado__matricula')
    list_display_icons = True

    def get_avaliacao_positiva(self, obj):
        if obj.avaliacao_realizada:
            Aluno = apps.get_model('edu', 'Aluno')
            avaliador = Aluno.objects.get(matricula=obj.matricula)
            return obj.avaliacao.resultado_consideracao_positiva(avaliador=avaliador.get_vinculo())
        return None

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related('progressao', 'avaliacao', 'progressao__avaliado')
        return queryset


admin.site.register(DiscenteAptosAvaliacao, DiscenteAptosAvaliacaoAdmin)


class FiltroDiaProgressao(admin.SimpleListFilter):
    title = 'Filtro por Dias'
    parameter_name = 'dias_filter'

    def lookups(self, request, model_admin):
        return ((30, '30 dias ou menos'), (45, '45 dias ou menos'), (90, '90 dias ou menos'))

    def queryset(self, request, queryset):
        # hoje como data de checagem
        hoje = date.today()
        # filtro para pegar a diferença em dias da data de hoje e da data fim da contagem
        queryset = queryset.annotate(dias_para_vencer=ExpressionWrapper(F('data_fim_contagem') - hoje, output_field=DurationField())).annotate(
            dias_para_vencer_int=Extract(F('dias_para_vencer'), 'day')
        )
        # realizando os filtros pelos dias que o usuário passou no formulário
        if self.value() == '30':
            return queryset.filter(dias_para_vencer_int__lte=30)
        elif self.value() == '45':
            return queryset.filter(dias_para_vencer_int__lte=45)
        elif self.value() == '90':
            return queryset.filter(dias_para_vencer_int__lte=90)
        return queryset


@admin.register(DocenteAProgredir)
class DocenteAProgredirAdmin(ModelAdminPlus):
    list_display_icons = True
    list_display = ('get_avaliado', 'nivel_atual', 'get_campus', 'get_periodo', 'get_dias', 'progressao_criada', 'progressao_finalizada', 'opcoes')
    list_filter = (CustomTabListFilter, FiltroDiaProgressao, 'progressao_criada', 'progressao_finalizada', 'avaliado__setor__uo')
    search_fields = DocenteAProgredir.SEARCH_FIELDS
    form = DocenteAProgredirForm
    actions = ('deletar', 'recalcular')

    def deletar(self, request, queryset):
        try:
            if request.user.is_superuser or in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico'):
                queryset.delete()
                messages.success(request, 'Ação realizada com sucesso.')
            else:
                raise PermissionError('Você não pode executar essa operação.')
        except Exception as ex:
            messages.error(request, ex)

    deletar.short_description = 'Apagar registros'

    def recalcular(self, request, queryset):
        try:
            if request.user.is_superuser or in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico'):
                matriculas = []
                for i in queryset:
                    matriculas.append(i.avaliado.matricula)
                # apagando registros
                queryset.filter(progressao_criada=False, progressao_finalizada=False).delete()
                # recalculando os docentes a progredir
                ProgressaoDocente.calcular_docentes_a_progredir(matriculas=matriculas)
                messages.success(request, 'Ação realizada com sucesso.')
            else:
                raise PermissionError('Você não pode executar essa operação.')
        except Exception as ex:
            messages.error(request, ex)

    recalcular.short_description = 'Recalcular registros'

    def has_add_permission(self, request):
        return False

    def get_action_bar(self, request, remove_add_button=True):
        items = []
        if request.user.is_superuser or in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico'):
            items.append({'label': 'Executar Scripts', 'css_class': 'success', 'url': '/progressao_docente/executar_importacao/'})
            return items
        return []

    # queryset ajustado para mostrar na aba "todos" todas as progressões exceto as com nível 404, que serão exibidas em uma aba a parte
    def get_queryset(self, request):
        # queryset = super().get_queryset(request)
        # return queryset.exclude(avaliado__nivel_padrao="404")
        return super().get_queryset(request)

    def get_tabs(self, request):
        return [
            'tab_c4',
        ]

    def tab_c4(self, request, queryset):
        return DocenteAProgredir.objects.filter(nivel_atual='C4')

    tab_c4.short_description = 'C4'

    def get_campus(self, obj):
        if obj.avaliado and obj.avaliado.setor:
            return obj.avaliado.setor.uo
        return None

    get_campus.short_description = 'Campus'
    get_campus.admin_order_field = 'avaliado__setor__uo'

    def get_avaliado(self, obj):
        #
        nivel = f'<small>{obj.nivel_atual} para {obj.proximo_nivel} </small>'
        if obj.nivel_atual in ProgressaoDocente.ULTIMOS_NIVEIS:
            nivel = f'<small>{obj.nivel_atual} (último nível)</small>'
        #
        avaliado = f"""
        {obj.avaliado.nome} (<a href="/rh/servidor/{obj.avaliado.matricula}/">{obj.avaliado.matricula}</a>)
        <br />
        Setor: {obj.avaliado.setor}
        <br />
        {nivel}
        """
        if obj.eh_primeira_promocao:
            avaliado += "<span class='status status-alert text-nowrap-normal'>Promoção (36 meses)</span>"
        if obj.progressao_finalizada:
            compl = ''
            if obj.progressaodocente_set.exists():
                progressao = obj.progressaodocente_set.first()
                if progressao and not progressao._aprovado():
                    compl = '<small>(reprovado)</small>'
            avaliado += f"<span class='status status-success text-nowrap-normal'>Progressão finalizada {compl}</span>"
        return mark_safe(avaliado)

    get_avaliado.short_description = 'Avaliado'
    get_avaliado.admin_order_field = 'avaliado__pessoa_fisica__nome'

    def get_periodo(self, obj):
        return mark_safe(
            f'De <strong>{obj.data_inicio_contagem.strftime("%d/%m/%Y")}</strong> a <strong>{obj.data_fim_contagem.strftime("%d/%m/%Y")}</strong>'
        )

    get_periodo.short_description = 'Período'
    get_periodo.admin_order_field = 'data_inicio_contagem'

    def get_dias(self, obj):
        if obj.progressao_finalizada or obj.avaliado.nivel_padrao == '404':
            return ' - '
        dias = obj.get_dias_restantes()
        class_css = 'status-success'  # padrao: status a iniciar
        if dias <= 10:
            class_css = 'status-error'
        if 10 < dias < 20:
            class_css = 'status-warning'
        return mark_safe(f"<span class='status {class_css} text-nowrap-normal'>{dias} dias</span>")

    get_dias.short_description = 'Dias restantes'

    def opcoes(self, obj):
        if obj.progressao_finalizada:
            # se finalizada, mostra apenas a opção de visualizar a progressão
            progressao = obj.progressaodocente_set.all().first()
            if progressao:
                return mark_safe(
                    f"<ul class='action-bar'><li><a class='btn btn-success' href='/progressao_docente/ver/{progressao.id}/'>Ver Progressão Docente</a></li></ul>"
                )
        #
        result = ''
        if obj.nivel_atual not in ProgressaoDocente.ULTIMOS_NIVEIS:
            result = '<ul class="action-bar">'
            if not obj.progressao_criada and obj.get_dias_restantes() <= ProgressaoDocente.DIAS_ANTECEDENCIA_CALCULAR_NOVAS_PROGRESSOES:
                # criar progressão
                result += f"<li><a class='btn confirm' href='/progressao_docente/criar_progressao/{obj.id}/'>Criar Progressão Docente</a></li>"
            if obj.progressao_criada:
                progressao = obj.progressaodocente_set.all().first()
                if progressao:
                    result += f"<li><a class='btn btn-success' href='/progressao_docente/ver/{progressao.id}/'>Ver Progressão Docente</a></li>"
            result += '</ul>'
        return mark_safe(f'{result}')

    opcoes.short_description = 'Opções'
