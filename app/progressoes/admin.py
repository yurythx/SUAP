import datetime
from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import DateField, DurationField, ExpressionWrapper, F, Value
from django.db.models.functions import Coalesce, ExtractDay, Now
from django.shortcuts import redirect
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from comum.models import Configuracao
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, DateRangeListFilter, ModelAdminPlus
from djtools.templatetags.filters.utils import in_group
from djtools.templatetags.tags import icon
from djtools.templatetags.tags.utils import edit_object_icon
from djtools.utils import httprr
from progressoes.forms import (
    AvaliacaoModeloForm,
    EstagioProbatorioAddForm,
    EstagioProbatorioEditForm,
    ProcessoProgressaoAddForm,
    ProcessoProgressaoEditForm,
)
from progressoes.models import (
    AvaliacaoModelo,
    AvaliacaoModeloCriterio,
    ConfiguracaoProgressao,
    ObservacaoAfastamentoEfetivoExercicio,
    ProcessoProgressao,
    ProcessoProgressaoAvaliacao,
    ServidorAProgredir,
    SiglaSetorPrimeiroTramite,
)
from rh.utils import gerar_filtro_por_relacao


class AvaliacaoModeloAdmin(ModelAdminPlus):
    list_display = ('nome', 'tipo')
    search_fields = ('nome', 'itens_avaliados__descricao_questao')
    form = AvaliacaoModeloForm
    list_display_icons = True


admin.site.register(AvaliacaoModelo, AvaliacaoModeloAdmin)


class AvaliacaoModeloCriterioAdmin(ModelAdminPlus):
    list_display = ('descricao_questao', 'nota_minima', 'nota_maxima', 'passo_nota')
    list_display_icons = True


admin.site.register(AvaliacaoModeloCriterio, AvaliacaoModeloCriterioAdmin)


class SituacaoFinalFilter(admin.SimpleListFilter):
    title = _('Situação Final')
    parameter_name = 'situacao_final'

    def lookups(self, request, model_admin):
        return (
            (0, _('Não Finalizado')),
            (1, _('Aprovado')),
            (2, _('Reprovado')),
        )

    def queryset(self, request, queryset):
        config = ProcessoProgressao.get_configuracao()
        if not config:
            raise ConfiguracaoProgressao.DoesNotExist(
                'Não foi encontrada uma configuração para a progressão TAE. Cadastre uma configuração para proceguir.'
            )
        if self.value() == '0':
            return queryset.filter(status__lt=ProcessoProgressao.STATUS_FINALIZADO)
        elif self.value() == '1':
            return queryset.filter(status=ProcessoProgressao.STATUS_FINALIZADO, media_processo__gte=config.media_aprovacao)
        elif self.value() == '2':
            return queryset.filter(status=ProcessoProgressao.STATUS_FINALIZADO, media_processo__lt=config.media_aprovacao)
        return queryset


class ProcessoProgressaoAdmin(ModelAdminPlus):
    list_display = (
        'acoes',
        'avaliado',
        'tipo_processo',
        'data_inicio_contagem_progressao',
        'data_fim_contagem_progressao',
        'status_display',
        'get_situacao_final_processo',
        'avaliacoes_respondidas',
        'assinaturas_requeridas',
        'opcoes',
    )
    search_fields = (
        'avaliado__pessoa_fisica__nome',
        'avaliado__matricula',
        'processoprogressaoperiodo__processoprogressaoavaliacao__avaliador__pessoa__nome',
        'processoprogressaoperiodo__processoprogressaoavaliacao__avaliador__user__username',
    )
    list_display_icons = False
    list_filter = (
        CustomTabListFilter,
        'tipo',
        ('data_fim_contagem_progressao', DateRangeListFilter),
        SituacaoFinalFilter,
    )
    show_count_on_tabs = True
    export_to_xls = True
    # FIELDSETS
    fieldset_progressao = (
        (
            '',
            {
                'fields': (
                    'avaliado',
                    'data_inicio_contagem_progressao',
                    'data_fim_contagem_progressao',
                    'padrao_anterior',
                    'padrao_novo',
                    'dias_saldo',
                )
            },
        ),
    )
    fieldset_progressao_add = (('', {'fields': ('avaliado', 'data_inicio_contagem_progressao', 'padrao_anterior', 'padrao_novo')}),)
    fieldset_estagio_probatorio = (
        (
            '',
            {
                'fields': (
                    'avaliado',
                    'data_inicio_contagem_progressao',
                    'data_fim_contagem_progressao',
                )
            },
        ),
    )
    fieldset_estagio_probatorio_add = (
        (
            '',
            {
                'fields': (
                    'avaliado',
                    'data_inicio_contagem_progressao',
                )
            },
        ),
    )
    rh_sistemico_extra_fieldsets = (('Rh Sistêmico', {'fields': ('processo_eletronico', 'registro_a_progredir', 'nao_permitir_recalculo_data_fim')}),)
    actions = ['recalcular_media_processo']

    def get_actions(self, request):
        if request.user.is_superuser or in_group(request.user, 'Coordenador de Gestão de Pessoas Sistêmico'):
            return super().get_actions(request)
        return []

    def recalcular_media_processo(self, request, queryset):
        for processo in queryset:
            processo_periodos = processo.processoprogressaoperiodo_set.all()
            for processo_periodo in processo_periodos:
                processo_periodo.calcular_media_periodo()  # a média do processo também será atualizada
            # processo.calcular_media_processo()
        self.message_user(request, 'Médias recalculadas com sucesso.')

    def to_xls(self, request, queryset, task):
        header = ['#', 'Avaliado', 'Tipo de Processo', 'Data Início da Contagem', 'Data Fim da Contagem', 'Status', 'Situação Final']
        rows = [header]
        for idx, obj in enumerate(task.iterate(queryset)):
            row = [
                idx + 1,
                f'{obj.avaliado} ({obj.avaliado.matricula})',
                obj.get_tipo_display(),
                obj.data_inicio_contagem_progressao,
                obj.data_fim_contagem_progressao,
                obj.get_status_display(),
                obj.obter_situacao_final_processo_as_text(),
            ]
            rows.append(row)
        return rows

    def get_situacao_final_processo(self, obj):
        situacao_final = obj.obter_situacao_final_processo()
        txt = ''
        if situacao_final == ProcessoProgressao.SITUACAO_FINAL_APROVADO:
            txt = '<span class="status status-success text-nowrap-normal">Aprovado</span>'
        elif situacao_final == ProcessoProgressao.SITUACAO_FINAL_REPROVADO:
            txt = '<span class="status status-error text-nowrap-normal">Reprovado</span>'
        elif situacao_final == ProcessoProgressao.SITUACAO_FINAL_NAO_FINALIZADO:
            txt = '<span class="status status-warning text-nowrap-normal">Não finalizado</span>'
        return mark_safe(txt)

    get_situacao_final_processo.short_description = 'Resultado Final'

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        tipo = request.GET.get('tipo', None)
        if tipo:
            tipo = int(tipo)
        # se em configurações estiver marcado para criar apenas pelo relatório, será sempre redirecionado para o relatório para que se possa criar o processo
        criar_pelo_relatorio_apenas = Configuracao.get_valor_por_chave('progressoes', 'criar_progressao_apenas_pelo_relatorio')
        if criar_pelo_relatorio_apenas and tipo == ProcessoProgressao.TIPO_PROGRESSAO_MERITO:
            return redirect('/admin/progressoes/servidoraprogredir/')
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_action_bar(self, request, remove_add_button=True):
        item = super().get_action_bar(request, remove_add_button)
        subitems = [
            # /admin/progressoes/servidoraprogredir/
            {'label': 'Progressão', 'url': '/admin/progressoes/processoprogressao/add/?tipo=1'},
            {'label': 'Estágio Probatório', 'url': '/admin/progressoes/processoprogressao/add/?tipo=2'},
        ]
        item.append({'label': 'Adicionar Processo', 'css_class': 'success', 'subitems': subitems})
        return item

    def tipo_processo(self, obj):
        return obj.get_tipo_display()

    tipo_processo.short_description = 'Tipo de Processo'
    tipo_processo.admin_order_field = 'tipo'

    def get_list_filter(self, request):
        if request.user.has_perm('progressoes.pode_ver_todos_os_processos'):
            if 'avaliado__setor__uo' not in self.list_filter:
                self.list_filter += ('avaliado__setor__uo',)
        return super().get_list_filter(request)

    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            tipo = request.GET.get('tipo', None)
            if tipo:
                tipo = int(tipo)
            if tipo == ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO:
                self.form = EstagioProbatorioAddForm
            else:
                self.form = ProcessoProgressaoAddForm
        else:
            if obj.is_tipo_estagio_probatorio:
                self.form = EstagioProbatorioEditForm
            else:
                self.form = ProcessoProgressaoEditForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        meus_fieldsets = ()
        if not obj:
            tipo = request.GET.get('tipo', None)
            if tipo:
                tipo = int(tipo)
            if tipo == ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO:
                meus_fieldsets = self.fieldset_estagio_probatorio_add
            else:
                meus_fieldsets = self.fieldset_progressao_add
        else:
            if obj.is_tipo_estagio_probatorio:
                meus_fieldsets = self.fieldset_estagio_probatorio
            else:
                meus_fieldsets = self.fieldset_progressao
            # somente no opção de editar podemos ver este campo
            if request.user.has_perm('rh.eh_rh_sistemico'):
                meus_fieldsets += self.rh_sistemico_extra_fieldsets
        return meus_fieldsets

    def response_add(self, request, obj, post_url_continue=None):
        return httprr(f'/progressoes/editar_processo/{obj.id}/', message='Processo de progressão cadastrado com sucesso.')

    def response_change(self, request, obj):
        return httprr(f'/progressoes/editar_processo/{obj.id}/', message='Processo de progressão alterado com sucesso.')

    def acoes(self, obj):
        acoes = icon('view', f'/progressoes/editar_processo/{obj.id}/')
        if obj.status != ProcessoProgressao.STATUS_FINALIZADO:
            acoes += icon('delete', f'/admin/progressoes/processoprogressao/{obj.id}/delete', 'Excluir Processo', 'no-confirm')
        return mark_safe(f'{acoes}')

    acoes.short_description = 'Ações'

    def opcoes(self, obj):
        opcoes = ''
        if obj.status == ProcessoProgressao.STATUS_FINALIZADO:
            opcoes += f"<a class='btn' href='/progressoes/imprimir_processo/{obj.id}/'>Imprimir Processo</a>"
        return mark_safe(f'{opcoes}')

    opcoes.short_description = 'Opções'

    def avaliacoes_respondidas(self, obj):
        avaliacoes = obj.obter_avaliacoes()
        if avaliacoes:
            avaliacoes_total = len(avaliacoes)
        else:
            avaliacoes_total = 0

        avaliacoes_respondidas = 0
        for avaliacao in avaliacoes:
            if avaliacao.is_avaliada:
                avaliacoes_respondidas += 1

        class_css = 'status-error'
        if avaliacoes:
            class_css = 'status-em-tramite'
        if avaliacoes_respondidas > 0 and avaliacoes_respondidas == avaliacoes_total:
            class_css = 'status-finalizado'

        return mark_safe(f"<span class='status {class_css} text-nowrap-normal'>{avaliacoes_respondidas}/{avaliacoes_total}</span>")

    avaliacoes_respondidas.short_description = 'Avaliações Respondidas'

    def assinaturas_requeridas(self, obj):
        avaliacoes = obj.obter_avaliacoes()
        avaliacoes_pendentes = 0
        assinaturas_realizadas = 0
        assinaturas_requeridas = 0
        class_css = 'status-error'
        if avaliacoes:
            class_css = 'status-em-tramite'
            for avaliacao in avaliacoes:
                assinaturas_situacao = avaliacao.assinaturas_realizadas_requeridas()
                assinaturas_realizadas += assinaturas_situacao[0]
                assinaturas_requeridas += assinaturas_situacao[1]
                if avaliacao.is_pendente:
                    avaliacoes_pendentes += 1

        if assinaturas_realizadas > 0 and assinaturas_realizadas == assinaturas_requeridas and avaliacoes_pendentes == 0:
            class_css = 'status-finalizado'

        return mark_safe(f"<span class='status {class_css} text-nowrap-normal'>{assinaturas_realizadas}/{assinaturas_requeridas}</span>")

    assinaturas_requeridas.short_description = 'Assinaturas'

    def get_queryset(self, request, *args, manager=None, **kwargs):
        qs = ModelAdminPlus.get_queryset(self, request, manager, *args, **kwargs)
        if request.user.has_perm('progressoes.pode_ver_todos_os_processos'):
            pass
        elif request.user.has_perm('progressoes.pode_ver_apenas_processos_do_seu_campus'):
            campus_usuario_logado = request.user.get_vinculo().setor.uo
            qs = qs.filter(avaliado__setor__uo__sigla=campus_usuario_logado.sigla)
        else:
            qs = qs.none()
        return qs

    def get_tabs(self, request):
        return ['tab_a_iniciar', 'tab_em_tramite', 'tab_a_finalizar', 'tab_finalizados', 'tab_any_data']

    def tab_a_iniciar(self, request, queryset):
        return queryset.filter(status=ProcessoProgressao.STATUS_A_INICIAR)

    tab_a_iniciar.short_description = 'A Iniciar'

    def tab_em_tramite(self, request, queryset):
        return queryset.filter(status=ProcessoProgressao.STATUS_EM_TRAMITE)

    tab_em_tramite.short_description = 'Em Trâmite'

    def tab_a_finalizar(self, request, queryset):
        return queryset.filter(status=ProcessoProgressao.STATUS_EM_TRAMITE).exclude(
            processoprogressaoperiodo__processoprogressaoavaliacao__status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_PENDENTE
        )

    tab_a_finalizar.short_description = 'A Finalizar'

    def tab_finalizados(self, request, queryset):
        return queryset.filter(status=ProcessoProgressao.STATUS_FINALIZADO)

    tab_finalizados.short_description = 'Finalizados'

    def status_display(self, obj):
        class_css = 'status-error'  # padrao: status a iniciar
        if obj.status == ProcessoProgressao.STATUS_EM_TRAMITE:
            class_css = 'status-em-tramite'
        if obj.status == ProcessoProgressao.STATUS_FINALIZADO:
            situacao_processo = obj.obter_situacao_final_processo()
            if situacao_processo == ProcessoProgressao.SITUACAO_FINAL_APROVADO:
                class_css = 'status-finalizado'
            elif situacao_processo == ProcessoProgressao.SITUACAO_FINAL_APROVADO:
                class_css = 'status-rejeitado'

        return mark_safe(f"<span class='status {class_css} text-nowrap-normal'>{obj.get_status_display()}</span>")

    status_display.admin_order_field = 'status'
    status_display.short_description = 'Situação'


admin.site.register(ProcessoProgressao, ProcessoProgressaoAdmin)


class ObservacaoAfastamentoEfetivoExercicioAdmin(ModelAdminPlus):
    list_display = ('processo', 'data_afetada', 'qtd_dias_afastamento', 'get_afastamentos')
    search_fields = ('processo', 'processo__avaliado')
    list_display_icons = True
    actions = [
        'apagar',
    ]

    def apagar(self, request, queryset):
        queryset.delete()

    apagar.short_description = 'Apagar Registros'

    def get_afastamentos(self, obj):
        html = '<ul>'
        for i in obj.afastamentos.all():
            html += f'<li>{i.afastamento} ({i.data_inicio} a {i.data_termino})</li>'
        html += '</ul>'
        return mark_safe(html)

    get_afastamentos.short_description = 'Afastamentos'


admin.site.register(ObservacaoAfastamentoEfetivoExercicio, ObservacaoAfastamentoEfetivoExercicioAdmin)


class FiltroDiaProgressao(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'Filtro por Dias'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'dias_filter'

    def lookups(self, request, model_admin):
        return ((30, '30 dias ou menos'), (45, '45 dias ou menos'), (90, '90 dias ou menos'))

    def queryset(self, request, queryset):
        # hoje como data de checagem
        hoje = datetime.date.today()
        # Subtrair saldo_dias (em dias) diretamente como intervalo
        queryset = queryset.annotate(saldo_em_dias=ExpressionWrapper(Coalesce(F('saldo_dias'), Value(0)) * Value(1), output_field=DurationField()))

        # Subtrair esse intervalo da data_fim_contagem (mesma regra da property ServidorAProgredir.data_fim_ajustada;
        # o nome difere porque a anotação não pode sobrescrever a property)
        queryset = queryset.annotate(
            data_fim_com_saldo=ExpressionWrapper(
                F('data_fim_contagem') - F('saldo_em_dias'),
                output_field=DateField(),  # ou DateTimeField se for o caso
            )
        )

        # Calcular dias para vencer
        queryset = queryset.annotate(
            dias_para_vencer=ExpressionWrapper(F('data_fim_com_saldo') - hoje, output_field=DurationField()),
            dias_para_vencer_int=ExtractDay('dias_para_vencer'),
        )
        # realizando os filtros pelos dias que o usuário passou no formulário
        if self.value() == '30':
            return queryset.filter(dias_para_vencer_int__lte=30)
        elif self.value() == '45':
            return queryset.filter(dias_para_vencer_int__lte=45)
        elif self.value() == '90':
            return queryset.filter(dias_para_vencer_int__lte=90)
        return queryset


SetorSiglaFilter = gerar_filtro_por_relacao(
    ServidorAProgredir,
    'avaliado__setor__uo__sigla',
    'Campus',
)


class TemSaldoFilter(admin.SimpleListFilter):
    title = 'Tem saldo?'
    parameter_name = 'tem_saldo'

    def lookups(self, request, model_admin):
        return (
            ('sim', 'Sim'),
            ('nao', 'Não'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(saldo_dias__gt=0)
        elif self.value() == 'nao':
            return queryset.filter(saldo_dias=0)
        return queryset


class ServidorAProgredirAdmin(ModelAdminPlus):
    list_display = ('get_avaliado', 'get_campus', 'get_periodo', 'calculo', 'data_inicio_contagem_manual', 'get_dias', 'processo_criado', 'opcoes')
    search_fields = (
        'avaliado__pessoa_fisica__nome',
        'avaliado__matricula',
    )
    list_filter = ('calculo', SetorSiglaFilter, 'processo_criado', FiltroDiaProgressao, TemSaldoFilter)
    list_display_icons = True
    actions = ('deletar',)

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

    def get_tabs(self, request):
        return ['tab_novo_periodo', 'tab_any_data']

    def tab_novo_periodo(self, request, queryset):
        return (
            queryset.annotate(
                data_modificada=ExpressionWrapper(
                    F('data_fim_contagem') - timedelta(days=6 * 30),  # Aproximação de 6 meses
                    output_field=DateField(),  # Especifica que o resultado é uma data
                )
            )
            .filter(
                data_modificada__lte=Now() + timedelta(days=90)  # Falta 90 dias ou menos
            )
            .exclude(situacao=ServidorAProgredir.SITUACAO_FINALIZADO)
        )

    tab_novo_periodo.short_description = 'Novo período'

    def get_action_bar(self, request, remove_add_button=False):
        item = super().get_action_bar(request, remove_add_button)
        if request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico'):
            item.append({'label': 'Executar Scripts', 'css_class': 'success', 'url': '/progressoes/executar_importacao/'})
            return item
        return []

    def show_list_display_icons(self, obj):
        out = []
        out.append(icon('view', obj.get_absolute_url()))
        out.append(edit_object_icon(obj))
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = '#'

    def has_add_permission(self, request):
        return request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(avaliado__ativo=True)
        # superusers e sistêmicos
        if request.user.is_superuser or request.user.has_perm('rh.eh_rh_sistemico'):
            return qs
        # usuarios não sistêmico
        uo_usuario = get_uo(request.user)
        return qs.filter(avaliado__setor__uo__id=uo_usuario.id).exclude(situacao=ServidorAProgredir.SITUACAO_FINALIZADO)

    def get_periodo(self, obj):
        data_fim = f'<strong>{obj.data_fim_contagem.strftime("%d/%m/%Y")}</strong>'
        if obj.tem_saldo_dias():
            _data_fim = obj.data_fim_contagem - timedelta(days=obj.saldo_dias)
            data_fim = f'<strong>{_data_fim.strftime("%d/%m/%Y")}</strong> <small>(<s>{obj.data_fim_contagem.strftime("%d/%m/%Y")}</s>)</small>'

        return mark_safe(
            f"""
            De <strong>{obj.data_inicio_contagem.strftime('%d/%m/%Y')}</strong> a {data_fim}
            """
        )

    get_periodo.short_description = 'Período'
    get_periodo.admin_order_field = 'data_inicio_contagem'

    def get_avaliado(self, obj):
        #
        # identificando o processo
        _qs_processo = ProcessoProgressao.objects.filter(registro_a_progredir=obj)
        processo = None
        if _qs_processo.exists():
            processo = _qs_processo.first()
        #
        classe = None
        if obj.avaliado.cargo_classe:
            classe = obj.avaliado.cargo_classe.codigo
        #
        if processo:
            _padrao = f'<dl><dt>Nível atual:</dt> <dd>{processo.padrao_anterior} </dd></dl> <dl><dt>Próximo nível:</dt> <dd>{processo.padrao_novo}</dd></dl>'
        else:
            _padrao = f'<dl><dt>Nível atual:</dt><dd>{classe}{obj.avaliado.nivel_padrao}</dd></dl>'
        #
        avaliado = f"""
        <h3>{obj.avaliado.pessoa_fisica.nome} (<a href="/rh/servidor/{obj.avaliado.matricula}/">{obj.avaliado.matricula}</a>)</h3>
        <dl>
            <dt>Situação:</dt><dd>{obj.avaliado.situacao}</dd>
        </dl>
        {_padrao}
        """
        if obj.situacao == ServidorAProgredir.SITUACAO_FINALIZADO:
            avaliado += "<span class='status status-success text-nowrap-normal'>Processo finalizado</span>"
        if obj.tem_saldo_dias():
            avaliado += f"<span class='status status-info'>Saldo de {obj.saldo_dias} dias</span>"
        return mark_safe(avaliado)

    get_avaliado.short_description = 'Avaliado'
    get_avaliado.admin_order_field = 'avaliado__pessoa_fisica__nome'

    def get_campus(self, obj):
        if obj.avaliado.setor:
            return obj.avaliado.setor.uo.sigla
        return None

    get_campus.short_description = 'Campus'
    get_campus.admin_order_field = 'avaliado__setor__uo__sigla'

    def opcoes(self, obj):
        # selecionando a configuração
        config = ProcessoProgressao.get_configuracao()
        if not config:
            return mark_safe(
                "<ul class='action-bar'><li><a class='btn warning' href='/admin/progressoes/configuracaoprogressao/'>Acessar Configuração</a></li></ul>"
            )
        #
        if obj.situacao == ServidorAProgredir.SITUACAO_FINALIZADO:
            return ''  # finalizado não é possível realizar nenhuma ação
        result = '<ul class="action-bar">'
        if obj.calculo == ServidorAProgredir.VIA_PCA:
            # só é possível marcar como capacitação um registro PCA
            result += f"<li><a class='btn success confirm' href='/progressoes/marcar_como_capacitacao/{obj.id}/'>Marcar como capacitação</a></li>"
        # corrigir data de início do período
        result += f"<li><a class='btn success popup' href='/progressoes/ultima_progressao_data/{obj.id}/'>Adicionar data de início manual</a></li>"
        if not obj.processo_criado and obj.get_dias_restantes() <= config.dias_antecedencia_calcular:
            # criar processo
            result += f"<li><a class='btn confirm' href='/progressoes/criar_processo/{obj.id}/'>Criar progressão</a></li>"
        # verificando novo período de progressão
        elif not obj.processo_criado and obj.get_dias_restantes(checar_novo_periodo=True) <= config.dias_antecedencia_calcular:
            result += f"<li><a class='btn warning confirm' href='/progressoes/criar_processo/{obj.id}/novo_periodo/'>Criar progressão (novo período)</a></li>"
        if self.request.user.has_perm('rh.eh_rh_sistemico') or self.request.user.has_perm('rh.eh_rh_campus'):
            if obj.avaliado.tem_divergencia_datas_progressao_pca():
                result += f"<li><a class='btn popup' href='/progressoes/escolher_fonte_atualizacao/{obj.id}/'>Atualizar informações</a></li>"
            else:
                result += f"<li><a class='btn confirm' data-confirm='Tem certeza que deseja atualizar as informações?' href='/progressoes/atualizar_dados_progredir/{obj.id}/'>Atualizar informações</a></li>"
        # verificando se existe processo
        if obj.processo_criado and obj.processoprogressao_set.exists():
            p = obj.processoprogressao_set.first()
            result += f"<li><a class='btn' href='/progressoes/editar_processo/{p.pk}/'>Acessar Processo</a></li>"
        #
        result += '</ul>'
        return mark_safe(f'{result}')

    opcoes.short_description = 'Opções'

    def get_dias(self, obj):
        if obj.situacao == ServidorAProgredir.SITUACAO_FINALIZADO:
            return ' - '
        dias = obj.get_dias_restantes()
        class_css = 'status-success'  # padrao: status a iniciar
        if dias <= 10:
            class_css = 'status-error'
        if 10 < dias < 20:
            class_css = 'status-warning'
        return mark_safe(f"<span class='status {class_css} text-nowrap-normal'>{dias} dias</span>")

    get_dias.short_description = 'Dias restantes'


admin.site.register(ServidorAProgredir, ServidorAProgredirAdmin)


class ConfiguracaoProgressaoAdmin(ModelAdminPlus):
    list_display = (
        'intersticio_progressao',
        'intersticio_estagio_probatorio',
        'dias_antecedencia_calcular',
        'gerar_inconsistencia_dias',
        'media_aprovacao',
        'ativo',
    )
    list_display_icons = True


admin.site.register(ConfiguracaoProgressao, ConfiguracaoProgressaoAdmin)


class SiglaSetorPrimeiroTramiteAdmin(ModelAdminPlus):
    list_display = ('tipo', 'sigla', 'ordem')
    list_filter = ('tipo',)
    search_fields = ('sigla',)
    list_display_icons = True


admin.site.register(SiglaSetorPrimeiroTramite, SiglaSetorPrimeiroTramiteAdmin)
