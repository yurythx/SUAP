from __future__ import annotations

from datetime import datetime

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import F, Q

from comum.models import Configuracao
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.contrib.admin.filters import DateRangeListFilter
from djtools.utils import httprr, somar_dias
from edu.forms import AbonoFaltasForm, ConfiguracaoPedidoMatriculaForm, RequerimentoForm
from edu.models import (
    AbonoFaltas,
    ConfiguracaoPedidoMatricula,
    CursoCampus,
    PedidoMatriculaDiario,
    ProcedimentoMatricula,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    SolicitacaoAproveitamentoEstudo,
    MotivoAusenciaEscolar,
)


class ConfiguracaoPedidoMatriculaAdmin(ModelAdminPlus):
    list_filter = (CustomTabListFilter, 'ano_letivo', 'periodo_letivo', 'diretorias')
    list_display = ('id', 'ano_letivo', 'periodo_letivo', 'descricao', 'get_status', 'get_diretorias', 'data_inicio', 'data_fim')
    list_display_icons = True
    search_fields = ('descricao',)
    ordering = ('-id',)
    form = ConfiguracaoPedidoMatriculaForm

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if not change:
            user = request.user
            if user.has_perm('comum.is_coordenador_de_curso', ignore_superuser=True):
                obj = form.instance
                cursos = CursoCampus.objects.filter(diretoria_id__in=obj.diretorias.values_list('id', flat=True)).filter(
                    Q(coordenador__user_id=user.id) | Q(coordenador_2__user_id=user.id)
                )
                obj.cursos.set(cursos)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ('Informações gerais', {'fields': ('descricao', ('ano_letivo', 'periodo_letivo'), 'diretorias')}),
            ('Período de matrícula', {'fields': (('data_inicio', 'data_fim'),)}),
            (
                'Configurações gerais',
                {
                    'fields': (
                        'impedir_troca_turma',
                        'restringir_por_curso',
                        'restringir_por_convenio',
                        'requer_atualizacao_dados',
                        'requer_atualizacao_caracterizacao',
                        'permite_cancelamento_matricula_diario',
                    )
                },
            ),
            (
                'Disciplinas eletivas',
                {
                    'fields': (
                        'permite_requerimento_matricula_diario',
                        'permite_solicitacao_disciplinas_eletivas',
                        'restringir_disciplinas_eletivas_mesmo_curso',
                    )
                },
            ),
        ]
        if (
            Configuracao.get_valor_por_chave('edu', 'permite_requerer_quebra_requisito_aumento_ch')
            or obj is not None
            and any((obj.permite_requerimento_quebra_de_requisito, obj.permite_requerimento_ultrapassar_ch_maxima))
        ):
            fieldsets.append(
                (
                    'Outras configurações',
                    {
                        'fields': (
                            'permite_requerimento_quebra_de_requisito',
                            'permite_requerimento_ultrapassar_ch_maxima',
                            'data_limite_requerimentos_especiais',
                        )
                    },
                ),
            )

        return fieldsets

    def get_status(self, obj):
        tokens = obj.get_status()
        return mark_safe(f'<span class="status {tokens[1]}">{tokens[0]}</span></td>')

    get_status.short_description = 'Situação'

    def get_tabs(self, request):
        return [
            'tab_aguardando_inicio_matricula',
            'tab_aguardando_matriculas',
            'tab_aguardando_processamento',
            'tab_finalizados',
            'tab_cancelados',
            'tab_sem_pedidos',
        ]

    def get_queryset(self, request):
        return super().get_queryset(request, ConfiguracaoPedidoMatricula.locals).distinct()

    def tab_aguardando_inicio_matricula(self, request, queryset):
        return queryset.exclude(data_inicio__lte=datetime.today())

    tab_aguardando_inicio_matricula.short_description = 'Aguardando início'

    def tab_aguardando_matriculas(self, request, queryset):
        return queryset.filter(data_inicio__lt=somar_dias(datetime.today(), 1), data_fim__gte=datetime.today())

    tab_aguardando_matriculas.short_description = 'Em andamento'

    def tab_aguardando_processamento(self, request, queryset):
        return (
            queryset.filter(data_fim__lt=datetime.today())
            .exclude(pedidomatricula__isnull=True)
            .exclude(pedidomatricula__pedidomatriculadiario__data_processamento__isnull=False)
            .exclude(pedidomatricula__motivo_impedimento_matricula_vinculo__isnull=False)
            .exclude(
                pedidomatricula__pedidomatriculadiario__isnull=True,
                pedidomatricula__matricula_periodo__procedimentomatricula__tipo=ProcedimentoMatricula.MATRICULA_VINCULO,
            )
            .exclude(pedidomatricula__pedidomatriculadiario__motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO)
        )

    tab_aguardando_processamento.short_description = 'Aguardando processamento'

    def tab_finalizados(self, request, queryset):
        return (
            queryset.filter(data_fim__lt=datetime.today())
            .filter(
                Q(pedidomatricula__pedidomatriculadiario__data_processamento__isnull=False)
                | Q(pedidomatricula__motivo_impedimento_matricula_vinculo__isnull=False)
                | Q(
                    pedidomatricula__pedidomatriculadiario__isnull=True,
                    pedidomatricula__matricula_periodo__procedimentomatricula__tipo=ProcedimentoMatricula.MATRICULA_VINCULO,
                )
            )
            .exclude(pedidomatricula__pedidomatriculadiario__motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO)
        )

    tab_finalizados.short_description = 'Processadas'

    def tab_cancelados(self, request, queryset):
        return queryset.filter(pedidomatricula__pedidomatriculadiario__motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO)

    tab_cancelados.short_description = 'Canceladas'

    def tab_sem_pedidos(self, request, queryset):
        return queryset.filter(pedidomatricula__isnull=True)

    tab_sem_pedidos.short_description = 'Sem pedidos'

    def delete_view(self, request, object_id, extra_context=None):
        configuracao_pedido_matricula = ConfiguracaoPedidoMatricula.objects.get(pk=object_id)
        if not request.POST:
            return super().delete_view(request, object_id, extra_context)
        elif request.POST and configuracao_pedido_matricula.pode_ser_excluido():
            configuracao_pedido_matricula.enviar_emails_alunos()
            return super().delete_view(request, object_id, extra_context)
        else:
            msg = 'Não é possível realizar a exclusão. Existem pedidos de matrícula já processados para esta configuração.'
            messages.error(request, msg)
            return redirect('.')

    def response_add(self, request, obj):
        return httprr(
            f'/edu/configuracao_pedido_matricula/{obj.pk}/',
            'Cadastro realizado com sucesso. Adicione os cursos para os quais os pedidos serão realizados.',
        )

    def get_diretorias(self, obj):
        if obj.diretorias.all().exists():
            lista = ['<ul>']
            for diretoria in obj.diretorias.all():
                lista.append(f'<li>{diretoria}</li>')
            lista.append('</ul>')
            return mark_safe(''.join(lista))
        else:
            return mark_safe('-')

    get_diretorias.short_description = 'Diretorias'


admin.site.register(ConfiguracaoPedidoMatricula, ConfiguracaoPedidoMatriculaAdmin)


class PedidoMatriculaDiarioAdmin(ModelAdminPlus):
    list_filter = (
        'pedido_matricula__configuracao_pedido_matricula__ano_letivo',
        'pedido_matricula__configuracao_pedido_matricula__periodo_letivo',
        'deferido',
        'pedido_matricula__matricula_periodo__aluno__curso_campus',
    )
    list_display = ('get_aluno', 'get_curso', 'get_ano_periodo', 'get_turma', 'diario', 'deferido', 'data_processamento')
    search_fields = ('pedido_matricula__matricula_periodo__aluno__matricula', 'pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome')
    ordering = ('-pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome',)
    list_display_icons = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        return items

    def get_aluno(self, obj):
        return obj.pedido_matricula.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_turma(self, obj):
        return obj.pedido_matricula.turma

    get_turma.short_description = 'Turma'

    def get_ano_periodo(self, obj):
        return f'{obj.pedido_matricula.configuracao_pedido_matricula.ano_letivo}/{obj.pedido_matricula.configuracao_pedido_matricula.periodo_letivo}'

    get_ano_periodo.short_description = 'Ano/Período'

    def get_curso(self, obj):
        return obj.pedido_matricula.matricula_periodo.aluno.curso_campus.descricao_historico

    get_curso.short_description = 'Curso'


admin.site.register(PedidoMatriculaDiario, PedidoMatriculaDiarioAdmin)


class MotivoAusenciaEscolarAdmin(ModelAdminPlus):
    list_filter = 'possui_previsao_normativa', 'reposicao_obrigatoria', 'ativo'
    list_display = (
        'descricao',
        'possui_previsao_normativa',
        'reposicao_obrigatoria',
        'prazo_maximo_apresentar_justificativa',
        'ativo',
    )
    list_display_icons = True


admin.site.register(MotivoAusenciaEscolar, MotivoAusenciaEscolarAdmin)


class AbonoFaltasAdmin(ModelAdminPlus):
    list_filter = (
        CustomTabListFilter,
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus__diretoria',
        'aluno__curso_campus',
        ('data_inicio', DateRangeListFilter),
        'deferido',
    )
    list_display = ('aluno', 'responsavel_abono', 'data_solicitacao', 'data_inicio', 'data_fim', 'deferido')
    list_display_icons = True
    search_fields = ('aluno__pessoa_fisica__nome_registro', 'aluno__pessoa_fisica__nome_social', 'aluno__matricula')
    form = AbonoFaltasForm
    date_hierarchy = 'data_inicio'
    export_to_xls = True

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.processar()

    def get_action_bar(self, request):
        items = [
            {'url': '/admin/edu/abonofaltas/add/', 'label': 'Adicionar Justificativa de Falta', 'css_class': 'success'},
            {'url': '/edu/abonar_faltas_lote/', 'label': 'Adicionar em Lote', 'css_class': 'success'},
        ]
        items.extend(super(self.__class__, self).get_action_bar(request, True))
        return items

    def has_change_permission(self, request, obj=None):
        if obj and obj.deferido is not None:
            return False
        return super().has_change_permission(request, obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (
                'Dados gerais',
                {
                    'fields': (
                        'aluno',
                        ('data_inicio', 'quantidade_dias'),
                        'data_fim',
                    )
                },
            ),
            (
                'Detalhamento',
                {
                    'fields': (
                        'motivo_ausencia_escolar',
                        'justificativa',
                        'anexo',
                    )
                },
            ),
        ]
        if obj is None or obj.id is None:
            fieldsets.append(
                ('Dados da avaliação', {'fields': ('responsavel_abono', 'diarios')}),
            )

        return fieldsets

    def get_queryset(self, request):
        return AbonoFaltas.locals.order_by(F('data_solicitacao').desc(nulls_last=True))

    def response_add(self, request, obj):
        if '_save' in request.POST:
            return httprr(obj.get_absolute_url(), 'Cadastro realizado com sucesso.')
        elif '_continue' in request.POST:
            return httprr(f'/admin/edu/abonofaltas/{obj.pk}/change/', 'Cadastro realizado com sucesso. Você pode editá-lo novamente.')
        elif '_addanother' in request.POST:
            return httprr('/admin/edu/abonofaltas/add/', 'Cadastro realizado com sucesso.')
        else:
            return super().response_add(request, obj)

    def get_tabs(self, request):
        return [
            'tab_aguardando_avaliacao',
            'tab_aguardando_reposicao_atividade',
            'tab_aguardando_reposicao_minha_atividade',
            'tab_sem_abono_docente',
            'tab_sem_meu_abono_docente',
        ]

    def tab_aguardando_avaliacao(self, request, queryset):
        return queryset.filter(motivo_ausencia_escolar__isnull=False, responsavel_abono__isnull=True)

    tab_aguardando_avaliacao.short_description = 'Aguardando avaliação'

    def tab_sem_abono_docente(self, request, queryset):
        return AbonoFaltas.locals.sem_abono_docente(queryset=queryset)

    tab_sem_abono_docente.short_description = 'Não abonadas pelo docente'

    def tab_sem_meu_abono_docente(self, request, queryset):
        return AbonoFaltas.locals.sem_abono_docente(queryset=queryset, user=request.user)

    tab_sem_meu_abono_docente.short_description = 'Não abonadas por mim'

    def tab_aguardando_reposicao_atividade(self, request, queryset):
        return AbonoFaltas.locals.aguardando_reposicao_atividade(queryset=queryset)

    tab_aguardando_reposicao_atividade.short_description = 'Aguardando agendamento para reposição de atividade'

    def tab_aguardando_reposicao_minha_atividade(self, request, queryset):
        return AbonoFaltas.locals.aguardando_reposicao_atividade(queryset=queryset, user=request.user)

    tab_aguardando_reposicao_minha_atividade.short_description = 'Aguardando meu agendamento para reposição de atividade'


admin.site.register(AbonoFaltas, AbonoFaltasAdmin)


class RequerimentoAdmin(ModelAdminPlus):
    search_fields = ('id', 'aluno__pessoa_fisica__nome', 'aluno__matricula')
    list_display = ('id', 'aluno', 'tipo', 'data', 'get_detalhamento', 'situacao', 'deferido', 'atendente')
    date_hierarchy = 'data'
    list_filter = (
        CustomTabListFilter,
        'tipo',
        'situacao',
        'aluno__curso_campus',
        'aluno__curso_campus__diretoria',
        'aluno__curso_campus__diretoria__setor__uo',
    )
    list_display_icons = True
    list_per_page = 15
    form = RequerimentoForm
    export_to_xls = True

    actions = ['deferir_em_lote', 'indeferir_em_lote']

    def action_checkbox(self, obj):
        """Retorna o checkbox de seleção apenas para requerimentos de tipos automatizados.

        Args:
            obj: instância do requerimento.

        Returns:
            HTML do checkbox quando ``obj`` é de um tipo automatizado,
            string vazia caso contrário.
        """
        if obj and obj.tipo in [choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES]:
            return super().action_checkbox(obj)
        return ''

    def get_actions(self, request):
        """Remove ações em lote quando não está na aba 'Em Andamento'
        ou o usuário não tem permissão de coordenador ou admin acadêmico.

        Args:
            request: requisição HTTP.

        Returns:
            dicionário de ações disponíveis para o admin.
        """
        actions = super().get_actions(request)
        tabs = request.GET.get('tab')

        if tabs != 'tab_em_andamento' or not request.user.has_group_cached(['Coordenador de Curso', 'Administrador Acadêmico']):
            actions.pop('deferir_em_lote', None)
            actions.pop('indeferir_em_lote', None)

        return actions

    def deferir_em_lote(self, request, queryset):
        erros = []
        processados = 0

        try:
            Requerimento.validar_tipos_na_avaliacao_em_lote(queryset)
        except ValidationError as e:
            self.message_user(request, ' '.join(e.messages), level=messages.ERROR)
            return

        ignorados = queryset.filter(deferido__isnull=False).count()

        for requerimento in queryset.filter(deferido__isnull=True):
            try:
                requerimento.sub_instance().processar(request.user)
                processados += 1
            except ValidationError as e:
                erros.append(f'{requerimento}: {" ".join(e.messages)}')

        mensagem_sucesso = ''
        if processados:
            mensagem_sucesso = f'{processados} requerimento{pluralize(processados)} deferido{pluralize(processados)} com sucesso.'

        if ignorados:
            mensagem_ignorados = '{n} {requerimento} {foi} {ignorado} porque já {havia} sido {avaliado}'.format(
                n=ignorados,
                requerimento=f'requerimento{pluralize(ignorados)}',
                foi=f'fo{pluralize(ignorados, "i,ram")}',
                ignorado=f'ignorado{pluralize(ignorados)}',
                havia=f'havia{pluralize(ignorados, "m")}',
                avaliado=f'avaliado{pluralize(ignorados)}',
            )

            mensagem_sucesso = f'{mensagem_sucesso} {mensagem_ignorados}'.strip()

        if mensagem_sucesso:
            self.message_user(request, mensagem_sucesso, level=messages.SUCCESS)

        if erros:
            self.message_user(request, f'{len(erros)} erro{pluralize(erros)} no processamento: {" ".join(erros)}', level=messages.ERROR)

    deferir_em_lote.short_description = 'Deferir'

    def indeferir_em_lote(self, request, queryset):
        try:
            Requerimento.validar_tipos_na_avaliacao_em_lote(queryset)
        except ValidationError as e:
            self.message_user(request, ' '.join(e.messages), level=messages.ERROR)
            return

        if qtd_arquivados := queryset.filter(situacao=Requerimento.SITUACAO_ARQUIVADO).count():
            msg = '{n} {requerimento} {foi} {ignorado} porque já {havia} sido {avaliado}'.format(
                n=qtd_arquivados,
                requerimento=f'requerimento{pluralize(qtd_arquivados)}',
                foi=f'fo{pluralize(qtd_arquivados, "i,ram")}',
                ignorado=f'ignorado{pluralize(qtd_arquivados)}',
                havia=f'havia{pluralize(qtd_arquivados, "m")}',
                avaliado=f'avaliado{pluralize(qtd_arquivados)}',
            )
            self.message_user(request, msg, level=messages.ERROR)

        ids = ','.join(str(pk) for pk in queryset.filter(situacao=Requerimento.SITUACAO_EM_ANDAMENTO).values_list('pk', flat=True))
        return httprr(f'{reverse("indeferir_em_lote")}?ids={ids}')

    indeferir_em_lote.short_description = 'Indeferir'

    def get_tabs(self, request):
        """Retorna a lista de abas disponíveis na página de listagem de requerimentos.

        Returns:
            lista de identificadores das abas.
        """
        return [
            'tab_em_andamento',
            'tab_encaminhar',
            'tab_reencaminhar',
            'tab_em_avaliacao',
            'tab_aguardando_minha_avaliacao',
            'tab_avaliados_por_mim',
            'tab_any_data',
        ]

    def get_detalhamento(self, obj):
        lista = ['<dl>']
        for k, v in obj.get_detalhamento():
            lista.append(f'<dt>{k}:</dt><dd>{v}</dd>')
        lista.append('</dl>')
        return mark_safe(''.join(lista)) if len(lista) > 2 else '-'

    get_detalhamento.short_description = 'Detalhamento'

    def tab_em_andamento(self, request, queryset):
        return queryset.exclude(situacao='Arquivado')

    tab_em_andamento.short_description = 'Em andamento'

    def tab_encaminhar(self, request, queryset):
        vinculo = request.user.get_vinculo()
        qs = RequerimentoAproveitamentoEstudo.objects.filter(situacao=Requerimento.SITUACAO_EM_ANDAMENTO, atendente__isnull=True)
        qs = qs.filter(aluno__curso_campus__coordenador=vinculo) | qs.filter(aluno__curso_campus__coordenador_2=vinculo)
        return queryset.filter(pk__in=qs.order_by('pk').values_list('pk', flat=True).distinct())

    tab_encaminhar.short_description = 'A encaminhar'

    def tab_reencaminhar(self, request, queryset):
        vinculo = request.user.get_vinculo()
        qs = RequerimentoAproveitamentoEstudo.objects.filter(situacao=Requerimento.SITUACAO_EM_ANDAMENTO, atendente__isnull=False)
        qs = qs.filter(aluno__curso_campus__coordenador=vinculo) | qs.filter(aluno__curso_campus__coordenador_2=vinculo)
        pks = qs.filter(solicitacaoaproveitamentoestudo__parecer__apto=False).order_by('pk').values_list('pk', flat=True).distinct()
        return queryset.filter(pk__in=pks)

    tab_reencaminhar.short_description = 'A reencaminhar'

    def tab_em_avaliacao(self, request, queryset):
        return queryset.exclude(situacao='Arquivado').filter(atendente__isnull=False)

    tab_em_avaliacao.short_description = 'Aguardando avaliação'

    def tab_aguardando_minha_avaliacao(self, request, queryset):
        pks = (
            SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento__situacao=Requerimento.SITUACAO_EM_ANDAMENTO,
                avaliador__vinculo=request.user.get_vinculo(),
                parecer__isnull=True,
            )
            .exclude(situacao=SolicitacaoAproveitamentoEstudo.SITUACAO_INDEFERIDA)
            .values_list('requerimento', flat=True)
        )
        return queryset.filter(pk__in=pks)

    tab_aguardando_minha_avaliacao.short_description = 'Aguardando minha avaliação'

    def tab_avaliados_por_mim(self, request, queryset):
        pks = SolicitacaoAproveitamentoEstudo.objects.filter(avaliador__vinculo=request.user.get_vinculo(), parecer__isnull=False).values_list(
            'requerimento', flat=True
        )
        return queryset.filter(pk__in=pks)

    tab_avaliados_por_mim.short_description = 'Avaliados por mim'

    def to_xls(self, request, queryset, processo):
        rows = []
        rows.append(['MATRÍCULA', 'ALUNO', 'TURMA', 'CURSO', 'TIPO', 'DATA', 'LOCALIZAÇÃO', 'SITUAÇÃO', 'DESCRIÇÃO/JUSTIFICATIVA'])
        for requerimento in queryset.select_related('curso_campus', 'aluno__pessoa_fisica'):
            rows.append(
                [
                    requerimento.aluno.matricula,
                    requerimento.aluno.pessoa_fisica.nome,
                    requerimento.aluno.get_ultima_matricula_periodo().turma or '',
                    requerimento.aluno.curso_campus.descricao,
                    requerimento.get_tipo_display(),
                    requerimento.data,
                    requerimento.localizacao,
                    requerimento.situacao,
                    requerimento.descricao,
                ]
            )
        return rows

    def get_queryset(self, request):
        if request.user.eh_aluno:
            raise PermissionDenied
        return Requerimento.get_queryset(request.user).filter(situacao__isnull=False).distinct()


admin.site.register(Requerimento, RequerimentoAdmin)
