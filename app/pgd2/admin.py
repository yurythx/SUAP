from django.contrib import admin
from django.db.models import F, Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.utils import get_sigla_reitoria
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_profile, status
from djtools.utils import get_client_ip
from pgd2.api_pgd2_v2 import ApiPgd2V2
from pgd2.forms import (
    ComissaoPGDForm,
    ConfiguracaoOrientacaoPitForm,
    ConfiguracaoOrientacaoPlanoEntregasSetorialForm,
    ConfiguracaoPerfilServidorForm,
    DocumentoAdesaoPesServidorForm,
    DocumentoAdesaoServidorForm,
    PeriodoPesForm,
    PeriodoPitRitForm,
    PGDExteriorForm,
    PlanoEntregasSetorialAddForm,
    SetorHabilitacaoForm,
)
from pgd2.models import (
    ComissaoPGD,
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoEntregasSetorial,
    ConfiguracaoPerfilServidor,
    DocumentoAdesaoPesServidor,
    DocumentoAdesaoServidor,
    JustificativaDesligamentoPgd,
    LogApi,
    LogApiDetalhe,
    LogApiParticipanteEnvio,
    LogApiPesEnvio,
    LogApiPitEnvio,
    ParticipantePgd,
    PeriodoPes,
    PeriodoPitRit,
    PGDExterior,
    PlanoEntregasSetorial,
    PlanoEntregasSetorialAprovacao,
    PlanoEntregasSetorialConsulta,
    RegistroAcaoPES,
    SetorHabilitacao,
    SetorPgdApi,
    SolicitacaoAdesaoPesServidor,
    SolicitacaoAdesaoServidor,
)
from pgd2.utils import get_setores_pgd, pode_consultar_dados_api, setores_que_sou_chefe_hoje, utilizar_integracao_com_pde
from rh.models import Setor, UnidadeOrganizacional
from suap import nomenclatura

# ====================================================
# CADASTROS BÁSICOS
# ====================================================


@admin.register(LogApi)
class LogApiAdmin(ModelAdminPlus):
    list_display = (
        'data_hora_inicio',
        'data_hora_fim',
        'qtd_envios_pes',
        'get_qtd_erros_envio_pes',
        'qtd_envios_participante',
        'get_qtd_erros_envio_participante',
        'qtd_envios_pit',
        'get_qtd_erros_envio_pits',
        'data_proximo_envio_por_sucesso',
        'url',
    )
    list_display_icons = True
    ordering = ['-id']

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_log_api_pgd2', args=[obj_pk]))


class LogApiFilter(admin.SimpleListFilter):
    title = 'Log'
    parameter_name = 'lg'

    def lookups(self, request, model_admin):
        opcoes = []
        for log in LogApi.objects.all().order_by('-data_hora_inicio'):
            opcoes.append((log.id, log))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(log=self.value())
        return queryset


@admin.register(LogApiDetalhe)
class LogApiDetalheAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'log',
        'data',
        'url',
        'erro_envio',
    )
    list_display_icons = True
    list_filter = (LogApiFilter,)
    ordering = ('-id',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)


@admin.register(LogApiPesEnvio)
class LogApiPesEnvioAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'pes',
        'get_status',
        'data_hora_envio_erro',
    )
    list_display_icons = True
    list_filter = (
        LogApiFilter,
        'status',
    )
    search_fields = ('pes__identificador_externo',)
    ordering = ('-id',)

    def get_status(self, obj):
        return mark_safe(status(obj.get_status_display()))

    get_status.short_description = 'Status'

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)


@admin.register(LogApiParticipanteEnvio)
class LogApiParticipanteEnvioAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'participante',
        'get_status',
        'data_hora_envio_erro',
    )
    list_display_icons = True
    list_filter = (
        LogApiFilter,
        'status',
    )
    search_fields = ('participante__servidor__matricula',)
    ordering = ('-id',)

    def get_status(self, obj):
        return mark_safe(status(obj.get_status_display()))

    get_status.short_description = 'Status'

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)


@admin.register(LogApiPitEnvio)
class LogApiPitEnvioEnvioAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'pit',
        'get_status',
        'data_hora_envio_erro',
    )
    list_display_icons = True
    list_filter = (
        LogApiFilter,
        'status',
    )
    search_fields = ('pit__adesao__servidor__matricula', 'erro_envio')
    ordering = ('-id',)

    def get_status(self, obj):
        return mark_safe(status(obj.get_status_display()))

    get_status.short_description = 'Status'

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)


class ParticipanteEnviadoFilter(admin.SimpleListFilter):
    title = 'Enviado pela API'
    parameter_name = 'eapi'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(data_hora_envio_api__isnull=False)
        if self.value() == '2':
            return queryset.filter(data_hora_envio_api__isnull=True)
        return queryset


@admin.register(ParticipantePgd)
class ParticipantePgdAdmin(ModelAdminPlus):
    list_display = (
        'servidor',
        'cod_unidade_lotacao',
        'modalidade_execucao',
        'data_assinatura_tcr',
        'situacao',
        'deve_enviar_pela_api',
        'data_hora_envio_api',
    )
    list_display_icons = True
    list_filter = (ParticipanteEnviadoFilter, 'situacao')
    search_fields = ['servidor__pessoa_fisica__nome', 'servidor__matricula', 'cod_unidade_lotacao']

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return pode_consultar_dados_api(request.user)


@admin.register(ComissaoPGD)
class ComissaoPGDAdmin(ModelAdminPlus):
    list_display = ('titulo', 'get_membros', 'estah_vigente', 'eh_sistemica', 'get_campus_abragencia', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = (
        'eh_sistemica',
        'campus_abragencia',
        'cancelado',
    )
    list_display_links = None
    date_hierarchy = 'data_inicio'
    search_fields = ('titulo',)

    form = ComissaoPGDForm

    fieldsets = (
        ('Dados Básicos', {'fields': ('titulo', 'membros')}),
        ('Abrangência', {'fields': ('eh_sistemica', 'campus_abragencia')}),
        ('Vigência', {'fields': ('data_inicio', 'data_fim', 'cancelado')}),
        ('Confirmação', {'fields': ('confirmacao', 'senha')}),
    )

    def get_campus_abragencia(self, obj):
        strs = []
        for m in obj.campus_abragencia.all():
            strs.append(f'{m.sigla} - {m.nome}')
        return ' / '.join(strs)

    get_campus_abragencia.short_description = 'Abrangência (campus)'

    def get_membros(self, obj):
        strs = []
        for m in obj.membros.all():
            strs.append(format_profile(m))
        return mark_safe(' / '.join(strs))

    get_membros.short_description = 'Membros'

    def response_add(self, request, obj, post_url_continue=None):
        if obj:
            ComissaoPGD.sincronizar_permissoes_comissao()
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if obj:
            ComissaoPGD.sincronizar_permissoes_comissao()
        return super().response_change(request, obj)

    def has_view_permission(self, request, obj=None):
        # return ComissaoPGD.pode_cadastrar_alterar(request.user)
        return False

    def has_change_permission(self, request, obj=None):
        return ComissaoPGD.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ComissaoPGD.pode_cadastrar_alterar(request.user)


@admin.register(JustificativaDesligamentoPgd)
class JustificativaDesligamentoPgdAdmin(ModelAdminPlus):
    list_display = ('titulo', 'descricao', 'ativo', 'servidor', 'chefe', 'gestao', 'qtd_dias_punicao')

    list_display_icons = True

    search_fields = ('titulo', 'descricao')
    list_filter = ('ativo', 'servidor', 'chefe', 'gestao')

    def has_view_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return JustificativaDesligamentoPgd.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return JustificativaDesligamentoPgd.pode_cadastrar_alterar(request.user)


@admin.register(ConfiguracaoOrientacaoPlanoEntregasSetorial)
class ConfiguracaoOrientacaoPlanoEntregasSetorialAdmin(ModelAdminPlus):
    list_display = ('id', 'eh_sistemica', 'get_campus_abragencia', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = (
        'eh_sistemica',
        'cancelado',
    )

    form = ConfiguracaoOrientacaoPlanoEntregasSetorialForm

    fieldsets = (
        ('Orientação', {'fields': ('orientacao',)}),
        ('Abrangência', {'fields': ('eh_sistemica', 'campus_abragencia')}),
        ('Vigência', {'fields': ('data_inicio', 'data_fim', 'cancelado')}),
    )

    def get_campus_abragencia(self, obj):
        strs = []
        for m in obj.campus_abragencia.all():
            strs.append(f'{m.sigla} - {m.nome}')
        return ' / '.join(strs)

    get_campus_abragencia.short_description = 'Abrangência (campus)'

    def has_view_permission(self, request, obj=None):
        return ComissaoPGD.user_estah_em_gestao_pgd(request.user)

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoOrientacaoPlanoEntregasSetorial.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoOrientacaoPlanoEntregasSetorial.pode_cadastrar_alterar(request.user)


@admin.register(DocumentoAdesaoServidor)
class DocumentoAdesaoServidorAdmin(ModelAdminPlus):
    list_display = ('estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = ('cancelado',)
    date_hierarchy = 'data_inicio'

    form = DocumentoAdesaoServidorForm

    def has_view_permission(self, request, obj=None):
        # return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)
        return False

    def has_change_permission(self, request, obj=None):
        return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)


@admin.register(ConfiguracaoPerfilServidor)
class ConfiguracaoPerfilServidorAdmin(ModelAdminPlus):
    list_display = ('id', 'categoria', 'deve_ter_funcao', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = (
        'situacoes',
        'funcoes',
        'cancelado',
    )
    form = ConfiguracaoPerfilServidorForm

    def has_view_permission(self, request, obj=None):
        # return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)
        return False

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)

    def render_change_form(self, request, context, *args, **kwargs):
        html_info = '<p class="alert alert-info">O perfil do Servidor será definido conforme as regras do PGD. Para a correta seleção das situações e funções adequadas ao PGD você pode consultar a Gestão de Pessoas.</p>'
        extra = {'info_extra': html_info}
        context.update(extra)
        return super().render_change_form(request, context, *args, **kwargs)


@admin.register(DocumentoAdesaoPesServidor)
class DocumentoAdesaoPesServidorAdmin(ModelAdminPlus):
    list_display = ('estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = ('cancelado',)
    date_hierarchy = 'data_inicio'

    form = DocumentoAdesaoPesServidorForm

    def has_view_permission(self, request, obj=None):
        # return DocumentoAdesaoPesServidor.pode_cadastrar_alterar(request.user)
        return False

    def has_change_permission(self, request, obj=None):
        return DocumentoAdesaoPesServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return DocumentoAdesaoPesServidor.pode_cadastrar_alterar(request.user)


@admin.register(ConfiguracaoOrientacaoPit)
class ConfiguracaoOrientacaoPitAdmin(ModelAdminPlus):
    list_display = ('id', 'eh_sistemica', 'get_campus_abragencia', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = (
        'eh_sistemica',
        'cancelado',
    )

    form = ConfiguracaoOrientacaoPitForm

    fieldsets = (
        ('Orientação', {'fields': ('orientacao',)}),
        ('Abrangência', {'fields': ('eh_sistemica', 'campus_abragencia')}),
        ('Vigência', {'fields': ('data_inicio', 'data_fim', 'cancelado')}),
    )

    def get_campus_abragencia(self, obj):
        strs = []
        for m in obj.campus_abragencia.all():
            strs.append(f'{m.sigla} - {m.nome}')
        return ' / '.join(strs)

    get_campus_abragencia.short_description = 'Abrangência (campus)'

    def has_view_permission(self, request, obj=None):
        # return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)
        return False

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)


@admin.register(PeriodoPes)
class PeriodoPesAdmin(ModelAdminPlus):
    list_display = ('titulo', 'data_inicio', 'data_fim', 'data_prazo_solicitar_avaliacao_execucao', 'cancelado')
    list_display_icons = True
    list_filter = ('cancelado',)
    form = PeriodoPesForm
    date_hierarchy = 'data_inicio'
    ordering = ('-data_inicio',)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.has_perm('rh.eh_servidor'))

    def has_change_permission(self, request, obj=None):
        return PeriodoPes.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return PeriodoPes.pode_cadastrar_alterar(request.user)


@admin.register(PeriodoPitRit)
class PeriodoPitAdmin(ModelAdminPlus):
    list_display = (
        'titulo',
        'periodo_pes',
        'data_inicio',
        'data_fim',
        'data_prazo_entrega_pit',
        'data_prazo_entrega_rit',
        'data_prazo_homologacao_pit',
        'data_prazo_homologacao_rit',
        'cancelado',
        'get_solicitacao_preenchimento_formulario_pesquisa',
        'get_opcoes',
    )

    list_display_icons = True

    list_filter = ('cancelado',)

    form = PeriodoPitRitForm

    ordering = ('-data_inicio',)

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'titulo',
                    'periodo_pes',
                    'data_inicio',
                    'data_fim',
                    'cancelado',
                )
            },
        ),
        (nomenclatura.plano_individual_de_trabalho_sigla_pgd2, {'fields': ('data_prazo_entrega_pit', 'data_prazo_homologacao_pit')}),
        (nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2, {'fields': ('data_prazo_entrega_rit', 'data_prazo_homologacao_rit')}),
    )

    date_hierarchy = 'data_inicio'

    def has_view_permission(self, request, obj=None):
        return bool(request.user.has_perm('rh.eh_servidor'))

    def has_change_permission(self, request, obj=None):
        return PeriodoPitRit.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return PeriodoPitRit.pode_cadastrar_alterar(request.user)

    def get_solicitacao_preenchimento_formulario_pesquisa(self, obj):
        if obj.preencher_questionario_pesquisa:
            return mark_safe('<span class="status status-sucess">Ativado</span>')
        else:
            return mark_safe('<span class="status status-error">Inativado</span>')

    get_solicitacao_preenchimento_formulario_pesquisa.short_description = 'Solicitação de preenchimento do questionário de pesquisa'

    def get_opcoes(self, obj):
        texto = '-'
        if PeriodoPitRit.pode_cadastrar_alterar(self.request.user):
            texto = '<ul class="action-bar">'
            if obj.preencher_questionario_pesquisa:
                texto += f'<li><a href="/pgd2/ativar_desativar_preencher_questionario_pesquisa/{obj.id}/" class="btn danger">Desativar solicitação de preenchimento do questionário de pesquisa</a></li>'
            else:
                texto += f'<li><a href="/pgd2/ativar_desativar_preencher_questionario_pesquisa/{obj.id}/" class="btn success">Ativar solicitação de preenchimento do questionário de pesquisa</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'


# ====================================================
# PES - Plano de Entregas Setorial
# ====================================================


class PesCadastroSetorSouChefeComDescentesFilter(admin.SimpleListFilter):
    title = 'Setor'
    parameter_name = 'setcd_a'

    def lookups(self, request, model_admin):
        opcoes = []
        setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        for setor in setores:
            opcoes.append((setor.id, setor))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_id=self.value())
        return queryset


class PesAprovacaoSetorSouChefeComDescentesFilter(admin.SimpleListFilter):
    title = 'Setor'
    parameter_name = 'setcda_a'

    def lookups(self, request, model_admin):
        opcoes = []
        setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        for setor in setores:
            opcoes.append((setor.id, setor))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_para_aprovacao_id=self.value())
        return queryset


class PesAprovacaoPeriodoPesFilter(admin.SimpleListFilter):
    title = 'Período PES'
    parameter_name = 'ppesa_a'

    def lookups(self, request, model_admin):
        opcoes = []
        periodos = PeriodoPes.objects.filter(cancelado=False).order_by('-data_inicio')
        for periodo in periodos:
            opcoes.append((periodo.id, periodo))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(periodo_pes_id=self.value())
        return queryset


@admin.register(PlanoEntregasSetorial)
class PlanoEntregasSetorialCadastroAdmin(ModelAdminPlus):
    list_display = ('setor', 'get_data_inicio', 'get_data_fim', 'get_situacao', 'get_situacao_avaliacao')
    list_display_icons = True
    list_filter = (PesCadastroSetorSouChefeComDescentesFilter, 'periodo_pes', 'situacao', 'situacao_avaliacao')

    add_form = PlanoEntregasSetorialAddForm

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def get_situacao_avaliacao(self, obj):
        if obj.situacao_avaliacao:
            return mark_safe(status(obj.get_situacao_avaliacao_display()))
        return None

    get_situacao_avaliacao.short_description = 'Situação da avaliação da execução'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_pes_pgd2', args=[obj_pk]))

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return PlanoEntregasSetorial.pode_visualizar_lista(request.user)

    def has_add_permission(self, request):
        return PlanoEntregasSetorial.pode_iniciar_cadastrar(request.user)[0]

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        super().save_model(request, obj, form, change)

        if obj and obj.id and not change:
            ip = get_client_ip(request)
            RegistroAcaoPES.objects.create(tipo=RegistroAcaoPES.TIPO_CRIACAO, pes=obj, ip=ip, observacao='')

    def response_add(self, request, obj, post_url_continue=None):
        super().response_add(request, obj, post_url_continue)
        return self.render_view_object(request, obj.id)

    def response_change(self, request, obj):
        super().response_change(request, obj)
        return self.render_view_object(request, obj.id)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        return qs.filter(setor__in=setores).order_by('periodo_pes__data_inicio')


@admin.register(PlanoEntregasSetorialAprovacao)
class PlanoEntregasSetorialAprovacaoAdmin(ModelAdminPlus):
    list_display = ('setor', 'get_data_inicio', 'get_data_fim', 'get_situacao')
    list_display_icons = True
    list_filter = (PesAprovacaoSetorSouChefeComDescentesFilter, PesAprovacaoPeriodoPesFilter)

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_pes_pgd2', args=[obj_pk]))

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return PlanoEntregasSetorial.pode_visualizar_lista(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # qs = super().get_queryset(request)
        # setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        # return qs.filter(situacao=PlanoEntregasSetorial.SOLICITADO_APROVACAO, setor_para_aprovacao__in=setores)
        return PlanoEntregasSetorial.get_pess_pendendentes_aprovacao(request.user)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Planos de Entregas Setorial - A Aprovar'
        return super().changelist_view(request, extra_context=extra_context)


# ====================================================
# Adesão PGD
# ====================================================


@admin.register(SolicitacaoAdesaoServidor)
class SolicitacaoAdesaoServidorAdmin(ModelAdminPlus):
    list_display = ('servidor', 'get_setor', 'get_situacao')
    list_display_icons = True

    list_filter = (CustomTabListFilter,)
    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')

    label_input_search_fields = 'Nome/Matrícula Servidor'

    show_tab_any_data = False

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return SolicitacaoAdesaoServidor.pode_visualizar_lista(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_setor(self, obj):
        return obj.servidor.setor

    get_setor.short_description = 'Setor'

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_solicitacao_adesao_pgd2', args=[obj_pk]))

    def get_tabs(self, request):
        return ['tab_deve_aprovar', 'tab_pode_aprovar']

    def tab_deve_aprovar(self, request, queryset):
        ids_solicitacoes = SolicitacaoAdesaoServidor.get_solicitacoes_pendendentes_avaliacao_chefe(
            request.user, apenas_chefe_direto=True
        ).values_list('id', flat=True)
        return queryset.filter(id__in=ids_solicitacoes)

    tab_deve_aprovar.short_description = 'Deve aprovar'

    def tab_pode_aprovar(self, request, queryset):
        ids_solicitacoes = SolicitacaoAdesaoServidor.get_solicitacoes_pendendentes_avaliacao_chefe(
            request.user, apenas_chefe_direto=False
        ).values_list('id', flat=True)
        return queryset.filter(id__in=ids_solicitacoes)

    tab_pode_aprovar.short_description = 'Pode aprovar'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(situacao=SolicitacaoAdesaoServidor.SOLICITADO).exclude(servidor=request.user.get_relacionamento())
        return qs

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Adesão do Servidor ao PGD - A Aprovar'
        return super().changelist_view(request, extra_context=extra_context)


# ====================================================
# Adesão PES
# ====================================================


@admin.register(SolicitacaoAdesaoPesServidor)
class SolicitacaoAdesaoPesServidorAdmin(ModelAdminPlus):
    list_display = ('get_servidor', 'get_setor_servidor', 'get_setor', 'get_situacao')
    list_display_icons = True

    list_filter = (CustomTabListFilter,)
    search_fields = ('adesao__servidor__pessoa_fisica__nome', 'adesao__servidor__matricula')

    label_input_search_fields = 'Nome/Matrícula Servidor'

    show_tab_any_data = False

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return SolicitacaoAdesaoPesServidor.pode_visualizar_lista(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_servidor(self, obj):
        return obj.adesao.servidor

    get_servidor.short_description = 'Servidor'

    def get_setor_servidor(self, obj):
        return obj.adesao.servidor.setor

    get_setor_servidor.short_description = 'Setor do Servidor'

    def get_setor(self, obj):
        return obj.setor

    get_setor.short_description = 'Setor PES'

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_solicitacao_adesao_pes_pgd2', args=[obj_pk]))

    def get_tabs(self, request):
        return ['tab_deve_aprovar', 'tab_pode_aprovar']

    def tab_deve_aprovar(self, request, queryset):
        ids_solicitacoes = SolicitacaoAdesaoPesServidor.get_solicitacoes_pendendentes_avaliacao_chefe(
            request.user, apenas_chefe_direto=True
        ).values_list('id', flat=True)
        return queryset.filter(id__in=ids_solicitacoes)

    tab_deve_aprovar.short_description = 'Deve aprovar'

    def tab_pode_aprovar(self, request, queryset):
        ids_solicitacoes = SolicitacaoAdesaoPesServidor.get_solicitacoes_pendendentes_avaliacao_chefe(
            request.user, apenas_chefe_direto=False
        ).values_list('id', flat=True)
        return queryset.filter(id__in=ids_solicitacoes)

    tab_pode_aprovar.short_description = 'Pode aprovar'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(situacao=SolicitacaoAdesaoPesServidor.SOLICITADO).exclude(adesao__servidor=request.user.get_relacionamento())
        return qs

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Adesões do Servidor a um PES - A Aprovar'
        return super().changelist_view(request, extra_context=extra_context)


# ====================================================
# Consultas
# ====================================================


class PlanoTrabalhoSetorialConsultaAgrupamentoFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'pts_a'

    def lookups(self, request, model_admin):
        opcoes = []
        opcoes.append(('1', 'Que sou auxiliar do Chefe no Preenchimento do Plano'))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.filter(auxiliares__in=[request.user.get_vinculo()])

        return queryset


@admin.register(PlanoEntregasSetorialConsulta)
class PlanoEntregasSetorialConsultaAdmin(ModelAdminPlus):
    list_display = ('setor', 'get_data_inicio', 'get_data_fim', 'get_situacao', 'get_situacao_avaliacao')
    list_display_icons = True
    list_filter = (PlanoTrabalhoSetorialConsultaAgrupamentoFilter, 'periodo_pes', 'setor', 'situacao', 'situacao_avaliacao')
    ordering = ('-periodo_pes__data_inicio',)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.has_perm('rh.eh_servidor'))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_pes_pgd2', args=[obj_pk]))

    def get_situacao_avaliacao(self, obj):
        return mark_safe(status(obj.get_situacao_avaliacao_display()))

    get_situacao_avaliacao.short_description = 'Situação da avaliação da execução'


class SetorHabilitacaoDocProcessoFilter(admin.SimpleListFilter):
    title = 'Documento ou Processo Informado'
    parameter_name = 'dpi'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(Q(documentos__isnull=False) | Q(processos__isnull=False))
        if self.value() == '2':
            return queryset.filter(documentos__isnull=True, processos__isnull=True)
        return queryset


class RelacaoSetorSiapeSuapFilter(admin.SimpleListFilter):
    title = 'Tem relação SIAPE x SUAP'
    parameter_name = 'trss'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def get_ids_setores_com_relacao_siape_suap(self, queryset):
        api_gd_v2 = ApiPgd2V2()
        ids_setores = []
        for s in queryset:
            relacao_setor_siape_suap = api_gd_v2.get_codigo_siape_setor(s.setor)
            if relacao_setor_siape_suap:
                ids_setores.append(s.setor.id)
        return ids_setores

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(setor_id__in=self.get_ids_setores_com_relacao_siape_suap(queryset))
        if self.value() == '2':
            return queryset.exclude(setor_id__in=self.get_ids_setores_com_relacao_siape_suap(queryset))
        return queryset


class SetorHabilitacaoTemPesPgdFilter(admin.SimpleListFilter):
    # SetorHabilitacaoAdmin
    title = 'Tem PES no PGD'
    parameter_name = 'tpes'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            ids_setores_com_pes = PlanoEntregasSetorial.objects.all().values('setor_id')
            return queryset.filter(setor_id__in=ids_setores_com_pes)
        if self.value() == '2':
            ids_setores_com_pes = PlanoEntregasSetorial.objects.all().values('setor_id')
            return queryset.exclude(setor_id__in=ids_setores_com_pes)
        return queryset


@admin.register(SetorHabilitacao)
class SetorHabilitacaoAdmin(ModelAdminPlus):
    list_display = ('get_setor_suap', 'habilitado', 'tem_relacao_siape_suap', 'tem_pes_no_pgd')
    list_display_icons = True
    form = SetorHabilitacaoForm

    def get_list_filter(self, request):
        if utilizar_integracao_com_pde():
            return (
                'setor',
                'setor__uo',
                'habilitado',
                SetorHabilitacaoDocProcessoFilter,
                RelacaoSetorSiapeSuapFilter,
                SetorHabilitacaoTemPesPgdFilter,
            )
        return ('setor', 'setor__uo', 'habilitado', RelacaoSetorSiapeSuapFilter, SetorHabilitacaoTemPesPgdFilter)

    def get_fieldsets(self, request, obj=None):
        if utilizar_integracao_com_pde():
            fieldsets = (
                ('Dados gerais', {'fields': ('setor', 'habilitado')}),
                ('Outros dados', {'fields': ('documentos', 'processos', 'observacao')}),
            )
        else:
            fieldsets = (
                ('Dados gerais', {'fields': ('setor', 'habilitado')}),
                ('Outros dados', {'fields': ('observacao',)}),
            )
        return fieldsets

    def has_view_permission(self, request, obj=None):
        return ComissaoPGD.user_estah_em_gestao_pgd(request.user) or ComissaoPGD.user_estah_em_comissao_sistemica_vigente(request.user)

    def has_change_permission(self, request, obj=None):
        return ComissaoPGD.user_estah_em_gestao_pgd(request.user) or ComissaoPGD.user_estah_em_comissao_sistemica_vigente(request.user)

    def has_add_permission(self, request):
        return ComissaoPGD.user_estah_em_gestao_pgd(request.user) or ComissaoPGD.user_estah_em_comissao_sistemica_vigente(request.user)

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_habilitacao_setor', args=[obj_pk]))

    @admin.display(description='Setor')
    def get_setor_suap(self, obj):
        if obj:
            out = [
                f"""
            <p><strong>{obj.setor.sigla}</strong> ({obj.setor.nome}) #{obj.setor.id}</p>
            <p>{obj.setor.get_caminho_as_html()}</p>"""
            ]
            return mark_safe(''.join(out))
        return None

    @admin.display(description='Tem relação SIAPE x SUAP', boolean=True)
    def tem_relacao_siape_suap(self, obj):
        if obj:
            api_gd_v2 = ApiPgd2V2()
            if api_gd_v2.get_codigo_siape_setor(obj.setor):
                return True
        return False

    @admin.display(description='Tem PES no PGD', boolean=True)
    def tem_pes_no_pgd(self, obj):
        if obj and obj.setor:
            return PlanoEntregasSetorial.objects.filter(setor=obj.setor).exists()
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('setor')
        return qs


class SetorPgdApiSiglaDiferenteFilter(admin.SimpleListFilter):
    title = 'Setor SIAPE tem sigla diferente do Setor SUAP'
    parameter_name = 'sd'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(setor_suap__isnull=False).exclude(setor_siape__sigla=F('setor_suap__sigla'))
        if self.value() == '2':
            return queryset.filter(setor_suap__isnull=False, setor_siape__sigla=F('setor_suap__sigla'))
        return queryset


class SetorPgdApiSemSetorSuapFilter(admin.SimpleListFilter):
    title = 'Setor SUAP foi informado'
    parameter_name = 'ssi'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(setor_suap__isnull=False)
        if self.value() == '2':
            return queryset.filter(setor_suap__isnull=True)
        return queryset


class SetorPgdApiAgrupamentoFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'agr'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Setores sugeridos para revisão')]
        return opcoes

    def queryset(self, request, queryset):
        # (tem_pes_pgd and eh_reitoria) or (tem_pes_pgd and tem_siglas_diferentes) or (tem_siglas_diferentes) or (eh_reitoria)

        ids_setores_com_pes = PlanoEntregasSetorial.objects.all().values('setor_id')
        tem_pes_pgd = Q(setor_suap__isnull=False) & Q(setor_suap__id__in=ids_setores_com_pes)
        eh_reitoria = Q(setor_suap__isnull=False) & Q(setor_suap__uo__sigla=get_sigla_reitoria())
        tem_siglas_diferentes = Q(setor_suap__isnull=False) & ~Q(setor_siape__sigla=F('setor_suap__sigla'))

        query = (tem_pes_pgd & eh_reitoria) | (tem_pes_pgd & tem_siglas_diferentes) | (tem_siglas_diferentes) | (eh_reitoria)

        if self.value() == '1':
            return queryset.filter(query)

        return queryset


class SetorPgdApiSetorSiapeFilter(admin.SimpleListFilter):
    title = 'Setor SIAPE'
    parameter_name = 'sesi'

    def lookups(self, request, model_admin):
        opcoes = []
        for s in Setor.objects.ativos().siape():
            opcoes.append((s.id, s))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_siape_id=self.value())
        return queryset


class SetorPgdApiCampusSiapeFilter(admin.SimpleListFilter):
    title = 'Campus SIAPE'
    parameter_name = 'csi'

    def lookups(self, request, model_admin):
        opcoes = []
        for uo in UnidadeOrganizacional.objects.siape():
            opcoes.append((uo.id, uo))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_siape__uo_id=self.value())
        return queryset


class SetorPgdApiSetorSuapFilter(admin.SimpleListFilter):
    title = 'Setor SUAP'
    parameter_name = 'sesu'

    def lookups(self, request, model_admin):
        opcoes = []
        for s in Setor.objects.ativos().suap():
            opcoes.append((s.id, s))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_suap_id=self.value())
        return queryset


class SetorPgdApiCampusSuapFilter(admin.SimpleListFilter):
    title = 'Campus SUAP'
    parameter_name = 'csu'

    def lookups(self, request, model_admin):
        opcoes = []
        for uo in UnidadeOrganizacional.objects.suap():
            opcoes.append((uo.id, uo))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(setor_suap__uo_id=self.value())
        return queryset


class SetorPgdApiTemPesPgdFilter(admin.SimpleListFilter):
    # SetorPgdApiAdmin
    title = 'Setor SUAP tem PES no PGD'
    parameter_name = 'tpes'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            ids_setores_com_pes = PlanoEntregasSetorial.objects.all().values('setor_id')
            return queryset.filter(setor_suap__isnull=False, setor_suap_id__in=ids_setores_com_pes)
        if self.value() == '2':
            ids_setores_com_pes = PlanoEntregasSetorial.objects.all().values('setor_id')
            return queryset.filter(setor_suap__isnull=False).exclude(setor_suap_id__in=ids_setores_com_pes)
        return queryset


class SetorPgdApiEstaHabilitadoFilter(admin.SimpleListFilter):
    # SetorPgdApiAdmin
    title = 'Setor SUAP está habilitado no PGD'
    parameter_name = 'sehpgd'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(setor_suap__isnull=False, setor_suap__in=SetorHabilitacao.get_setores_habilitados())
        if self.value() == '2':
            return queryset.filter(setor_suap__isnull=False).exclude(setor_suap__in=SetorHabilitacao.get_setores_habilitados())
        return queryset


@admin.register(SetorPgdApi)
class SetorPgdApiAdmin(ModelAdminPlus):
    list_display = (
        'get_setor_siape_uo',
        'get_setor_siape',
        'get_setor_suap',
        'get_setor_suap_uo',
        'tem_pes_no_pgd',
        'siglas_diferentes',
        'setor_suap_habilitado',
    )
    list_display_icons = True
    list_filter = (
        SetorPgdApiCampusSiapeFilter,
        SetorPgdApiSetorSiapeFilter,
        SetorPgdApiCampusSuapFilter,
        SetorPgdApiSetorSuapFilter,
        SetorPgdApiTemPesPgdFilter,
        SetorPgdApiSiglaDiferenteFilter,
        SetorPgdApiSemSetorSuapFilter,
        SetorPgdApiAgrupamentoFilter,
        SetorPgdApiEstaHabilitadoFilter,
    )
    ordering = ('setor_siape__sigla',)
    change_form_template = 'pgd2/templates/admin/change_form_setor_pgd_api.html'
    change_list_template = 'pgd2/templates/admin/change_list_setor_pgd_api.html'

    def get_action_bar(self, request):
        items = []
        if ComissaoPGD.user_estah_em_gestao_pgd(request.user):
            items.append({'url': 'add/', 'label': 'Adicionar', 'css_class': 'success'})
            items.append({'url': '/pgd2/atualizar_setores_siape/', 'label': 'Atualizar setores', 'css_class': 'success'})
        return items

    def has_view_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return SetorPgdApi.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return SetorPgdApi.pode_cadastrar_alterar(request.user)

    def get_setor_siape(self, obj):
        out = [
            f"""
        <p><strong>{obj.setor_siape.sigla}</strong> ({obj.setor_siape.nome}) #{obj.setor_siape.id} Siape: {obj.setor_siape.codigo} </p>
        <p>{obj.setor_siape.get_caminho_as_html()}</p>"""
        ]

        return mark_safe(''.join(out))

    get_setor_siape.short_description = 'Setor SIAPE'

    def get_setor_siape_uo(self, obj):
        if obj and obj.setor_siape and obj.setor_siape.uo:
            return obj.setor_siape.uo.sigla
        return None

    get_setor_siape_uo.short_description = 'Campus SIAPE'

    def get_setor_suap(self, obj):
        if obj:
            if obj.setor_suap:
                out = [
                    f"""
                <p><strong>{obj.setor_suap.sigla}</strong> ({obj.setor_suap.nome}) #{obj.setor_suap.id}</p>
                <p>{obj.setor_suap.get_caminho_as_html()}</p>"""
                ]
                return mark_safe(''.join(out))
            else:
                return mark_safe("<span class='status status-warning'>Cadastre o setor SUAP correspondente ao SIAPE</span>")
        return None

    get_setor_suap.short_description = 'Setor SUAP'

    def get_setor_suap_uo(self, obj):
        if obj:
            if obj.setor_suap:
                return obj.setor_suap.uo.sigla
            else:
                return mark_safe("<span class='status status-warning'>Cadastre o setor SUAP correspondente ao SIAPE</span>")
        return None

    get_setor_suap_uo.short_description = 'Campus SUAP'

    @admin.display(boolean=True)
    def tem_pes_no_pgd(self, obj):
        if obj and obj.setor_suap:
            return PlanoEntregasSetorial.objects.filter(setor=obj.setor_suap).exists()
        return False

    tem_pes_no_pgd.short_description = 'Setor SUAP tem PES no PGD'

    @admin.display(boolean=True)
    def siglas_diferentes(self, obj):
        if obj and obj.setor_suap:
            return obj.setor_siape.sigla != obj.setor_suap.sigla
        return False

    siglas_diferentes.short_description = 'Setor SIAPE tem sigla diferente do Setor SUAP'

    @admin.display(description='Setor SUAP está habilitado no PGD', boolean=True)
    def setor_suap_habilitado(self, obj):
        if obj and obj.setor_suap:
            return SetorHabilitacao.get_setores_habilitados().filter(id=obj.setor_suap.id).exists()
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['setor_siape'].queryset = Setor.objects.siape().filter(excluido=False).order_by('sigla')
        form.base_fields['setor_suap'].queryset = get_setores_pgd().order_by('sigla')
        return form

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Associar Estruturas SIAPE x SUAP'
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Associar Estruturas SIAPE x SUAP'
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Associação entre Setores SIAPE e SUAP'
        return super().changelist_view(request, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('setor_suap', 'setor_suap__uo', 'setor_siape', 'setor_siape__uo')
        return qs


class PgdExteriorVgenteFilter(admin.SimpleListFilter):
    title = 'Está vigente'
    parameter_name = 'vig'

    def lookups(self, request, model_admin):
        opcoes = [('1', 'Sim'), ('2', 'Não')]
        return opcoes

    def queryset(self, request, queryset):
        lista = []
        if self.value() == '1':
            for o in queryset:
                if o.estah_vigente():
                    lista.append(o.id)
        if self.value() == '2':
            for o in queryset:
                if not o.estah_vigente():
                    lista.append(o.id)
        if lista:
            return queryset.filter(id__in=lista)
        return queryset


@admin.register(PGDExterior)
class PGDExteriorAdmin(ModelAdminPlus):
    list_display = (
        'get_servidor',
        'processo',
        'data_inicio',
        'data_fim',
        'cancelado',
        'hipotese_legal',
        'documento_eletronico',
        'data_hora_criacao',
        'ultima_modificacao',
        'estah_vigente',
    )
    list_filter = (PgdExteriorVgenteFilter, 'servidor')
    list_display_icons = True
    list_display_links = None

    change_list_template = 'pgd2/templates/admin/change_list_pgd_exterior.html'

    form = PGDExteriorForm

    def has_add_permission(self, request):
        return PGDExterior.tem_permissao_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return PGDExterior.tem_permissao_cadastrar_alterar(request.user) or PGDExterior.tem_permissao_informar_portaria(request.user)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.processo:
            if PGDExterior.tem_permissao_informar_portaria(request.user):
                if PGDExterior.tem_permissao_cadastrar_alterar(request.user):
                    return []
                return ['servidor', 'processo', 'data_inicio', 'hipotese_legal']
        return []

    @admin.display(description='Servidor')
    def get_servidor(self, obj):
        if obj:
            url = reverse('servidor_pgd_pgd2', args=[obj.servidor.matricula])
            return mark_safe(f'<a href="{url}">{obj.servidor}</a>')
