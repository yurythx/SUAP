from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q, Value
from django.forms import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from auditoria.utils import considerar_liberacoes_ponto
from djtools.contrib.admin import ModelAdminPlus
from djtools.contrib.admin.filters import CustomTabListFilter
from djtools.templatetags.filters import format_profile, status
from djtools.utils import get_datetime_now, httprr
from rh.models import Setor

from .forms import (
    AcaoForm,
    BeneficioForm,
    ConcederPermissaoDeChefeForm,
    LiberacaoProgramadaForm,
    NucleoAuditoriaForm,
    PaintForm,
    RecomendacaoAddForm,
    RecomendacaoForm,
    RelatorioAddForm,
)
from .models import (
    Acao,
    AcaoPermissao,
    AlcanceEstrategico,
    Beneficio,
    CategoriaLiberacao,
    ClasseBeneficio,
    HistoricoRecomendacao,
    LiberacaoProgramada,
    Manifestacao,
    ManifestacaoStatus,
    Monitoramento,
    MonitoramentoStatus,
    Motivacao,
    NucleoAuditoria,
    OrigemDemanda,
    Paint,
    PermissaoDeChefe,
    PerspectivaEstrategica,
    PlanejamentoAnual,
    Recomendacao,
    RecomendacaoStatus,
    # Monitoramento
    Relatorio,
    PosicionamentoStatus,
    TipoAfastamento,
    TipoPosicionamentoValido,
    TipoServico,
    UnidadeAfetada,
)
from .papeis import eh_auditor_chefe
from .permissao import exige_permissao, tem_permissao


class AcaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'tipo_servico', 'ativo')
    list_filter = (
        'tipo_servico',
        'ativo',
    )
    search_fields = ('nome',)
    list_display_icons = True
    form = AcaoForm
    fieldsets = AcaoForm.fieldsets


admin.site.register(Acao, AcaoAdmin)


class NucleoAuditoriaAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'coordenador', 'email', 'ramal', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    list_display_icons = True
    form = NucleoAuditoriaForm


admin.site.register(NucleoAuditoria, NucleoAuditoriaAdmin)


class TipoServicoAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'gera_ordem_servico', 'requer_revisor', 'ativo')
    list_filter = ('ativo', 'gera_ordem_servico', 'requer_revisor')
    search_fields = ('nome',)
    list_display_icons = True

    fieldsets = (
        (
            'Dados do Tipo de Serviço',
            {
                'fields': (
                    ('nome',),
                    ('descricao',),
                    ('gera_ordem_servico', 'requer_revisor'),
                    ('ativo',),
                )
            },
        ),
    )


admin.site.register(TipoServico, TipoServicoAdmin)


class OrigemDemandaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)
    list_display_icons = True


admin.site.register(OrigemDemanda, OrigemDemandaAdmin)


class PerspectivaEstrategicaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativa')
    list_filter = ('ativa',)
    search_fields = ('nome',)
    list_display_icons = True


admin.site.register(PerspectivaEstrategica, PerspectivaEstrategicaAdmin)


class UnidadeAuditadasFilter(admin.SimpleListFilter):
    title = 'Unidade Auditada'
    parameter_name = 'unidade_auditada'  # The URL parameter name

    def lookups(self, request, model_admin):
        return Setor.objects.suap_ativos().all().values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            setor = Setor.objects.suap_ativos().get(id=self.value())
            return queryset.filter(unidades_auditadas__id=setor)
        return queryset


class RelatorioAdmin(ModelAdminPlus):
    list_display = (
        'get_identificador',
        'get_paint',
        'get_acao',
        'get_unidades_auditadas',
        'get_equipe',
        'nucleo',
    )
    list_filter = (
        'ano',
        'acao',
        'ano_paint',
        'nucleo',
        'equipe',
        'unidades_auditadas',
    )
    search_fields = ('acao__nome',)
    list_display_icons = True
    list_per_page = 25
    form = RelatorioAddForm
    fieldsets = RelatorioAddForm.fieldsets

    def get_identificador(self, obj):
        return obj.identificador

    get_identificador.short_description = 'Número do relatório'

    def get_paint(self, obj):
        return obj.ano_paint

    get_paint.short_description = 'Ano/PAINT'

    def get_acao(self, obj):
        return obj.acao.nome

    get_acao.short_description = 'Ação'

    def get_unidades_auditadas(self, obj):
        setores = ['<ul>']
        for setor in obj.unidades_auditadas.all():
            setores.append(f'<li>{setor}</li>')
        setores.append('</ul>')
        return mark_safe(''.join(setores))

    get_unidades_auditadas.short_description = 'Unidades Auditadas'

    def get_equipe(self, obj):
        equipe = [f'<li>{format_profile(membro)}</li>' for membro in obj.equipe.all()]
        return mark_safe(f'<ul>{"".join(equipe)}</ul>')

    get_equipe.short_description = 'Equipe'

    def save_model(self, request, obj, form, change):
        try:
            if change:
                obj.modificado_por = request.user
            super().save_model(request, obj, form, change)
        except ValueError as e:
            messages.error(request, str(e))


admin.site.register(Relatorio, RelatorioAdmin)


class PossuiManifestacaoPendenteFilter(admin.SimpleListFilter):
    title = 'Manifestação Pendente'
    parameter_name = 'possui_manifestacao_pendente'

    def lookups(self, request, model_admin):
        return (
            ('sim', 'Sim'),
            ('nao', 'Não'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.filter(monitoramentos__manifestacoes__status__in=[MonitoramentoStatus.AGUARDANDO_REVISAO]).distinct()
        elif self.value() == 'nao':
            return queryset.exclude(monitoramentos__manifestacoes__status__in=[MonitoramentoStatus.AGUARDANDO_REVISAO]).distinct()
        return queryset


class RecomendacaoAdmin(ModelAdminPlus):
    title = 'Recomendações'
    list_display = (
        'identificador',
        'relatorio',
        'get_acao',
        'get_ano_auditoria',
        'get_status',
        'get_monitor',
        'get_revisor',
        'nucleo',
        'get_unidades_auditadas',
        'get_ultima_manifestacao',
    )
    list_filter = (
        CustomTabListFilter,
        'relatorio',
        'relatorio__acao',
        'ano',
        'relatorio__ano_paint',
        'status',
        'monitor',
        'revisor',
        'nucleo',
        'unidades',
        PossuiManifestacaoPendenteFilter,
    )
    search_fields = ('numero', 'ano')
    list_display_icons = True
    export_to_xls = True
    list_per_page = 25
    add_form = RecomendacaoAddForm
    form = RecomendacaoForm
    show_count_on_tabs = True

    def get_search_results(self, request, queryset, search_term):
        # If search term matches numero_ano, filter queryset by it
        if search_term:
            # Split the search term on the slash ("/") or any other delimiter
            search_terms = search_term.split('/')
            if len(search_terms) == 2:
                # If both parts (numero and ano) are provided, filter on both
                queryset = queryset.filter(Q(numero=int(search_terms[0])) & Q(ano__ano=int(search_terms[1])))
            else:
                # If only one part is provided, search in both fields
                if search_term.isnumeric():
                    queryset = queryset.filter(Q(numero=search_term) | Q(ano__ano=search_term))
                else:
                    queryset = queryset.filter(relatorio__acao__nome__icontains=search_term)
        return queryset, False

    def get_fieldsets(self, request, obj=None):
        form = self.form if obj else self.add_form
        return form.fieldsets

    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if has_permission and obj is not None:
            if obj.pode_editar(request.user) and obj.ativa:
                return True
            return obj.pode_reativar(request.user)
        return False

    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if has_permission and obj is not None:
            return obj.pode_remover(request.user) or request.user.is_superuser
        return False

    def response_delete(self, request, obj_display, obj_id):
        # This method is called after the object is deleted
        # Construct the URL for the admin list view (changelist view)
        app_label = Recomendacao._meta.app_label
        model_name = Recomendacao._meta.model_name
        changelist_url = reverse(f'admin:{app_label}_{model_name}_changelist')

        # Redirect to the list view
        return redirect(changelist_url)

    def get_acao(self, obj):
        return obj.relatorio.acao

    get_acao.short_description = 'Ação'

    def get_ano_auditoria(self, obj):
        return obj.relatorio.data_inicio.year

    get_ano_auditoria.short_description = 'Ano Auditoria'

    def get_ultima_manifestacao(self, obj):
        monitoramento_ids = obj.monitoramentos.values_list('id', flat=True)
        qs = Manifestacao.objects.filter(monitoramento__in=monitoramento_ids)
        ultima_manifestacao = (qs.aguardando_analise() | qs.enviadas()).order_by('-ultima_modificacao').first()
        if ultima_manifestacao:
            return mark_safe(f'<a href="{ultima_manifestacao.get_absolute_url()}">{ultima_manifestacao.unidade}</a>')
        return 'Sem manifestações pendentes'

    get_ultima_manifestacao.short_description = 'Manifestação a Analisar'

    def get_status(self, obj):
        obj.verificar_expiracao()
        display, classe = RecomendacaoStatus.get_display_and_class(obj.status)
        return format_html(f'<span class="status status-{classe}"> {display}</span>')

    get_status.short_description = 'Situação'

    def get_monitor(self, obj):
        return format_profile(obj.monitor)

    get_monitor.short_description = 'Monitor'

    def get_revisor(self, obj):
        return format_profile(obj.revisor) if obj.revisor else None

    get_revisor.short_description = 'Revisor'

    def get_unidades_auditadas(self, obj):
        setores = ['<ul>']
        for setor in obj.unidades.all():
            setores.append(f'<li>{setor}</li>')
        setores.append('</ul>')
        return mark_safe(''.join(setores))

    get_unidades_auditadas.short_description = 'Unidades Auditadas'

    def tab_minhas_recomendacoes_a_monitorar(self, request, queryset):
        auditor = request.user.get_vinculo()
        return queryset.filter(monitor=auditor)

    tab_minhas_recomendacoes_a_monitorar.short_description = 'Minhas Recomendações'

    def tab_minhas_recomendacoes_a_revisar(self, request, queryset):
        auditor = request.user.get_vinculo()
        return queryset.filter(
            revisor=auditor,
            monitoramentos__manifestacoes__posicionamentos__status__in=[
                PosicionamentoStatus.REVISAO_PENDENTE,
                PosicionamentoStatus.EM_REVISAO,
            ],
        ).distinct()

    tab_minhas_recomendacoes_a_revisar.short_description = 'Posicionamentos a revisar'

    def get_tabs(self, request):
        return ['tab_minhas_recomendacoes_a_monitorar', 'tab_minhas_recomendacoes_a_revisar']

    def register_changelog(self, request, obj, form):
        user = request.user
        initial_data = obj.__class__.objects.get(pk=obj.pk).__dict__
        for field in form.changed_data:
            if field == 'descricao':
                continue
            #
            initial_value = initial_data.get(field)
            new_value = getattr(obj, field)
            if initial_value != new_value:
                change_description = f"Usuário {user} mudou o campo '{field}' de '{initial_value}' para '{new_value}'"
                HistoricoRecomendacao.objects.create(recomendacao=obj, descricao=change_description)

    def save_model(self, request, obj, form, change):
        try:
            with transaction.atomic():
                if change:
                    self.register_changelog(request, obj, form)
                #
                super().save_model(request, obj, form, change)
                obj.salvar_descricao(form.cleaned_data.get('descricao'))
                #
        except Exception as e:
            # Captura o ValueError levantado pelo signal e o converte em um ValidationError
            form.add_error(None, ValidationError(e))
            messages.error(request, str(e))

    def save_related(self, request, form, formsets, change):
        try:
            with transaction.atomic():
                return super().save_related(request, form, formsets, change)
        except Exception as e:
            form.add_error(None, ValidationError(e))
            messages.error(request, str(e))


admin.site.register(Recomendacao, RecomendacaoAdmin)


class RecomendacaoFilter(admin.SimpleListFilter):
    title = 'Recomendação'
    parameter_name = 'recomendacao'

    def lookups(self, request, model_admin):
        recomendacoes = Recomendacao.objects.all()
        identificadores = set()
        for recomendacao in recomendacoes:
            identificadores.add((recomendacao.identificador, recomendacao.identificador))
        return sorted(identificadores, key=lambda x: x[1])

    def queryset(self, request, queryset):
        if self.value():
            numero, ano = self.value().split('/')
            return queryset.filter(recomendacao__numero=numero, recomendacao__ano__ano=ano)
        return queryset


class CampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'campus'

    def lookups(self, request, model_admin):
        monitoramentos = Monitoramento.objects.values_list('unidade__uo__id', 'unidade__uo__sigla').distinct()
        return sorted(monitoramentos, key=lambda x: x[1])

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(unidade__uo__id=self.value())
        else:
            return queryset


class PrazoFilter(admin.SimpleListFilter):
    title = 'Prazo Atual'
    parameter_name = 'prazo_status'

    def lookups(self, request, model_admin):
        return (
            ('vencido', 'Vencido'),
            ('proximo', 'Vencendo em 7 dias'),
            ('futuro', 'Futuro (> 7 dias)'),
        )

    def queryset(self, request, queryset):
        today = get_datetime_now().date()
        soon = get_datetime_now().date() + Value(timedelta(days=7))

        if self.value() == 'vencido':
            return queryset.filter(ultima_solicitacao__prazo_atual__lt=today)
        elif self.value() == 'proximo':
            return queryset.filter(ultima_solicitacao__prazo_atual__gte=today, ultima_solicitacao__prazo_atual__lte=soon)
        elif self.value() == 'futuro':
            return queryset.filter(ultima_solicitacao__prazo_atual__gt=soon)
        return queryset


class MonitoramentoAdmin(ModelAdminPlus):
    list_display = (
        'get_recomendacao',
        'get_unidade',
        'get_paint',
        'get_acao',
        'get_status',
        'get_monitor',
        'get_revisor',
        'get_nucleo',
        'get_prazo_atual',
        'get_data_limite',
        'get_status_manifestacao',
        'get_dias_sem_movimentacao',
    )
    list_filter = (
        CustomTabListFilter,
        RecomendacaoFilter,
        'recomendacao__relatorio',
        CampusFilter,
        PrazoFilter,
        'recomendacao__relatorio__acao',
        'recomendacao__relatorio__ano_paint',
        'status',
        'recomendacao__monitor',
        'recomendacao__revisor',
        'unidade',
    )
    search_fields = ('recomendacao__numero',)
    # list_display_icons = True
    list_per_page = 25
    export_to_xls = True
    show_count_on_tabs = True
    ordering = ('ultima_solicitacao__prazo_atual',)

    def delete_model(self, request, obj: Monitoramento):
        if not obj.pode_excluir(request.user):
            self.message_user(request, 'Você não tem permissão para realizar essa ação.', level='error')
            return
        setor_auditado = obj.unidade
        recomendacao = obj.recomendacao
        request._redirect_after_delete = f'{recomendacao.get_absolute_url()}'
        with transaction.atomic():
            obj.delete()
            recomendacao.unidades.remove(setor_auditado)
        self.message_user(request, 'Monitoramento removido com sucesso.')

    def response_delete(self, request, obj_display, obj_id):
        return httprr(getattr(request, '_redirect_after_delete', '..'))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj: Monitoramento = self.get_object(request, unquote(object_id))
        if obj:
            redirect_url = f'{obj.recomendacao.get_absolute_url()}?tab={slugify(obj.unidade)}'
            return HttpResponseRedirect(redirect_url)
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def get_recomendacao(self, obj: Monitoramento):
        return obj.recomendacao.identificador

    get_recomendacao.short_description = 'Recomendação'

    def get_acao(self, obj: Monitoramento):
        return obj.recomendacao.relatorio.acao

    get_acao.short_description = 'Ação'

    def get_paint(self, obj: Monitoramento):
        return obj.recomendacao.relatorio.ano_paint

    get_paint.short_description = 'Ano/PAINT'

    def get_nucleo(self, obj: Monitoramento):
        return obj.recomendacao.nucleo

    get_nucleo.short_description = 'Nucleo Executor'

    def get_status_manifestacao(self, obj: Monitoramento):
        ultima = obj.manifestacoes.last()
        if ultima:
            status = ultima.get_status_display()
            return format_html('<span class="status status-info">{}</span>', status)
        return format_html('<span class="status status-warning">{}</span>', 'Sem manifestação')

    get_status_manifestacao.short_description = 'Última Manifestação'

    def get_dias_sem_movimentacao(self, obj: Monitoramento):
        # ultima_manifestacao: Manifestacao = obj.manifestacoes.last()
        if not obj.ativo or obj.registrado:
            return format_html('<span class="tag tag-success">{}</span>', 'Em dia')
        # Se o obj não está em monitoramento, ele tem uma solicitação
        ultima_movimentacao = obj.get_ultima_movimentacao()
        if not ultima_movimentacao:
            return format_html('<span class="tag tag-info">{}</span>', 'Sem dados')

        hoje = get_datetime_now().date()
        data_referencia = ultima_movimentacao.ultima_movimentacao_em.date()
        dias = (hoje - data_referencia).days
        if dias < 14:
            cor = 'success'
        elif dias < 30:
            cor = 'warning'
        else:
            cor = 'error'

        return format_html('<span class="status status-{}">{} dia(s)</span>', cor, dias)

    get_dias_sem_movimentacao.short_description = 'Dias sem movimentação'

    def get_status(self, obj: Monitoramento):
        display, classe = MonitoramentoStatus.get_display_and_class(obj.status)
        return format_html('<span class="status status-{}"> {}</span>', classe, display)

    get_status.short_description = 'Situação'

    get_status.short_description = 'Situação'

    def get_monitor(self, obj: Monitoramento):
        return format_profile(obj.recomendacao.monitor)

    get_monitor.short_description = 'Monitor'

    def get_revisor(self, obj: Monitoramento):
        return format_profile(obj.revisor) if obj.revisor else None

    get_revisor.short_description = 'Revisor'

    def get_prazo_atual(self, obj: Monitoramento):
        return obj.prazo_atual or '-'

    get_prazo_atual.short_description = 'Prazo Atual'

    def get_data_limite(self, obj: Monitoramento):
        return obj.data_limite

    get_data_limite.short_description = 'Data Limite'

    def get_unidade(self, obj: Monitoramento):
        return obj.unidade

    get_unidade.short_description = 'Setor'

    def tab_meus_monitoramentos_a_monitorar(self, request, queryset):
        auditor = request.user.get_vinculo()
        return queryset.filter(recomendacao__monitor=auditor)

    tab_meus_monitoramentos_a_monitorar.short_description = 'Meus Monitoramentos'

    def tab_posicionamentos_a_revisar(self, request, queryset):
        auditor = request.user.get_vinculo()
        return queryset.filter(
            recomendacao__revisor=auditor,
            manifestacoes__posicionamentos__status__in=[
                PosicionamentoStatus.REVISAO_PENDENTE,
                PosicionamentoStatus.EM_REVISAO,
            ],
        ).distinct()

    tab_posicionamentos_a_revisar.short_description = 'Posicionamentos a revisar'

    def tab_manifestacoes_a_receber(self, request, queryset):
        qs = queryset.filter(manifestacoes__status=ManifestacaoStatus.ENVIADA)
        if not eh_auditor_chefe(request.user):
            auditor = request.user.get_vinculo()
            qs = qs.filter(recomendacao__monitor=auditor)
        return qs.distinct()

    tab_manifestacoes_a_receber.short_description = 'Manifestações a receber'

    def tab_manifestacoes_a_analisar(self, request, queryset):
        qs = queryset.filter(manifestacoes__status=ManifestacaoStatus.RECEBIDA)
        if not eh_auditor_chefe(request.user):
            auditor = request.user.get_vinculo()
            qs = qs.filter(recomendacao__monitor=auditor)
        return qs

    tab_manifestacoes_a_analisar.short_description = 'Manifestações em análise'

    def tab_monitoramento_expirados(self, request, queryset):
        expirados_qs = queryset.expirados()
        if not eh_auditor_chefe(request.user):
            auditor = request.user.get_vinculo()
            return expirados_qs.filter(recomendacao__monitor=auditor)
        return expirados_qs

    tab_monitoramento_expirados.short_description = 'Monitoramentos expirados'

    def get_tabs(self, request):
        return [
            'tab_meus_monitoramentos_a_monitorar',
            'tab_manifestacoes_a_receber',
            'tab_manifestacoes_a_analisar',
            'tab_monitoramento_expirados',
            'tab_posicionamentos_a_revisar',
        ]


admin.site.register(Monitoramento, MonitoramentoAdmin)


class TipoPosicionamentoValidoAdmin(ModelAdminPlus):
    list_display = ('tipo_manifestacao', 'tipo_posicionamento')
    list_filter = ('tipo_manifestacao', 'tipo_posicionamento')
    list_display_icons = True
    list_per_page = 25


admin.site.register(TipoPosicionamentoValido, TipoPosicionamentoValidoAdmin)


class MotivacaoAdmin(ModelAdminPlus):
    list_display = ('tipo_posicionamento', 'motivo')
    list_filter = ('tipo_posicionamento',)
    search_fields = ('tipo_posicionamento', 'motivo')
    ordering = ('tipo_posicionamento',)
    list_per_page = 25
    list_display_icons = True


admin.site.register(Motivacao, MotivacaoAdmin)


class ClasseBeneficioAdmin(ModelAdminPlus):
    list_display = ('descricao', 'tipo')
    list_filter = ('tipo',)
    list_per_page = 25
    list_display_icons = True


admin.site.register(ClasseBeneficio, ClasseBeneficioAdmin)


class BeneficioAdmin(ModelAdminPlus):
    list_display = ('id', 'ano', 'tipo', 'get_status', 'origem_beneficio', 'classe', 'get_natureza', 'get_monitor', 'get_objeto_associado')
    list_filter = ('ano', 'tipo', 'status', 'origem_beneficio', 'classe', 'monitor', 'auditoria_detalhamentofinanceiro__natureza')
    search_fields = ('descricao', 'classe__descricao')
    list_per_page = 25
    list_display_icons = True
    form = BeneficioForm
    fieldsets = BeneficioForm.fieldsets

    class Media:
        js = ('auditoria/js/beneficio_form.js',)

    def save_model(self, request, obj, form, change):
        try:
            form.save(commit=True)
        except ValueError as e:
            messages.error(request, str(e))

    def get_status(self, obj: Beneficio):
        return format_html(status(obj.get_status_display()))

    get_status.short_description = 'Status'

    def get_natureza(self, obj: Beneficio):
        if obj.eh_financeiro:
            return obj.detalhamento_financeiro.get_natureza_display()
        return 'Não definido'

    get_natureza.short_description = 'Natureza'

    def get_monitor(self, obj: Beneficio):
        return format_profile(obj.monitor)

    get_monitor.short_description = 'Monitor'

    def get_objeto_associado(self, obj: Beneficio):
        if obj.content_object:
            return mark_safe(f'<a href="{obj.content_object.get_reference_object_url()}">{obj.content_object}</a>')
        return 'Nenhum objeto associado'

    get_objeto_associado.short_description = 'Objeto Associado'

    def get_documentos(self, obj: Beneficio):
        """
        Mostra a lista de documentos associados ao benefício.
        """
        documentos = obj.documentos.all()
        if documentos.exists():
            return ', '.join([doc.nome for doc in documentos])
        return 'Nenhum documento'

    get_documentos.short_description = 'Documentos Anexados'

    def has_change_permission(self, request, obj: Beneficio = None):
        has_permission = super().has_change_permission(request, obj) and obj is not None
        if has_permission:
            has_permission = obj.planejado if obj.eh_financeiro else obj.ativo
            return has_permission and (request.user.get_vinculo() == obj.monitor or eh_auditor_chefe(request.user) or request.user.is_superuser)
        return False

    def response_add(self, request, obj, post_url_continue=None):
        if '_continue' not in request.POST:
            app_label = Beneficio._meta.app_label
            model_name = Beneficio._meta.model_name
            changelist_url = reverse(f'admin:{app_label}_{model_name}_changelist')
            # Redirect to the list view
            return redirect(changelist_url)
        return super().response_add(request, obj, post_url_continue)


admin.site.register(Beneficio, BeneficioAdmin)


class UnidadeAfetadaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(UnidadeAfetada, UnidadeAfetadaAdmin)


class AlcanceEstrategicoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(AlcanceEstrategico, AlcanceEstrategicoAdmin)


class PaintAdmin(ModelAdminPlus):
    form = PaintForm
    list_display = ('ano', 'criado_por', 'criado_em', 'atualizado_por', 'atualizado_em')
    search_fields = ('ano__ano',)
    list_display_icons = True

    def get_atualizado_por(self, obj: Paint):
        return mark_safe(format_profile(obj.atualizado_por)) if obj.atualizado_por else '-'

    get_atualizado_por.short_description = 'Atualizado Por'

    def save_model(self, request, obj, form, change):
        try:
            if not change:
                obj.criado_por = request.user
            obj.atualizado_por = request.user.get_vinculo()
            obj.save()
        except ValueError as e:
            messages.error(request, str(e))


admin.site.register(Paint, PaintAdmin)


@admin.register(TipoAfastamento)
class TipoAfastamentoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('descricao',)
    list_display_icons = True

    def save_model(self, request, obj, form, change):
        try:
            form.save(commit=True)
        except ValueError as e:
            messages.error(request, str(e))


@admin.register(PlanejamentoAnual)
class PlanejamentoAnualAdmin(ModelAdminPlus):
    list_display = (
        'auditor',
        'paint',
        'get_status',
        'carga_horaria_prevista',
        'carga_horaria_afastada',
        'carga_horaria_liquida',
    )
    list_filter = (
        'paint',
        'status',
    )
    search_fields = ('auditor__nome',)
    list_display_icons = True

    def get_status(self, obj: Beneficio):
        return format_html(status(obj.get_status_display()))

    get_status.short_description = 'Status'


@admin.register(LiberacaoProgramada)
class LiberacaoProgramadaAdmin(ModelAdminPlus):
    form = LiberacaoProgramadaForm
    list_display = (
        'nome',
        'categoria_badge',
        'tipo_expediente_display',
        'escopo',
        'periodo_ou_recorrencia',
        'ativo',
    )
    list_display_links = ('nome',)

    # filtros laterais
    list_filter = (
        'categoria',
        'tipo_expediente',
        'ativo',
        ('uo', admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ('nome', 'descricao')
    date_hierarchy = 'data_inicio'
    fieldsets = LiberacaoProgramadaForm.fieldsets
    actions = ('marcar_ativo', 'marcar_inativo')

    @admin.display(description='Categoria', ordering='categoria')
    def categoria_badge(self, obj: LiberacaoProgramada):
        cor = {
            CategoriaLiberacao.FERIADO: 'status-info',  # azul
            CategoriaLiberacao.FERIADO_RECORRENTE: 'status-success',  # verde
            CategoriaLiberacao.RECESSO: 'status-warning',  # âmbar
        }.get(obj.categoria)  # cinza
        return format_html(
            '<span class="status {}">{}</span>',
            cor,
            obj.get_categoria_display(),
        )

    @admin.display(description='Tipo de Expediente', ordering='tipo_expediente')
    def tipo_expediente_display(self, obj: LiberacaoProgramada):
        return obj.get_tipo_expediente_display()

    @admin.display(description='Escopo', ordering='uo')
    def escopo(self, obj: LiberacaoProgramada):
        return 'GLOBAL' if obj.uo_id is None else str(obj.uo.nome)

    @admin.display(description='Quando')
    def periodo_ou_recorrencia(self, obj: LiberacaoProgramada):
        if obj.categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            if obj.mes_recorrente and obj.dia_recorrente:
                return f'{obj.dia_recorrente:02d}/{obj.mes_recorrente:02d} (anual)'
            return '—'
        # pontual
        if obj.data_inicio and obj.data_fim:
            return f'{obj.data_inicio:%d/%m/%Y} — {obj.data_fim:%d/%m/%Y}'
        if obj.data_inicio:
            return f'{obj.data_inicio:%d/%m/%Y}'
        return '—'

    # ------- Ações -------
    @admin.action(description='Marcar como ATIVO')
    def marcar_ativo(self, request, queryset):
        updated = queryset.update(ativo=True)
        self.message_user(request, f'{updated} registro(s) marcados como ATIVO.')

    @admin.action(description='Marcar como INATIVO')
    def marcar_inativo(self, request, queryset):
        updated = queryset.update(ativo=False)
        self.message_user(request, f'{updated} registro(s) marcados como INATIVO.')

    def has_add_permission(self, request):
        has_perm = super().has_add_permission(request)
        if not has_perm:
            vinculo = request.user.get_vinculo()
            has_perm = tem_permissao(vinculo, AcaoPermissao.ADICIONAR, LiberacaoProgramada)
        return has_perm

    def has_change_permission(self, request, obj=None):
        has_perm = super().has_change_permission(request, obj)
        if not has_perm:
            vinculo = request.user.get_vinculo()
            has_perm = tem_permissao(vinculo, AcaoPermissao.ALTERAR, LiberacaoProgramada)
        return has_perm

    def has_delete_permission(self, request, obj=None):
        has_perm = super().has_delete_permission(request, obj)
        if not has_perm:
            vinculo = request.user.get_vinculo()
            has_perm = tem_permissao(vinculo, AcaoPermissao.EXCLUIR, LiberacaoProgramada)
        return has_perm

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            acao = AcaoPermissao.ALTERAR if change else AcaoPermissao.ADICIONAR
            vinculo = request.user.get_vinculo()
            exige_permissao(vinculo, acao, LiberacaoProgramada)
        obj.save(validate=considerar_liberacoes_ponto())

    def delete_model(self, request, obj):
        if not request.user.is_superuser:
            vinculo = request.user.get_vinculo()
            exige_permissao(vinculo, AcaoPermissao.EXCLUIR, LiberacaoProgramada)
        super().delete_model(request, obj)


class ContentTypeAuditoriaFilter(admin.SimpleListFilter):
    title = 'Modelo da auditoria'
    parameter_name = 'ct_auditoria'

    def lookups(self, request, model_admin):
        cts = ContentType.objects.filter(app_label='auditoria').order_by('model')
        lookups = []
        for ct in cts:
            model_class = ct.model_class()
            if model_class:
                label = model_class._meta.verbose_name_plural.title()
            else:
                # fallback se não encontrar a classe
                label = f'{ct.app_label}.{ct.model}'
            lookups.append((str(ct.id), label))
        return lookups

    def queryset(self, request, queryset):
        val = self.value()
        if val:
            return queryset.filter(content_type_id=val)
        return queryset


@admin.register(PermissaoDeChefe)
class PermissaoDeChefeAdmin(ModelAdminPlus):
    form = ConcederPermissaoDeChefeForm
    list_display = (
        'get_auditor',
        'content_type_label',
        'acao',
        'status',
        'concedido_em',
        'concedido_por',
        'revogado_em',
        'revogado_por',
    )
    list_filter = (
        'acao',
        ContentTypeAuditoriaFilter,
        'concedido_em',
        'revogado_em',
    )
    search_fields = (
        'vinculo_permitido__pessoa__nome',
        'vinculo_permitido__pessoa__pessoafisica__cpf',
        'concedido_por__username',
        'revogado_por__username',
    )
    ordering = ('-concedido_em',)

    def get_auditor(self, obj):
        return format_profile(obj.vinculo_permitido)

    get_auditor.short_description = 'Auditor'

    def content_type_label(self, obj):
        model_class = obj.content_type.model_class()
        return f'{model_class._meta.verbose_name_plural.title()}' if model_class else str(obj.content_type)

    content_type_label.short_description = 'Modelo'

    def acao(self, obj):
        return obj.get_acao_display()

    def status(self, obj):
        if obj.revogado_em:
            return format_html('<span class="badge status-danger">Revogado</span>')
        return format_html('<span class="badge status-success">Ativo</span>')

    status.short_description = 'Status'

    # ação em lote para revogar
    actions = ['revogar_selecionados']

    def revogar_selecionados(self, request, queryset):
        count = 0
        for perm in queryset.filter(revogado_em__isnull=True):
            perm.revogar(por_usuario=request.user, motivo='Revogado via ação em lote no admin')
            count += 1
        self.message_user(request, f'{count} permissões revogadas.')

    revogar_selecionados.short_description = 'Revogar permissões selecionadas'

    def get_queryset(self, request, manager=None, *args, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if eh_auditor_chefe(request.user):
            return qs
        vinculo = request.user.get_vinculo()
        qs = qs.filter(Q(vinculo_permitido=vinculo) | Q(concedido_por=request.user) | Q(revogado_por=request.user)).distinct()
        return qs
