import operator
from functools import reduce

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Setor, Vinculo
from comum.utils import get_setor, get_setores_que_sou_chefe_hoje
from djtools.contrib.admin import DateRangeListFilter, ModelAdminPlus, SimpleListModelFilter, get_uo_setor_listfilter
from djtools.templatetags.filters import format_profile, status
from djtools.templatetags.tags import icon
from djtools.utils import get_datetime_now, httprr
from documento_eletronico.models import SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa
from processo_eletronico.forms import EditarModeloDespachoForm, TramiteDistribuicaoForm
from processo_eletronico.models import (
    CompartilhamentoProcessoEletronicoLog,
    CompartilhamentoProcessoEletronicoPoderDeChefe,
    CompartilhamentoProcessoEletronicoSetorPessoa,
    ConfiguracaoProcessoEletronico,
    ConfiguracaoTramiteProcesso,
    DocumentoTextoProcesso,
    GrupoInteressadosProcesso,
    LogCommandProcessoEletronico,
    Processo,
    RegistroAcaoProcesso,
    Requerimento,
    Rotulo,
    SolicitacaoAlteracaoNivelAcesso,
    SolicitacaoDespacho,
    SolicitacaoJuntada,
    TipoProcesso,
    Tramite,
    TramiteDistribuicao,
)
from processo_eletronico.status import SolicitacaoJuntadaStatus
from processo_eletronico.utils import search_fields_para_solicitacao_alteracao_nivel_acesso, setores_que_sou_chefe_ou_tenho_poder_de_chefe
from rh.models import UnidadeOrganizacional
from suap import nomenclatura

from .forms import (
    ConfiguracaoTramiteProcessoForm,
    DocumentoDigitalizadoProcesso,
    DocumentoDigitalizadoProcessoForm,
    DocumentoTextoProcessoForm,
    ModeloDespacho,
    ProcessoEditarForm,
    ProcessoForm,
    RotuloForm,
    TipoProcessoForm,
)
from .status import CienciaStatus, ProcessoStatus


class GrupoInteressadosProcessoAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_filter = ('nome', 'interessados')
    list_display_icons = True
    list_display = ('nome',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(usuario=request.user)


admin.site.register(GrupoInteressadosProcesso, GrupoInteressadosProcessoAdmin)


class TipoProcessoAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_filter = ('nivel_acesso_default', 'consulta_publica')
    list_display_icons = True
    list_display = (
        'nome',
        'permite_nivel_acesso_privado',
        'permite_nivel_acesso_restrito',
        'permite_nivel_acesso_publico',
        'nivel_acesso_default',
        'consulta_publica',
        'permite_gerar_processo_via_requerimento',
        'ativo',
    )
    form = TipoProcessoForm
    fieldsets = TipoProcessoForm.fieldsets
    export_to_xls = True


admin.site.register(TipoProcesso, TipoProcessoAdmin)


class SetorAtualListFilter(SimpleListModelFilter):
    title = 'Setor Atual'
    parameter_name = 'setor_atual'
    parametro_uo = 'uo_atual'

    def lookups(self, request, model_admin):
        exibir_setor_inativo_no_filtro = Configuracao.get_valor_por_chave('processo_eletronico', 'exibir_setor_inativo_no_filtro')
        if exibir_setor_inativo_no_filtro:
            queryset = Setor.objects.suap().all()
        else:
            queryset = Setor.objects.suap_ativos().all()
        if self.parametro_uo in request.GET and request.GET.get(self.parametro_uo):
            queryset = queryset.filter(uo__id__exact=request.GET.get(self.parametro_uo))
        return queryset.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                reduce(operator.and_, [Q(ultimo_tramite__remetente_setor=self.value()), Q(ultimo_tramite__data_hora_recebimento__isnull=True)])
                | Q(ultimo_tramite__destinatario_setor=self.value())
            ).distinct()
        return queryset


class CampusAtualListFilter(SimpleListModelFilter):
    title = f'{nomenclatura.campus} Atual'
    parameter_name = 'uo_atual'

    def lookups(self, request, model_admin):
        lista_uos = []
        queryset = UnidadeOrganizacional.objects.suap().all()
        for uo in queryset:
            lista_uos.append((str(uo.id), uo.sigla))
        return sorted(lista_uos, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                reduce(operator.and_, [Q(ultimo_tramite__remetente_setor__uo=self.value()), Q(ultimo_tramite__data_hora_recebimento__isnull=True)])
                | Q(ultimo_tramite__destinatario_setor__uo=self.value())
            ).distinct()
        return queryset


class SetorTramiteListFilter(SimpleListModelFilter):
    title = 'Setor que Tramitou'
    parameter_name = 'setor_tramite'

    def lookups(self, request, model_admin):
        lista_setores = []
        exibir_setor_inativo_no_filtro = Configuracao.get_valor_por_chave('processo_eletronico', 'exibir_setor_inativo_no_filtro')
        if exibir_setor_inativo_no_filtro:
            queryset = Setor.objects.suap().all()
        else:
            queryset = Setor.objects.suap_ativos().all()
        for setor in queryset:
            lista_setores.append((str(setor.id), setor.sigla))
        return sorted(lista_setores, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Q(tramites__remetente_setor=self.value())).distinct()
        return queryset


class DashboardFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'opcao'

    TODOS = ('0',)
    # Opções do Dashboard
    MEUS_PROCESSOS = '1'
    PROCESSOS_DE_INTERESSE = '2'
    AGUARDANDO_MINHA_CIENCIA = '3'
    # Despachos
    DESPACHOS_PENDENTES = '4'
    # SOLICITAÇÕES
    SOLICITACOES_ACESSO_DOCUMENTOS = '5'
    SOLICITACOES_JUNTADA = '6'
    COM_MINHA_CIENCIA = '7'

    OPCOES = (
        (MEUS_PROCESSOS, 'Meus Processos'),
        (PROCESSOS_DE_INTERESSE, 'Processos de Interesse'),
        (AGUARDANDO_MINHA_CIENCIA, 'Processos Aguardando Minha Ciência'),
        (COM_MINHA_CIENCIA, 'Processos que Registrei Ciência'),
        # Despachos
        (DESPACHOS_PENDENTES, 'Despachos Pendentes'),
        # Solicitações
        (SOLICITACOES_ACESSO_DOCUMENTOS, 'Solicitações de Documentos'),
        (SOLICITACOES_JUNTADA, 'Solicitações de Juntada'),
    )

    def lookups(self, request, model_admin):
        return DashboardFilter.OPCOES

    def queryset(self, request, queryset):
        # Filtra processos_com_solicitação_visualização
        vinculo = request.user.get_vinculo()
        if not vinculo:
            return queryset.none()

        documentos = SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa.objects.filter(
            status_solicitacao=SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa.STATUS_AGUARDANDO, documento__dono_documento=vinculo
        ).values_list('documento', flat=True) | SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa.objects.filter(
            status_solicitacao=SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa.STATUS_AGUARDANDO, solicitante=vinculo
        ).values_list('documento', flat=True)
        ids_docs_solic_acesso = DocumentoDigitalizadoProcesso.objects.filter(documento__in=documentos).values_list('processo', flat=True)

        # Filtra documentos_com_solicitações_de_documentos
        vinculo = request.user.get_vinculo()
        today = get_datetime_now().date()
        ids_docs = SolicitacaoJuntada.objects.filter(
            solicitado=vinculo, data_limite__gte=today, status=SolicitacaoJuntadaStatus.STATUS_ESPERANDO
        ).values_list('tramite__processo', flat=True)

        # Filtra Despachos Pendentes
        ids_despachos = SolicitacaoDespacho.objects.solicitacao_pendente(solicitado=vinculo).values_list('processo', flat=True)

        switcher = {
            DashboardFilter.MEUS_PROCESSOS: lambda: queryset.filter(interessados=request.user.get_vinculo()).order_by('-data_hora_criacao'),
            DashboardFilter.PROCESSOS_DE_INTERESSE: lambda: queryset.filter(acompanhantes_processo=request.user.get_vinculo()).order_by(
                '-data_hora_criacao'
            ),
            DashboardFilter.AGUARDANDO_MINHA_CIENCIA: lambda: queryset.filter(
                solicitacaociencia__solicitado=request.user.get_vinculo(), solicitacaociencia__status=CienciaStatus.STATUS_ESPERANDO
            ),
            # Despachos pendentes
            DashboardFilter.DESPACHOS_PENDENTES: lambda: queryset.filter(id__in=ids_despachos).order_by('-data_hora_criacao'),
            # Solicitações
            DashboardFilter.SOLICITACOES_ACESSO_DOCUMENTOS: lambda: queryset.filter(id__in=ids_docs_solic_acesso).order_by('-data_hora_criacao'),
            DashboardFilter.SOLICITACOES_JUNTADA: lambda: queryset.filter(id__in=ids_docs).order_by('-data_hora_criacao'),
            DashboardFilter.COM_MINHA_CIENCIA: lambda: queryset.filter(
                solicitacaociencia__solicitado=vinculo, solicitacaociencia__data_ciencia__isnull=False
            ),
        }

        if self.value():
            qs = switcher.get(self.value())

            if qs is None:
                return queryset

            return qs()


class ProcessoAdmin(ModelAdminPlus):
    list_filter = (
        DashboardFilter,
        *get_uo_setor_listfilter(parametro_setor='setor_criacao', title_setor='Setor de Criação', title_uo=f'{nomenclatura.campus} de Criação'),
        CampusAtualListFilter,
        SetorAtualListFilter,
        SetorTramiteListFilter,
        'tipo_processo',
        'nivel_acesso',
        'hipotese_legal',
        'status',
        ('data_hora_criacao', DateRangeListFilter),
        ('data_finalizacao', DateRangeListFilter),
        'interessados',
        'usuario_gerador',
    )
    list_display = [
        'get_numero_unico_protocolo',
        'get_tipo_processo',
        'get_assunto',
        'get_interessados',
        'get_setor_criacao',
        'get_data_abertura',
        'get_status',
        'get_setor_atual_com_campus',
        'get_nivel_acesso',
        'get_data_ultima_movimentacao',
        # 'get_opcoes'
    ]
    search_fields = [
        'search_fields_optimized',
    ]
    export_to_xls = True
    list_display_icons = True
    form = ProcessoForm
    change_form = ProcessoEditarForm
    show_tab_any_data = False
    readonly_fields = []
    list_per_page = 30

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        self.model = model
        self._exibir_dados_basicos_listagem = None

    def exibir_dados_basicos_listagem(self):
        if self._exibir_dados_basicos_listagem is None:
            self._exibir_dados_basicos_listagem = Configuracao.get_valor_por_chave('processo_eletronico', 'exibir_dados_basicos_listagem')
        return self._exibir_dados_basicos_listagem

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.get_vinculo().eh_usuario_externo():
            return qs.filter(interessados=request.user.get_vinculo()).order_by('-data_hora_criacao')
        return qs.select_related(
            'setor_atual', 'setor_criacao', 'tipo_processo', 'ultimo_tramite', 'usuario_gerador__vinculo__pessoa__pessoafisica'
        ).prefetch_related(Prefetch('interessados', queryset=Vinculo.objects.select_related('pessoa')))

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = []
        if obj and obj.tem_tramite():
            readonly_fields += ['assunto', 'interessados', 'tipo_processo', 'setor_criacao']
        if obj and obj.pk:
            readonly_fields += ['nivel_acesso', 'hipotese_legal']
        return readonly_fields

    def get_fieldsets(self, request, obj=None):
        fields_dados_processo = ('interessados', 'grupo_interessados', 'tipo_processo', 'assunto', 'setor_criacao', 'classificacao')
        if obj and obj.pk:
            fields_dados_processo = ('interessados', 'tipo_processo', 'assunto', 'setor_criacao', 'classificacao')

        self.fieldsets = (
            (
                'Dados do Processo',
                {'fields': fields_dados_processo},
            ),
            ('Nível de Acesso', {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal')}),
        )

        if obj and obj.pk and not obj.tem_tramite():
            self.fieldsets = (
                (
                    'Dados do Processo',
                    {'fields': ('tipo_processo', 'setor_criacao', 'classificacao')},
                ),
            )

        return self.fieldsets

    def get_numero_unico_protocolo(self, obj):
        numero_protocolo = obj.get_numero_unico_protocolo()
        if obj.status == ProcessoStatus.STATUS_ANEXADO:
            anexador = obj.anexacao_anexadas.first().processo_anexador
            numero_protocolo += f'(Anexado ao processo <a href="{anexador.get_absolute_url()}">{anexador.get_numero_unico_protocolo()}</a>)'
        return mark_safe(numero_protocolo)

    get_numero_unico_protocolo.short_description = 'Número Protocolo'

    def get_tipo_processo(self, obj):
        return obj.tipo_processo if (self.exibir_dados_basicos_listagem() or obj.pode_ver_informacoes_basicas(self.request.user)) else '-'

    get_tipo_processo.short_description = 'Tipo de Processo'
    get_tipo_processo.admin_order_field = 'tipo_processo'

    def get_assunto(self, obj):
        return obj.assunto if (self.exibir_dados_basicos_listagem() or obj.pode_ver_informacoes_basicas(self.request.user)) else '-'

    get_assunto.short_description = 'Assunto'
    get_assunto.admin_order_field = 'assunto'

    def get_setor_criacao(self, obj):
        return obj.setor_criacao if (self.exibir_dados_basicos_listagem() or obj.pode_ver_informacoes_basicas(self.request.user)) else '-'

    get_setor_criacao.short_description = 'Setor de Criação'
    get_setor_criacao.admin_order_field = 'setor_criacao'

    def get_status(self, obj):
        return (
            status(obj.get_status_display()) if (self.exibir_dados_basicos_listagem() or obj.pode_ver_informacoes_basicas(self.request.user)) else '-'
        )

    get_status.short_description = 'Situação'
    get_status.admin_order_field = 'status'

    def get_setor_atual_com_campus(self, obj):
        return (
            obj.setor_atual.sigla
            if obj.setor_atual and (self.exibir_dados_basicos_listagem() or obj.pode_ver_informacoes_basicas(self.request.user))
            else '-'
        )

    get_setor_atual_com_campus.short_description = 'Setor Atual'

    def get_interessados(self, obj):
        # Reusa o cache do prefetch (Vinculo já com select_related('pessoa')): sem query por linha.
        lista_interessados = list(obj.interessados.all())
        count = len(lista_interessados)
        interessados = ['<ul>']
        for interessado in lista_interessados[0:3]:
            interessados.append(f'<li>{format_profile(interessado)}</li>')
        interessados.append('</ul>')
        if count > 3:
            extra = count - 3
            interessados.append(f'<div style="white-space: nowrap">+{extra} interessado(s)</div>')
        pode_exibir_interessados = obj.eh_publico() or (
            obj.pode_ver_informacoes_basicas(self.request.user) and (not obj.eh_restrito() or obj.pode_ler(self.request.user))
        )
        return pode_exibir_interessados and mark_safe(''.join(interessados)) or '-'

    get_interessados.short_description = 'Interessados'

    def get_nivel_acesso(self, obj):
        if obj.pode_ler_consulta_publica():
            url = reverse_lazy('visualizar_processo_publica', kwargs={'processo_id': obj.uuid})
            return mark_safe(f'<a href="{url}">{obj.get_nivel_acesso_display()}</a>')
        else:
            return obj.get_nivel_acesso_display()

    get_nivel_acesso.admin_order_field = 'nivel_acesso'
    get_nivel_acesso.short_description = 'Nível de Acesso'

    def get_data_abertura(self, obj):
        return obj.data_hora_criacao

    get_data_abertura.short_description = 'Data de Abertura'

    def get_data_ultima_movimentacao(self, obj):
        if hasattr(obj, 'ultimo_tramite'):
            tramite = obj.ultimo_tramite
            if tramite:
                ultima_movimentacao = tramite.data_hora_recebimento if tramite.recebido else tramite.data_hora_encaminhamento
                return ultima_movimentacao if obj.pode_ver_informacoes_basicas(self.request.user) else '-'
        return '-'

    get_data_ultima_movimentacao.short_description = 'Última Movimentação'

    def add_view(self, request, form_url='', extra_context=None):
        setor = get_setor(request.user)
        if not setor:
            return httprr('/', 'Você não possui setor associado.', 'error')
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        setor = get_setor(request.user)
        if not setor:
            return httprr('/', 'Você não possui setor associado.', 'error')
        processo = self.get_object(request, object_id)
        if processo and not processo.pode_editar():
            raise PermissionDenied

        extra_context = extra_context or {}
        extra_context['title'] = f'Modificar Processo {processo}'

        return super(ModelAdminPlus, self).change_view(request, object_id, form_url, extra_context)

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.status != ProcessoStatus.STATUS_ANEXADO
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar_dados_basicos(request.user)
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        # Retorna True caso o usuário tenha pelo menos um setor no qual possa criar processo.
        return Tramite.get_todos_setores(request.user, deve_poder_criar_processo=True).exists()

    # Apenas o root pode apagar.
    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
            tipo = RegistroAcaoProcesso.TIPO_CRIACAO
            if change:
                tipo = RegistroAcaoProcesso.TIPO_EDICAO

            RegistroAcaoProcesso.objects.create(processo=obj, tipo=tipo, ip=request.META.get('REMOTE_ADDR', ''), observacao='')
        except Exception as e:
            if settings.DEBUG:
                raise e

    def save_related(self, request, form, formsets, change):
        if form.instance.pk:
            super().save_related(request, form, formsets, change)
            processo = form.instance
            processo.save()

    def response_add(self, request, obj, post_url_continue='/processo_eletronico/processo/{0}/'):
        documento_id = request.GET.get('documento_id', None)
        if documento_id and obj:
            url = reverse_lazy(
                'adicionar_documento_processo', kwargs={'documento_id': documento_id, 'processo_id': obj.id}, current_app='processo_eletronico'
            )
            return HttpResponseRedirect(url)
        else:
            msg = 'Cadastro realizado com sucesso.'

            if obj.id:
                msg = mark_safe(msg + f' <a href="{obj.get_absolute_url()}">Acesse o cadastro</a>.')
            self.message_user(request, msg)

            if obj.id:
                return httprr(post_url_continue.format(obj.id))
            else:
                return httprr('/admin/processo_eletronico/processo/?opcao=1')

    def response_change(self, request, obj):
        return HttpResponseRedirect(f'/processo_eletronico/processo/{obj.pk}/')


admin.site.register(Processo, ProcessoAdmin)


class DocumentoTextoProcessoAdmin(ModelAdminPlus):
    form = DocumentoTextoProcessoForm


admin.site.register(DocumentoTextoProcesso, DocumentoTextoProcessoAdmin)


class DocumentoDigitalizadoProcessoAdmin(ModelAdminPlus):
    form = DocumentoDigitalizadoProcessoForm


admin.site.register(DocumentoDigitalizadoProcesso, DocumentoDigitalizadoProcessoAdmin)


class ModeloDespachoAdmin(ModelAdminPlus):
    list_display = ('get_cabecalho', 'get_rodape')
    list_display_icons = True
    safe_view = True
    form = EditarModeloDespachoForm
    change_form_template = 'documento_eletronico/templates/adminutils/change_form.html'

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_cabecalho(self, obj):
        from django.utils.safestring import mark_safe

        return mark_safe(obj.cabecalho)

    get_cabecalho.short_description = 'Cabeçalho'

    def get_rodape(self, obj):
        from django.utils.safestring import mark_safe

        return mark_safe(obj.rodape)

    get_rodape.short_description = 'Rodapé'


admin.site.register(ModeloDespacho, ModeloDespachoAdmin)


class ConfiguracaoTramiteProcessoAdmin(ModelAdminPlus):
    form = ConfiguracaoTramiteProcessoForm
    list_display = ('tipo_processo', 'uo_origem_interessado', 'setor_destino_primeiro_tramite')
    list_display_icons = True
    ordering = ('tipo_processo', 'uo_origem_interessado', 'setor_destino_primeiro_tramite')


admin.site.register(ConfiguracaoTramiteProcesso, ConfiguracaoTramiteProcessoAdmin)


class RequerimentoAdmin(ModelAdminPlus):
    list_display = ('get_numero_requerimento', 'tipo_processo', 'assunto', 'data_hora_iniciado', 'get_situacao', 'get_processo')
    list_display_icons = True
    list_filter = ('tipo_processo',)
    date_hierarchy = 'data_hora_iniciado'
    search_fields = ['id', 'assunto'] + [f'tipo_processo__{termo}' for termo in TipoProcesso.SEARCH_FIELDS]

    def get_queryset(self, request):
        vinculo = Vinculo.objects.get(user=request.user)
        return super().get_queryset(request).filter(interessado=vinculo)

    def get_action_bar(self, request, remove_add_button=True):
        items = super().get_action_bar(request, remove_add_button)
        items.append({'url': '/processo_eletronico/cadastrar_requerimento/', 'label': 'Adicionar Requerimento', 'css_class': 'success'})
        return items

    def has_change_permission(self, request, obj=None):
        if obj:
            return False
        return super().has_change_permission(request, obj)

    def get_numero_requerimento(self, obj):
        return obj.get_numero_requerimento()

    get_numero_requerimento.admin_order_field = 'id'
    get_numero_requerimento.short_description = 'Identificador'

    def get_situacao(self, obj):
        return obj.get_situacao_as_html()

    get_situacao.short_description = 'Situação'

    def get_processo(self, obj):
        if obj.processo:
            return mark_safe(f'<a href="{obj.processo.get_absolute_url()}">{obj.processo}</a>')
        return '-'

    get_processo.short_description = 'Processo'


admin.site.register(Requerimento, RequerimentoAdmin)


class LogCommandProcessoEletronicoAdmin(ModelAdminPlus):
    list_display = ('id', 'dt_ini_execucao', 'dt_fim_execucao', 'sucesso', 'comando')

    ordering = ['-id']

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False


admin.site.register(LogCommandProcessoEletronico, LogCommandProcessoEletronicoAdmin)


class TramiteDistribuicaoAdmin(ModelAdminPlus):
    list_display = ('setor', 'distribuir_para', 'get_tipos_processos')
    search_fields = ('distribuir_para__pessoa__nome',)
    list_display_icons = True
    form = TramiteDistribuicaoForm

    def show_list_display_icons(self, obj):
        out = []
        if obj.pode_ver(self.request.user):
            out.append(icon('view', obj.get_absolute_url()))

        if obj.pode_excluir(self.request.user):
            out.append(
                icon(
                    'delete',
                    url=f'/processo_eletronico/tramitedistribuicao/excluir_tramitedistribuicao/{obj.id:d}/',
                    confirm=f'Tem certeza que deseja excluir a distribuição dos trâmites para {obj.distribuir_para}?',
                )
            )
        return mark_safe(''.join(out))

    show_list_display_icons.short_description = 'Ações'

    def get_queryset(self, request):
        setores_usuario = get_setores_que_sou_chefe_hoje(request.user)
        ids_funcionarios = []
        for setor in setores_usuario:
            vinculos = setor.get_funcionarios(recursivo=False)
            for vinculo in vinculos:
                if vinculo.ativo:
                    ids_funcionarios.append(vinculo.id)
        #
        qs = super().get_queryset(request)
        return qs.filter(distribuir_para_id__in=ids_funcionarios, distribuir_para__ativo=True)

    def has_add_permission(self, request):
        return True

    def has_delete_permission(self, request, obj=None):
        return True

    def get_tipos_processos(self, obj):
        tipos = "<ul class='tags'>"
        for tipo_processo in obj.tipos_processos_atendidos.all():
            tipos += f'<li>{tipo_processo.nome}</li>'
        tipos += '</ul>'
        return mark_safe(tipos)

    get_tipos_processos.short_description = 'Tipos de Processos Atendidos'


admin.site.register(TramiteDistribuicao, TramiteDistribuicaoAdmin)


class CompartilhamentoProcessoEletronicoSetorPessoaAdmin(ModelAdminPlus):
    list_display = ('setor_dono', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    list_filter = ('setor_dono', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    date_hierarchy = 'data_criacao'
    list_display_icons = True


admin.site.register(CompartilhamentoProcessoEletronicoSetorPessoa, CompartilhamentoProcessoEletronicoSetorPessoaAdmin)


class CompartilhamentoProcessoEletronicoPoderDeChefeAdmin(ModelAdminPlus):
    list_display = ('setor_dono', 'vinculo_permitido', 'data_criacao', 'usuario_criacao')
    list_filter = ('setor_dono', 'vinculo_permitido', 'data_criacao', 'usuario_criacao')
    date_hierarchy = 'data_criacao'
    list_display_icons = True


admin.site.register(CompartilhamentoProcessoEletronicoPoderDeChefe, CompartilhamentoProcessoEletronicoPoderDeChefeAdmin)


class CompartilhamentoProcessoEletronicoLogAdmin(ModelAdminPlus):
    list_display = ('setor_dono', 'setor_permitido', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    list_filter = ('setor_dono', 'setor_permitido', 'vinculo_permitido', 'nivel_permissao', 'data_criacao', 'usuario_criacao')
    date_hierarchy = 'data_criacao'
    list_display_icons = True


admin.site.register(CompartilhamentoProcessoEletronicoLog, CompartilhamentoProcessoEletronicoLogAdmin)


class ConfiguracaoProcessoEletronicoAdmin(ModelAdminPlus):
    list_display = ('get_setores_retorno_programado',)
    list_display_icons = True

    def has_add_permission(self, request):
        return bool(not ConfiguracaoProcessoEletronico.objects.all().exists())

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_setores_retorno_programado(self, obj):
        setores = ['<ul>']
        for setor in obj.setores_que_podem_cadastrar_retorno_programado.all():
            setores.append(f'<li>{setor}</li>')
        setores.append('</ul>')
        return mark_safe(''.join(setores))

    get_setores_retorno_programado.short_description = 'Setores Permitidos para Retorno Programado'


admin.site.register(ConfiguracaoProcessoEletronico, ConfiguracaoProcessoEletronicoAdmin)


class TipoObjSolicitacaoFilter(admin.SimpleListFilter):
    title = 'Tipo'
    parameter_name = 'tipo'

    def lookups(self, request, model_admin):
        opcoes = (('processo', 'Processo'), ('documento_digitalizado', 'Documento Digitalizado'), ('documento_texto', 'Documento Texto'))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'processo':
                return queryset.filter(processo__isnull=False)
            elif self.value() == 'documento_digitalizado':
                return queryset.filter(documento_digitalizado__isnull=False)
            else:
                return queryset.filter(documento_texto__isnull=False)
        return queryset


class AgrupamentoSolicitacaoFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'agrupamento'

    def lookups(self, request, model_admin):
        opcoes = (('minhas', 'Minhas solitações'), ('que_posso_analisar', 'Solicitações que posso analisar'))
        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'minhas':
                return queryset.filter(usuario_solicitante=request.user)
            if self.value() == 'que_posso_analisar':
                return SolicitacaoAlteracaoNivelAcesso.get_solicitacoes_em_aberto_que_posso_analisar(user=request.user, queryset=queryset)

        return queryset


class SolicitacaoAlteracaoNivelAcessoAdmin(ModelAdminPlus):
    # Solicitante (todos os solicitantes com usuario no suap -- Servidor, Aluno)
    # - Lista as solicitações
    # - Exclui a solitacao
    # Gestão de Nível de acesso OU servidor que puder
    # - Lista as solicitações
    # - Analisa as solitações

    list_display = (
        'get_documento_processo',
        'data_hora_solicitacao',
        'usuario_solicitante',
        'descricao',
        'hipotese_legal',
        'get_de_nivel_acesso',
        'get_para_nivel_acesso',
        'usuario_analise',
        'data_analise',
        'get_situacao_display',
        'deferido_pela_solicitacao',
        'get_opcoes',
    )
    list_display_icons = True

    list_filter = (
        AgrupamentoSolicitacaoFilter,
        TipoObjSolicitacaoFilter,
        'situacao',
        'usuario_analise',
    )

    search_fields = (
        search_fields_para_solicitacao_alteracao_nivel_acesso(1)
        + search_fields_para_solicitacao_alteracao_nivel_acesso(2)
        + search_fields_para_solicitacao_alteracao_nivel_acesso(3)
    )

    def get_documento_processo(self, obj):
        texto = f'<a href="{obj.get_documento_processo().get_absolute_url()}">{"Processo" if obj.eh_processo() else "Documento"} - {obj.get_documento_processo()}</a></li>'
        return mark_safe(texto)

    get_documento_processo.short_description = 'Documento/Processo'

    def get_de_nivel_acesso(self, obj):
        if obj.get_de_nivel_acesso() and len(obj.get_de_nivel_acesso()) > 1:
            return obj.get_de_nivel_acesso()[1]
        return obj.get_de_nivel_acesso()[1] or '-'

    get_de_nivel_acesso.short_description = 'De Nível de Acesso'

    def get_para_nivel_acesso(self, obj):
        if obj.get_para_nivel_acesso() and len(obj.get_para_nivel_acesso()) > 1:
            return obj.get_para_nivel_acesso()[1]
        return obj.get_para_nivel_acesso() or '-'

    get_para_nivel_acesso.short_description = 'Para Nível de Acesso'

    def get_situacao_display(self, obj):
        return obj.get_situacao_display()

    get_situacao_display.short_description = 'Situação'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.situacao == SolicitacaoAlteracaoNivelAcesso.SITUACAO_SOLICITADO:
            return obj.usuario_solicitante == request.user
        if request.user.is_superuser:
            return super().has_delete_permission(request, obj)
        return False

    def get_opcoes(self, obj):
        if obj and obj.get_documento_processo().pode_alterar_nivel_acesso(user=self.request.user) and not obj.usuario_analise:
            deferir = reverse_lazy(
                'analisar_solicitacao_alteracao_nivel_acesso', kwargs={'solicitacao_id': obj.id}, current_app='processo_eletronico'
            )
            indeferir = reverse_lazy(
                'indeferir_solicitacao_alteracao_nivel_acesso', kwargs={'solicitacao_id': obj.id}, current_app='processo_eletronico'
            )
            texto = '<ul class="action-bar">'
            texto += f'<li><a href="{deferir}" class="btn success">Deferir</a></li>'
            texto += f'<li><a href="{indeferir}" class="btn danger">Indeferir</a></li>'
            texto += '</ul>'
            return mark_safe(texto)
        return '-'

    get_opcoes.short_description = 'Opções'


admin.site.register(SolicitacaoAlteracaoNivelAcesso, SolicitacaoAlteracaoNivelAcessoAdmin)


class RotuloAdmin(ModelAdminPlus):
    search_fields = ('legenda',)
    list_filter = ('setor', 'ativo')
    list_display_icons = True
    list_display = ('get_legenda', 'descricao', 'setor', 'ativo')
    form = RotuloForm
    fieldsets = RotuloForm.fieldsets

    def get_legenda(self, obj):
        return mark_safe(f'<span class="status status-{obj.cor}">{obj.legenda}</span>')

    get_legenda.short_description = 'Legenda'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            setores = setores_que_sou_chefe_ou_tenho_poder_de_chefe(request.user).values_list('id', flat=True)
            qs = qs.filter(setor_id__in=setores)
        return qs

    def has_view_permission(self, request, obj=None):
        has_permission = request.user.has_perm('rh.eh_chefe')
        has_permission = has_permission and super().has_view_permission(request, obj)
        return has_permission or setores_que_sou_chefe_ou_tenho_poder_de_chefe(request.user).exists()

    def has_change_permission(self, request, obj=None):
        has_permission = request.user.has_perm('rh.eh_chefe')
        has_permission = has_permission and super().has_change_permission(request, obj)
        if obj and obj.setor:
            return has_permission or setores_que_sou_chefe_ou_tenho_poder_de_chefe(request.user).filter(id=obj.setor.id).exists()
        return has_permission

    def has_add_permission(self, request):
        has_permission = request.user.has_perm('rh.eh_chefe')
        has_permission = has_permission and super().has_add_permission(request)
        return has_permission or setores_que_sou_chefe_ou_tenho_poder_de_chefe(request.user).exists()

    def has_delete_permission(self, request, obj=None):
        has_permission = request.user.has_perm('rh.eh_chefe')
        has_permission = has_permission and super().has_delete_permission(request, obj)
        if obj and obj.setor:
            return has_permission or setores_que_sou_chefe_ou_tenho_poder_de_chefe(request.user).filter(id=obj.setor.id).exists()

        return has_permission


admin.site.register(Rotulo, RotuloAdmin)
