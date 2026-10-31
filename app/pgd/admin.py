from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.safestring import mark_safe

from comum.models import Vinculo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus, StackedInlinePlus, TabularInlinePlus
from djtools.templatetags.filters import format_datetime, format_profile, status
from djtools.templatetags.filters.utils import format_hours
from djtools.utils import break_lines_safe, get_client_ip, httprr
from pgd.forms import (
    AtividadeCadastrarForm,
    AtividadeEntregaFormset,
    AtividadeForm,
    ComissaoPGDForm,
    ComplexidadeAtividadeForm,
    ConfiguracaoOrientacaoPitForm,
    ConfiguracaoOrientacaoPlanoSetorialForm,
    ConfiguracaoPerfilServidorForm,
    DocumentoAdesaoPtsServidorForm,
    DocumentoAdesaoServidorForm,
    EditarEntregaEmLoteForm,
    PeriodoPitRitForm,
    PlanoTrabalhoSetorialAddForm,
)
from pgd.models import (
    Atividade,
    AtividadeEntrega,
    AtividadeSolicitacoes,
    ComissaoPGD,
    ComplexidadeAtividade,
    ConfiguracaoOrientacaoPit,
    ConfiguracaoOrientacaoPlanoSetorial,
    ConfiguracaoPerfilServidor,
    DocumentoAdesaoPtsServidor,
    DocumentoAdesaoServidor,
    FaixaComplexidade,
    JustificativaDesligamentoPgd,
    ParticipantesPgd,
    PeriodoPitRit,
    PlanoIndividualTrabalho,
    PlanoTrabalhoSetorial,
    PlanoTrabalhoSetorialSelecionar,
    RegistroAcaoPTS,
    RelatorioIndividualTrabalho,
    RelatorioIndividualTrabalhoAtividadeEntrega,
    RelatorioIndividualTrabalhoAtividadeEntregaAvaliar,
    RelatorioIndividualTrabalhoAtividadeEntregaChefeRegistrar,
    RelatorioIndividualTrabalhoAtividadeEntregaServidorRegistrar,
    RelatorioIndividualTrabalhoAtividadeEntregaTodasAvaliar,
    ServicoAtividade,
    SetorHabilitacao,
    SolicitacaoAdesaoPtsServidor,
    SolicitacaoAdesaoServidor,
    SubtematicaAtividade,
    TematicaAtividade,
)
from pgd.utils import setores_que_sou_chefe_hoje
from rh.models import Funcao, Servidor, Setor, Situacao

# SolicitacaoAdesaoServidor
# SolicitacaoAdesaoPtsServidor


@admin.register(TematicaAtividade)
class TematicaAtividadeAdmin(ModelAdminPlus):
    list_display = ('titulo', 'descricao', 'get_administradores', 'setor', 'ativo')

    list_display_icons = True

    search_fields = ('titulo', 'descricao')
    list_filter = ('ativo',)

    def get_administradores(self, obj):
        strs = []
        for m in obj.administradores.all():
            strs.append(format_profile(m, m.nome))
        return mark_safe(' / '.join(strs))

    get_administradores.short_description = 'Administradores'

    def has_view_permission(self, request, obj=None):
        return TematicaAtividade.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return TematicaAtividade.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return TematicaAtividade.pode_cadastrar_alterar(request.user)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        form.base_fields['administradores'].queryset = Vinculo.objects.filter(user__eh_servidor=True, user__is_active=True)
        return form

    def response_add(self, request, obj, post_url_continue=None):
        if obj:
            TematicaAtividade.sincronizar_permissoes_administradores_tematica()
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if obj:
            TematicaAtividade.sincronizar_permissoes_administradores_tematica()
        return super().response_change(request, obj)


@admin.register(SubtematicaAtividade)
class SubtematicaAtividadeAdmin(ModelAdminPlus):
    list_display = ('tematica', 'titulo', 'descricao', 'ativo')
    list_display_icons = True
    search_fields = ('titulo', 'descricao')
    list_filter = (
        'tematica',
        'ativo',
    )

    def has_view_permission(self, request, obj=None):
        return SubtematicaAtividade.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return SubtematicaAtividade.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return SubtematicaAtividade.pode_cadastrar_alterar(request.user)


@admin.register(ServicoAtividade)
class ServicoAtividadeAdmin(ModelAdminPlus):
    list_display = ('subtematica', 'titulo', 'descricao', 'ativo')
    list_display_icons = True
    search_fields = ('titulo', 'descricao')
    list_filter = (
        'subtematica__tematica',
        'subtematica',
        'ativo',
    )

    def has_view_permission(self, request, obj=None):
        return ServicoAtividade.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return ServicoAtividade.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ServicoAtividade.pode_cadastrar_alterar(request.user)


@admin.register(FaixaComplexidade)
class FaixaComplexidadeAdmin(ModelAdminPlus):
    list_display = ('complexidade', 'ativo')
    list_display_icons = True
    list_filter = ('ativo',)
    search_fields = ('complexidade',)

    def has_view_permission(self, request, obj=None):
        return FaixaComplexidade.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return FaixaComplexidade.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return FaixaComplexidade.pode_cadastrar_alterar(request.user)


@admin.register(ConfiguracaoOrientacaoPlanoSetorial)
class ConfiguracaoOrientacaoPlanoSetorialAdmin(ModelAdminPlus):
    list_display = ('id', 'eh_sistemica', 'get_campus_abragencia', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = (
        'eh_sistemica',
        'cancelado',
    )

    form = ConfiguracaoOrientacaoPlanoSetorialForm

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
        return ConfiguracaoOrientacaoPlanoSetorial.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoOrientacaoPlanoSetorial.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoOrientacaoPlanoSetorial.pode_cadastrar_alterar(request.user)


class ComplexidadeAtividadeInline(TabularInlinePlus):
    model = ComplexidadeAtividade
    readonly_fields = ('faixa_complexidade',)
    fields = ('faixa_complexidade', 'tempo_execucao_presencial', 'tempo_execucao_remoto')
    form = ComplexidadeAtividadeForm

    def get_max_num(self, request, obj=None, **kwargs):
        if obj:
            return obj.faixas_complexidade.count()
        return 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # def has_change_permission(self, request, obj=None):
    #    return ComplexidadeAtividade.pode_cadastrar_alterar(request.user)


class AtividadeEntregaInline(StackedInlinePlus):
    formset = AtividadeEntregaFormset
    model = AtividadeEntrega
    fields = ('atividade', 'titulo', 'ativo')


@admin.register(Atividade)
class AtividadeAdmin(ModelAdminPlus):
    list_display = (
        'hierarquia',
        'titulo',
        'data_inativacao_efeitos_a_partir_de',
        'descricao_entregas',
        'ganho_produtividade',
        'pode_ser_teletrabalho',
        'get_opcoes',
    )
    list_display_icons = True
    search_fields = (
        'titulo',
        'descricao',
    )
    list_filter = (
        'tematica',
        'subtematica',
        'servico',
        'pode_ser_teletrabalho',
        'ativo',
    )
    inlines = [AtividadeEntregaInline, ComplexidadeAtividadeInline]

    add_form = AtividadeCadastrarForm
    change_form = AtividadeForm

    def get_opcoes(self, obj):
        if obj and obj.pode_alterar(self.request.user):
            texto = '<ul class="action-bar">'
            if obj:
                texto += f'<li><a href="/pgd/selecionar_hierarquia_atividade/{obj.id}" class="btn primary">Editar Hierarquia</a></li>'
            texto += '</ul>'
            return mark_safe(texto)
        return None

    get_opcoes.short_description = 'Opções'

    def hierarquia(self, obj):
        return obj.hierarquia()

    hierarquia.short_description = 'Hierarquia'

    def descricao_entregas(self, obj):
        if obj.descricao_entregas:
            return obj.descricao_entregas
        else:
            return mark_safe('<span class="status status-error">É necessário editar esta atividade.</span>')

    descricao_entregas.short_description = 'Descrição das Entregas'

    def get_inlines(self, request, obj=None):
        if obj:
            return [AtividadeEntregaInline, ComplexidadeAtividadeInline]
        return [AtividadeEntregaInline]

    def get_fieldsets(self, request, obj=None):
        fieldsets = ()

        if obj:
            fieldsets = (
                ('Hierarquia', {'fields': ('tematica', 'subtematica', 'servico')}),
                (
                    'Dados gerais',
                    {'fields': ('titulo', 'descricao', 'ganho_produtividade', 'pode_ser_teletrabalho', 'data_inativacao_efeitos_a_partir_de')},
                ),
            )
        else:
            pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)
            if pode_solicitar_cadastro_alteracao:
                fieldsets = (
                    ('Justificativa da Solicitação', {'fields': ('justificativa', 'confirmacao', 'senha')}),
                    ('Hierarquia', {'fields': ('tematica', 'subtematica', 'servico')}),
                    ('Dados gerais', {'fields': ('titulo', 'descricao', 'ganho_produtividade', 'pode_ser_teletrabalho')}),
                )
            else:
                fieldsets = (
                    ('Hierarquia', {'fields': ('tematica', 'subtematica', 'servico')}),
                    ('Dados gerais', {'fields': ('titulo', 'descricao', 'ganho_produtividade', 'pode_ser_teletrabalho')}),
                )

        return fieldsets

    def has_add_permission(self, request):
        pode_cadastrar = Atividade.pode_cadastrar(request.user)
        if pode_cadastrar:
            return True
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)
        return bool(pode_solicitar_cadastro_alteracao)

    def has_change_permission(self, request, obj=None):
        return bool(obj and obj.pode_alterar(request.user))

    # def add_view(self, request, form_url='', extra_context=None):
    #    return HttpResponseRedirect(reverse('selecionar_hierarquia_atividade'))

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': reverse('selecionar_hierarquia_atividade'), 'label': 'Adicionar Atividade', 'css_class': 'success'})
        return items

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}

        # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)
        extra_context['title'] = 'Adicionar Atividade'
        if pode_solicitar_cadastro_alteracao:
            extra_context['title'] = 'Solicitar Cadastro de Nova Atividade'

        return super(ModelAdminPlus, self).add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}

        if object_id:
            a = Atividade.objects.todos().get(id=object_id)

            # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
            pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)
            if pode_solicitar_cadastro_alteracao:
                extra_context['title'] = 'Solicitar Alteração da Atividade {} - {}'.format(a.titulo, 'Ativo' if a.ativo else 'Inativo')
                if a.esta_pendente_envio:
                    extra_context['title'] = f'Esitar Solicitação de Alteração da Atividade: {a.titulo}'
            else:
                extra_context['title'] = 'Editar {} - {}'.format(a.titulo, 'Ativo' if a.ativo else 'Inativo')

            extra_context['pode_solicitar_cadastro_alteracao'] = pode_solicitar_cadastro_alteracao

        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect('/pgd/quadro_atividades/')

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(f'/pgd/visualizar_atividade/{obj_pk}/')

    def response_add(self, request, obj, post_url_continue=None):
        messages.success(request, 'Cadastro realizado com sucesso.')
        return HttpResponseRedirect(f'/pgd/visualizar_atividade/{obj.id}/')

    def response_change(self, request, obj):
        messages.success(request, 'Cadastro realizado com sucesso.')
        return HttpResponseRedirect(f'/pgd/visualizar_atividade/{obj.id}/')

    def render_change_form(self, request, context, *args, **kwargs):
        # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(request.user)

        if pode_solicitar_cadastro_alteracao:
            html_info = '<p class="alert alert-info">A sua solicitação só será efetivada após o envio dos dados.</p>'
            extra = {'info_extra': html_info}
            context.update(extra)

        return super().render_change_form(request, context, *args, **kwargs)

    def get_queryset(self, request):
        return Atividade.objects.todos()


@admin.register(JustificativaDesligamentoPgd)
class JustificativaDesligamentoPgdAdmin(ModelAdminPlus):
    list_display = ('titulo', 'descricao', 'ativo', 'servidor', 'chefe', 'qtd_dias_punicao')

    list_display_icons = True

    search_fields = ('titulo', 'descricao')
    list_filter = ('ativo', 'servidor', 'chefe')

    def has_view_permission(self, request, obj=None):
        return JustificativaDesligamentoPgd.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return JustificativaDesligamentoPgd.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return JustificativaDesligamentoPgd.pode_cadastrar_alterar(request.user)


class SituacaoSolicitacaoAtividadeFilter(admin.SimpleListFilter):
    title = 'Pendente de Análise'
    parameter_name = 'pa'

    def lookups(self, request, model_admin):
        OPCOES = (('1', 'Apenas as pendentes de análise'),)
        return OPCOES

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.filter(situacao_cadastro=Atividade.SOLICITADO)
        return queryset


@admin.register(AtividadeSolicitacoes)
class AtividadeSolicitacoesAdmin(ModelAdminPlus):
    # Tela de analise das solicitacoes de cadastro ou alteração de alguma atividade

    list_display = (
        'hierarquia',
        'titulo',
        'ativo',
        'descricao_entregas',
        'ganho_produtividade',
        'pode_ser_teletrabalho',
        'situacao_cadastro',
        'get_tipo_solicitacao',
    )
    list_display_icons = True
    search_fields = (
        'titulo',
        'descricao',
    )
    list_filter = ('tematica', 'subtematica', 'servico', 'pode_ser_teletrabalho', 'ativo', SituacaoSolicitacaoAtividadeFilter)
    inlines = [AtividadeEntregaInline, ComplexidadeAtividadeInline]

    add_form = AtividadeCadastrarForm
    change_form = AtividadeForm

    def hierarquia(self, obj):
        return obj.hierarquia()

    hierarquia.short_description = 'Hierarquia'

    def get_tipo_solicitacao(self, obj):
        if obj.tipo_solicitacao:
            tipo = obj.tipo_solicitacao
            if obj.original:
                original = f'<p><a href="/pgd/visualizar_atividade/{obj.original.id}">Atividade original</a></p>'
                return mark_safe(f'{tipo}{original}')
            return mark_safe(f'{tipo}')
        return None

    get_tipo_solicitacao.short_description = 'Solicitação de'

    def get_queryset(self, request):
        # Se é da comissão de Gestão ou está em alguma Comissão Sistêmica retorna todos os registros
        if request.user.has_group_cached('Gestor do PGD') or request.user.has_group_cached('Comissão Sistêmica PGD'):
            return AtividadeSolicitacoes.objects.solicitacoes()

        # Se é administrador de alguma tematica visualiz apenas os da tematica que é administrador
        if TematicaAtividade.eh_administrador_de_tematica(request.user):
            tematica_ids = TematicaAtividade.objects.filter(ativo=True, administradores__in=[request.user.get_vinculo()]).values_list('id', flat=True)
            return AtividadeSolicitacoes.objects.solicitacoes().filter(tematica__id__in=tematica_ids)

        return AtividadeSolicitacoes.objects.none()

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(f'/pgd/visualizar_atividade/{obj_pk}/')


@admin.register(SetorHabilitacao)
class SetorHabilitacaoAdmin(ModelAdminPlus):
    list_display = ('setor', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = ('setor', 'cancelado')
    date_hierarchy = 'data_inicio'

    def has_change_permission(self, request, obj=None):
        return SetorHabilitacao.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return SetorHabilitacao.pode_cadastrar_alterar(request.user)


class PlanoTrabalhoSetorialAgrupamentoFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'pts_a'

    def lookups(self, request, model_admin):
        chefe = ('1', 'Relacionado a setores que sou chefe')
        auxiliar = ('2', 'Que sou auxiliar do Chefe no Preenchimento do Plano')

        opcoes = []
        if setores_que_sou_chefe_hoje(request.user.get_relacionamento()).exists():
            opcoes.append(chefe)

        opcoes.append(auxiliar)

        return opcoes

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.filter(setor__in=setores_que_sou_chefe_hoje(request.user.get_relacionamento()))
            if self.value() == '2':
                return queryset.filter(auxiliares__in=[request.user.get_vinculo()])

        return queryset


@admin.register(PlanoTrabalhoSetorial)
class PlanoTrabalhoSetorialAdmin(ModelAdminPlus):
    list_display = ('setor', 'estah_vigente', 'data_inicio', 'data_fim', 'publicado', 'cancelado')
    list_display_icons = True
    list_filter = (PlanoTrabalhoSetorialAgrupamentoFilter, 'setor', 'publicado', 'cancelado')
    add_form = PlanoTrabalhoSetorialAddForm
    date_hierarchy = 'data_inicio'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_plano_trabalho_setorial', args=[obj_pk]))

    def has_view_permission(self, request, obj=None):
        # Retorna a verificação padrão para que ele possa abrir a tela do changelist_view
        # - Apenas no caso de visualizar um obj específico é que ele testa a condição do usuário
        # O has_change_permission será False pq ele não vai editar pela tela padrão
        # - A permission que seria chamamada por este método é utilizada em outras telas
        # O has_add_permission poderá ser False ou True de acordo com a condição do usuário
        if obj:
            return obj.pode_visualizar(request.user)
        return super().has_view_permission(request, obj=None)

    def has_add_permission(self, request):
        return PlanoTrabalhoSetorial.pode_cadastrar(request.user)

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.user = request.user
        super().save_model(request, obj, form, change)

        if obj and obj.id and not change:
            ip = get_client_ip(request)
            RegistroAcaoPTS.objects.create(tipo=RegistroAcaoPTS.TIPO_CRIACAO, pts=obj, ip=ip, observacao='')

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(f'/pgd/visualizar_plano_trabalho_setorial/{obj.id}/')

    def response_change(self, request, obj):
        return HttpResponseRedirect(f'/pgd/visualizar_plano_trabalho_setorial/{obj.id}/')


@admin.register(PlanoTrabalhoSetorialSelecionar)
class PlanoTrabalhoSetorialSelecionarAdmin(ModelAdminPlus):
    list_display = ('setor', '__str__', 'get_opcoes')
    list_display_icons = True
    list_filter = ('setor',)

    def get_opcoes(self, obj):
        texto = '<ul class="action-bar">'
        if obj:
            texto += f'<li><a href="/pgd/solicitar_adesao_pts/{obj.setor.id}" class="btn success">Aderir a este PTS</a></li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_plano_trabalho_setorial', args=[obj_pk]))

    def get_queryset(self, request):
        setor_id = request.GET.get('setor')
        if setor_id:
            setor = Setor.objects.suap_ativos().get(id=setor_id)
            pts = PlanoTrabalhoSetorial.get_pts_vigente_publicado_setor(setor)
            if pts:
                return PlanoTrabalhoSetorial.objects.filter(id=pts.id)
            return PlanoTrabalhoSetorial.objects.none()
        return PlanoTrabalhoSetorial.get_pts_vigentes_publicado()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Selecione um PTS para Solicitar Adesão'

        return super().changelist_view(request, extra_context=extra_context)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(DocumentoAdesaoServidor)
class DocumentoAdesaoServidorAdmin(ModelAdminPlus):
    list_display = ('pk', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = ('cancelado',)
    date_hierarchy = 'data_inicio'

    form = DocumentoAdesaoServidorForm

    def has_view_permission(self, request, obj=None):
        return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return DocumentoAdesaoServidor.pode_cadastrar_alterar(request.user)


@admin.register(DocumentoAdesaoPtsServidor)
class DocumentoAdesaoPtsServidorAdmin(ModelAdminPlus):
    list_display = ('pk', 'estah_vigente', 'data_inicio', 'data_fim', 'cancelado')
    list_display_icons = True
    list_filter = ('cancelado',)
    date_hierarchy = 'data_inicio'

    form = DocumentoAdesaoPtsServidorForm

    def has_view_permission(self, request, obj=None):
        return DocumentoAdesaoPtsServidor.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return DocumentoAdesaoPtsServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return DocumentoAdesaoPtsServidor.pode_cadastrar_alterar(request.user)


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
        return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoPerfilServidor.pode_cadastrar_alterar(request.user)

    def render_change_form(self, request, context, *args, **kwargs):
        html_info = '<p class="alert alert-info">O perfil do Servidor será definido conforme as regras do PGD. Para a correta seleção das situações e funções adequadas ao PGD você pode consultar a Gestão de Pessoas.</p>'
        extra = {'info_extra': html_info}
        context.update(extra)
        return super().render_change_form(request, context, *args, **kwargs)


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

    """
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        form.base_fields['membros'].queryset = PessoaFisica.objects.filter(eh_servidor=True, vinculo__user__is_active=True)
        return form
    """


@admin.register(SolicitacaoAdesaoServidor)
class SolicitacaoAdesaoServidorAdmin(ModelAdminPlus):
    list_display_icons = True
    show_tab_any_data = False

    """
    SOLICITADO = 1
    CANCELADO_PELO_SERVIDOR = 2
    CANCELADO_PELO_AVALIADOR = 3
    DEFERIDO = 4
    INDEFERIDO = 5
    # Adicionar status DESLIGADO
    SITUACAO_SOLICITACAO_ADESAO_CHOICES = [[SOLICITADO, 'Solicitado e Aguardando Análise'],
                                           [CANCELADO_PELO_SERVIDOR, 'Cancelado pelo Servidor'],
                                           [CANCELADO_PELO_AVALIADOR, 'Cancelado pelo Avaliador'],
                                           [DEFERIDO, 'Deferido'],
                                           [INDEFERIDO, 'Indeferido']]

    """

    def get_tabs(self, request):
        return ['tab_minhas', 'tab_solicitado', 'tab_cancelado_servidor', 'tab_cancelado_avaliador', 'tab_deferido', 'tab_indeferido']

    def tab_minhas(self, request, queryset):
        return queryset.filter(servidor__vinculos__user=request.user)

    tab_minhas.short_description = 'Minhas'

    def tab_solicitado(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.SOLICITADO).exclude(servidor__vinculos__user=request.user)

    tab_solicitado.short_description = 'Solicitado e Aguardando Análise'

    def tab_cancelado_servidor(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR).exclude(servidor__vinculos__user=request.user)

    tab_cancelado_servidor.short_description = 'Cancelado pelo Servidor'

    def tab_cancelado_avaliador(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR).exclude(servidor__vinculos__user=request.user)

    tab_cancelado_avaliador.short_description = 'Cancelado pelo Avaliador'

    def tab_deferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO).exclude(servidor__vinculos__user=request.user)

    tab_deferido.short_description = 'Deferido'

    def tab_indeferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.INDEFERIDO).exclude(servidor__vinculos__user=request.user)

    tab_indeferido.short_description = 'Indeferido'

    def changelist_view(self, request, extra_context=None):
        self.list_display = ('servidor', 'get_setor', 'get_situacao')
        self.list_filter = ()
        self.search_fields = ()

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        if estah_em_gestao_pgd or estah_em_comissao_vigente or eh_chefe_de_setor_hoje:
            self.list_filter = (CustomTabListFilter, 'situacao', 'servidor__setor')
            self.search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')

        return super().changelist_view(request, extra_context=extra_context)

    def get_setor(self, obj):
        return obj.servidor.setor

    get_setor.short_description = 'Setor'

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def has_change_permission(self, request, obj=None):
        return False

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': reverse('solicitar_adesao'), 'label': 'Solicitar Adesão ao PGD', 'css_class': 'success'})
        return items

    def add_view(self, request):
        return HttpResponseRedirect(reverse('solicitar_adesao'))

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_solicitacao_adesao', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        # Se é Gestão ou está em alguma Comissão Sistêmica
        if estah_em_gestao_pgd or estah_em_comissao_vigente:
            return qs

        # As que pode avaliar e as que ele mesmo solicitou
        if eh_chefe_de_setor_hoje:
            setores_ids = eh_chefe_de_setor_hoje.values_list('id', flat=True)
            return qs.filter(Q(servidor__setor__in=setores_ids) | Q(servidor__vinculos__user=request.user))

        if estah_em_comissao_local_vigente:
            campis = ComissaoPGD.get_campis_comissoes_locais_vigentes_user(request.user.get_vinculo())
            return qs.filter(Q(servidor__setor__uo__in=campis) | Q(servidor__vinculos__user=request.user))

        # Se APENAS é quem solicitou
        return qs.filter(servidor__vinculos__user=request.user)


class CategoriaListFilter(admin.SimpleListFilter):
    title = 'Categoria'
    parameter_name = 'categoria'
    DOCENTE = 'docente'
    TECNICO = 'tecnico_administrativo'
    ESTAGIARIO = 'estagiario'

    def lookups(self, request, model_admin):
        return [[self.DOCENTE, 'Docente'], [self.TECNICO, 'Técnico Administrativo'], [self.ESTAGIARIO, 'Estagiário']]

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == self.DOCENTE:
                return queryset.filter(servidor__eh_docente=True)
            elif self.value() == self.TECNICO:
                return queryset.filter(servidor__eh_tecnico_administrativo=True)
            elif self.value() == self.ESTAGIARIO:
                return queryset.filter(servidor__situacao__codigo__in=Situacao.situacoes_siape_estagiarios())
        return queryset


@admin.register(ParticipantesPgd)
class ParticipantesPgdAdmin(ModelAdminPlus):
    # nome, campus, setor, TELEFONE INFORMADO pelo servidor no momento da adesão
    list_display = (
        'servidor',
        'get_info_funcional',
        'get_contato_ultima_adesao_deferida',
        'get_preferencia_contato_ultima_adesao_deferida',
        'get_vigencia_adesao',
    )

    list_filter = ('servidor__setor__uo', 'servidor__setor', 'servidor__ativo', CategoriaListFilter, 'servidor__cargo_emprego_area')

    list_display_icons = True

    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')

    actions = ['enviar_email']

    def get_vigencia_adesao(self, obj):
        return bool(obj.estah_vigente)

    get_vigencia_adesao.short_description = 'Vigência'
    get_vigencia_adesao.boolean = True

    def enviar_email(self, request, queryset):
        parametros = []
        parametros.append('action=enviar_email_participantes_pgd_selecionados')
        parametros.append('checks=' + '&checks='.join(request.POST.getlist('_selected_action')))
        parametros = mark_safe('&'.join(parametros))
        return HttpResponseRedirect(f'/pgd/enviar_email_pgd/?{parametros}')

    enviar_email.short_description = 'Enviar E-mail'

    def get_situacao_ultima_adesao(self, obj):
        ultima_adesao = obj.get_ultima_adesao()
        if ultima_adesao:
            return mark_safe(status(ultima_adesao.get_situacao_display()))
        else:
            return '-'

    get_situacao_ultima_adesao.short_description = 'Situação da Última Adesão'

    def get_contato_ultima_adesao_deferida(self, obj):
        ultima_adesao_deferida = obj.get_ultima_adesao_deferida()
        if ultima_adesao_deferida:
            return ultima_adesao_deferida.telefone
        else:
            return '-'

    get_contato_ultima_adesao_deferida.short_description = 'Contato PGD'

    def get_preferencia_contato_ultima_adesao_deferida(self, obj):
        ultima_adesao_deferida = obj.get_ultima_adesao_deferida()
        if ultima_adesao_deferida:
            if ultima_adesao_deferida.link_whats:
                preferencia = ultima_adesao_deferida.link_whats
            elif ultima_adesao_deferida.preferencia_contato == SolicitacaoAdesaoServidor.PREFERENCIA_CONTATO_EMAIL:
                preferencia = f'<a href="mailto:{obj.servidor.email_institucional}" class="btn"><span class="fa fa-envelope" aria-hidden="true"></span> E-mail institucional</a>'
            else:
                preferencia = ultima_adesao_deferida.get_preferencia_contato_display()
            return mark_safe(preferencia)
        else:
            return '-'

    get_preferencia_contato_ultima_adesao_deferida.short_description = 'Preferência de Contato'

    def get_info_funcional(self, obj):
        out = ['<dl>']
        if obj.servidor.setor_lotacao:
            out.append(f'<dt>SIAPE Lotação:</dt><dd>{obj.servidor.setor_lotacao.sigla}</dd>')
        if obj.servidor.setor_exercicio:
            out.append(f'<dt>SIAPE Exercício:</dt><dd>{obj.servidor.setor_exercicio.sigla}</dd>')
        if obj.servidor.setor:
            out.append(f'<dt>SUAP:</dt><dd>{obj.servidor.setor.sigla}</dd>')
        out.append('</dl>')
        return mark_safe(''.join(out))

    get_info_funcional.short_description = 'Setor'

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        servidores_vinculados = Servidor.objects.vinculados()
        qs = qs.filter(servidor__in=servidores_vinculados)

        adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes()
        qs = qs.filter(id__in=adesoes_vigentes)

        return qs


@admin.register(SolicitacaoAdesaoPtsServidor)
class SolicitacaoAdesaoPtsServidorAdmin(ModelAdminPlus):
    list_display_icons = True
    show_tab_any_data = False

    """
    SOLICITADO = 1
    CANCELADO_PELO_SERVIDOR = 2
    CANCELADO_PELO_AVALIADOR = 3
    DEFERIDO = 4
    INDEFERIDO = 5
    SITUACAO_SOLICITACAO_ADESAO_CHOICES = [[SOLICITADO, 'Solicitado e Aguardando Análise'],
                                           [CANCELADO_PELO_SERVIDOR, 'Cancelado pelo Servidor'],
                                           [CANCELADO_PELO_AVALIADOR, 'Cancelado pelo Avaliador'],
                                           [DEFERIDO, 'Deferido'],
                                           [INDEFERIDO, 'Indeferido']]
    """

    def get_tabs(self, request):
        return ['tab_minhas', 'tab_solicitado', 'tab_cancelado_servidor', 'tab_cancelado_avaliador', 'tab_deferido', 'tab_indeferido']

    def tab_minhas(self, request, queryset):
        return queryset.filter(adesao__servidor__vinculos__user=request.user)

    tab_minhas.short_description = 'Minhas'

    def tab_solicitado(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoPtsServidor.SOLICITADO).exclude(adesao__servidor__vinculos__user=request.user)

    tab_solicitado.short_description = 'Solicitado e Aguardando Análise'

    def tab_cancelado_servidor(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_SERVIDOR).exclude(adesao__servidor__vinculos__user=request.user)

    tab_cancelado_servidor.short_description = 'Cancelado pelo Servidor'

    def tab_cancelado_avaliador(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_AVALIADOR).exclude(adesao__servidor__vinculos__user=request.user)

    tab_cancelado_avaliador.short_description = 'Cancelado pelo Avaliador'

    def tab_deferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoPtsServidor.DEFERIDO).exclude(adesao__servidor__vinculos__user=request.user)

    tab_deferido.short_description = 'Deferido'

    def tab_indeferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoPtsServidor.INDEFERIDO).exclude(adesao__servidor__vinculos__user=request.user)

    tab_indeferido.short_description = 'Indeferido'

    def changelist_view(self, request, extra_context=None):
        self.list_display = ('get_servidor', 'get_setor', 'plano_trabalho_setorial', 'get_situacao')
        self.list_filter = ()
        self.search_fields = ()

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        if estah_em_gestao_pgd or estah_em_comissao_vigente or eh_chefe_de_setor_hoje:
            self.list_filter = (CustomTabListFilter, 'situacao', 'plano_trabalho_setorial__setor')
            self.search_fields = ('adesao__servidor__pessoa_fisica__nome', 'adesao__servidor__matricula')

        return super().changelist_view(request, extra_context=extra_context)

    def get_servidor(self, obj):
        return obj.adesao.servidor

    get_servidor.short_description = 'Servidor'

    def get_setor(self, obj):
        return obj.plano_trabalho_setorial.setor

    get_setor.short_description = 'Setor'

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def has_change_permission(self, request, obj=None):
        return False

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': '/admin/pgd/planotrabalhosetorialselecionar/', 'label': 'Solicitar Adesão ao PTS', 'css_class': 'success'})
        return items

    def add_view(self, request):
        return HttpResponseRedirect('/admin/pgd/planotrabalhosetorialselecionar/')

    # def has_add_permission(self, request):
    #    return False

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_solicitacao_adesao_pts', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = request.user.has_group_cached('Comissão Local PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        # Se é Gestão ou está em alguma Comissão Sistêmica
        if estah_em_gestao_pgd or estah_em_comissao_vigente:
            return qs

        # As que pode avaliar e as que ele mesmo solicitou
        if eh_chefe_de_setor_hoje:
            setores_ids = eh_chefe_de_setor_hoje.values_list('id', flat=True)
            return qs.filter(Q(plano_trabalho_setorial__setor__in=setores_ids) | Q(adesao__servidor__vinculos__user=request.user))

        if estah_em_comissao_local_vigente:
            campis = ComissaoPGD.get_campis_comissoes_locais_vigentes_user(request.user.get_vinculo())
            return qs.filter(Q(plano_trabalho_setorial__setor__uo__in=campis) | Q(adesao__servidor__vinculos__user=request.user))

        # Se APENAS é quem solicitou
        return qs.filter(adesao__servidor__vinculos__user=request.user)


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
        return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return ConfiguracaoOrientacaoPit.pode_cadastrar_alterar(request.user)


@admin.register(PeriodoPitRit)
class PeriodoPitAdmin(ModelAdminPlus):
    list_display = ('titulo', 'data_inicio', 'data_fim', 'cancelado', 'get_opcoes')

    list_display_icons = True

    list_filter = ('cancelado',)

    form = PeriodoPitRitForm

    """
    fieldsets = (
        ('Dados gerais', {'fields': ('titulo', 'ano', 'cancelado')}),
        ('Datas do PIT', {'fields': ('data_inicio', 'data_fim')}),
        ('Datas do RIT 1', {'fields': ('rit_data_inicio_1', 'rit_data_fim_1')}),
        ('Datas do RIT 2', {'fields': ('rit_data_inicio_2', 'rit_data_fim_2')}),
        ('Datas do RIT 3', {'fields': ('rit_data_inicio_3', 'rit_data_fim_3')}),
        ('Datas do RIT 4', {'fields': ('rit_data_inicio_4', 'rit_data_fim_4')}),
        ('Datas do RIT 5', {'fields': ('rit_data_inicio_5', 'rit_data_fim_5')}),
        ('Datas do RIT 6', {'fields': ('rit_data_inicio_6', 'rit_data_fim_6')}),
    )
    """
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'titulo',
                    'ano',
                    'cancelado',
                )
            },
        ),
        ('Datas do PIT', {'fields': ('data_inicio', 'data_fim')}),
        ('Datas do RIT', {'fields': ('rit_data_inicio_1', 'rit_data_fim_1')}),
    )

    def has_view_permission(self, request, obj=None):
        return PeriodoPitRit.pode_cadastrar_alterar(request.user)

    def has_change_permission(self, request, obj=None):
        return PeriodoPitRit.pode_cadastrar_alterar(request.user)

    def has_add_permission(self, request):
        return PeriodoPitRit.pode_cadastrar_alterar(request.user)

    def get_opcoes(self, obj):
        texto = '-'
        if self.request.user.has_perm('pgd.change_periodopitrit'):
            texto = '<ul class="action-bar">'
            if obj.preencher_questionario_pesquisa:
                texto += f'<li><a href="/pgd/ativar_desativar_preencher_questionario_pesquisa/{obj.id}/" class="btn danger">Desativar</a></li>'
            else:
                texto += f'<li><a href="/pgd/ativar_desativar_preencher_questionario_pesquisa/{obj.id}/" class="btn success">Ativar</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Solicitar preenchimento do questionário de pesquisa'


@admin.register(PlanoIndividualTrabalho)
class PlanoIndividualTrabalhoAdmin(ModelAdminPlus):
    list_display = ('adesao', 'get_adesao_servidor', 'get_adesao_servidor_setor', 'periodo_pit_rit', 'get_situacao', 'homologado_definitivo')
    list_filter = (CustomTabListFilter, 'adesao__servidor__setor')
    search_fields = ('adesao__servidor__pessoa_fisica__nome', 'adesao__servidor__matricula')
    list_display_icons = True

    # CADASTRADO = 1
    # AGUARDANDO_PARECER = 2
    # CANCELADO_PELO_SERVIDOR = 3
    # CANCELADO_PELO_AVALIADOR = 4
    # AUTORIZADO = 5

    def get_tabs(self, request):
        return ['tab_cadastrados', 'tab_aguardando_parecer', 'tab_cancelado', 'tab_autorizado']

    def get_adesao_servidor(self, obj):
        return str(obj.adesao.servidor)

    get_adesao_servidor.short_description = 'Servidor'

    def get_adesao_servidor_setor(self, obj):
        return str(obj.adesao.servidor.setor)

    get_adesao_servidor_setor.short_description = 'Servidor'

    def tab_cadastrados(self, request, queryset):
        return queryset.filter(situacao=PlanoIndividualTrabalho.CADASTRADO)

    tab_cadastrados.short_description = 'Cadastrados'

    def tab_aguardando_parecer(self, request, queryset):
        return queryset.filter(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)

    tab_aguardando_parecer.short_description = 'Aguardando Aprovação/Homologação'

    def tab_cancelado(self, request, queryset):
        return queryset.filter(
            Q(situacao=PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR) | Q(situacao=PlanoIndividualTrabalho.CANCELADO_PELO_AVALIADOR)
        )

    tab_cancelado.short_description = 'Cancelado'

    def tab_autorizado(self, request, queryset):
        return queryset.filter(situacao=PlanoIndividualTrabalho.AUTORIZADO)

    tab_autorizado.short_description = 'Autorizado'

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))

    get_situacao.short_description = 'Situação'

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_chefe_plano_individual_trabalho', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request).order_by('adesao__servidor__pessoa_fisica__nome')
        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD', ignore_groups_if_superuser=False)
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD', ignore_groups_if_superuser=False)

        # Ver todos
        # --------------------------------
        if estah_em_gestao_pgd and estah_em_comissao_vigente:
            return qs

        # Ver os que pode aprovar
        # --------------------------------
        return PlanoIndividualTrabalho.get_pits_chefe_setor(request.user)


class FiltroEditarLoteFilter(admin.SimpleListFilter):
    title = ''
    parameter_name = 'editar_em_lote'

    def lookups(self, request, model_admin):
        return []

    def queryset(self, request, queryset):
        if self.value():
            return queryset


"""
class AtividadeTipoEntregaFilter(admin.SimpleListFilter):
    title = "Atvidade"
    parameter_name = "atividade"

    def lookups(self, request, model_admin):
        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))
        atividades_pode_receber_entregas = rit.get_atividades_pode_receber_entregas()
        atividades_com_entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=rit).distinct('rit_atividade')
        if atividades_com_entregas:
            atividades_pode_receber_entregas = atividades_pode_receber_entregas.filter(id__in=atividades_com_entregas.values_list('rit_atividade', flat=True))
        return [(a.id, a.atividade_pts.atividade.hierarquia_atividade()) for a in atividades_pode_receber_entregas]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(rit_atividade__id=self.value())
        return queryset
"""


"""
class EntregaPtsFilter(admin.SimpleListFilter):
    # Filtra as entregas de um RelatorioIndividualTrabalhoAtividadeEntrega por PTS

    title = "PTS"
    parameter_name = "pts"

    def lookups(self, request, model_admin):
        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))
        entregas = rit.get_entregas()
        ptss_entregas = entregas.values_list('rit_atividade__atividade_pts__plano_trabalho_setorial__id', flat=True).distinct()
        return [(a.id, a) for a in PlanoTrabalhoSetorial.objects.filter(id__in=ptss_entregas)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(rit_atividade__atividade_pts__plano_trabalho_setorial__id=self.value())
        return queryset
"""


"""
@admin.register(SolicitacaoAdesaoServidor)
class SolicitacaoAdesaoServidorAdmin(ModelAdminPlus):
    list_display_icons = True
    show_tab_any_data = False

    def get_tabs(self, request):
        return ['tab_minhas', 'tab_solicitado', 'tab_cancelado_servidor', 'tab_cancelado_avaliador', 'tab_deferido', 'tab_indeferido']

    def tab_minhas(self, request, queryset):
        return queryset.filter(servidor__vinculos__user=request.user)
    tab_minhas.short_description = 'Minhas'

    def tab_solicitado(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.SOLICITADO).exclude(servidor__vinculos__user=request.user)
    tab_solicitado.short_description = 'Solicitado e Aguardando Análise'

    def tab_cancelado_servidor(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR).exclude(servidor__vinculos__user=request.user)
    tab_cancelado_servidor.short_description = 'Cancelado pelo Servidor'

    def tab_cancelado_avaliador(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR).exclude(servidor__vinculos__user=request.user)
    tab_cancelado_avaliador.short_description = 'Cancelado pelo Avaliador'

    def tab_deferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO).exclude(servidor__vinculos__user=request.user)
    tab_deferido.short_description = 'Deferido'

    def tab_indeferido(self, request, queryset):
        return queryset.filter(situacao=SolicitacaoAdesaoServidor.INDEFERIDO).exclude(servidor__vinculos__user=request.user)
    tab_indeferido.short_description = 'Indeferido'

    def changelist_view(self, request, extra_context=None):
        self.list_display = ('servidor', 'get_situacao')
        self.list_filter = ()
        self.search_fields = ()

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        if estah_em_gestao_pgd or estah_em_comissao_vigente or eh_chefe_de_setor_hoje:
            self.list_filter = (CustomTabListFilter, 'situacao',)
            self.search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')

        return super().changelist_view(request, extra_context=extra_context)

    def get_situacao(self, obj):
        return mark_safe(status(obj.get_situacao_display()))
    get_situacao.short_description = 'Situação'

    def has_change_permission(self, request, obj=None):
        return False

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append(dict(url=reverse('solicitar_adesao'), label='Solicitar Adesão ao PGD', css_class='success'))
        return items

    def add_view(self, request):
        return HttpResponseRedirect(reverse('solicitar_adesao'))

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_solicitacao_adesao', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        eh_chefe_de_setor_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        # Se é Gestão ou está em alguma Comissão Sistêmica
        if estah_em_gestao_pgd or estah_em_comissao_vigente:
            return qs

        # As que pode avaliar e as que ele mesmo solicitou
        if eh_chefe_de_setor_hoje:
            setores_ids = eh_chefe_de_setor_hoje.values_list('id', flat=True)
            return qs.filter(Q(servidor__setor__in=setores_ids) | Q(servidor__vinculos__user=request.user))

        # Se APENAS é quem solicitou
        return qs.filter(servidor__vinculos__user=request.user)

"""

# ------------------------------------------------------------
# RIT
# ------------------------------------------------------------

# Servidor - Visualizar, Editar, Adicionar Entregas ao RIT
# ------------------------------------------------------------


@admin.register(RelatorioIndividualTrabalhoAtividadeEntregaServidorRegistrar)
class RelatorioIndividualTrabalhoAtividadeEntregaServidorRegistrarAdmin(ModelAdminPlus):
    perfil = 'servidor'

    list_filter = (
        'rit_atividade__rit',
        FiltroEditarLoteFilter,
        'rit_atividade__atividade_pts__plano_trabalho_setorial',
        'rit_atividade',
        'situacao',
        'prioridade',
        'tipo_entrega',
        'executada_em_teletrabalho',
    )
    hidden_filters = ['rit_atividade__rit', 'editar_em_lote']
    filters_ajax = False

    change_list_template = 'pgd/templates/rit_entrega_registrar.html'

    date_hierarchy = 'data_iniciou'

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return True

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_entrega_rit', args=[obj_pk]))

    def has_change_permission(self, request, obj=None):
        if obj:
            return obj.pode_editar(request.user)
        if request.GET.get('editar_em_lote'):
            return request.user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        try:
            return HttpResponseRedirect(reverse('alterar_entrega_rit', args=[object_id]) + f'?p={self.perfil}')
        except Exception:
            return httprr('/pgd/servidor_pgd/', 'RIT não encontrado', 'error')

    def entregar_entrega(self, request, queryset):
        ids = [str(id) for id in list(queryset.exclude(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE).values_list('id', flat=True))]
        parametros = []
        parametros.append('rit_id={}'.format(request.GET.get('rit_atividade__rit')))
        parametros.append('action={}'.format(request.POST.getlist('action')[0]))
        parametros.append('checks=' + '&checks='.join(ids))
        parametros.append(f'p={self.perfil}')
        parametros = mark_safe('&'.join(parametros))
        return HttpResponseRedirect(f'/pgd/servidor_chefe_operacoes_entrega_rit/?{parametros}')

    entregar_entrega.short_description = 'Entregar'

    def reverter_entrega_entregue(self, request, queryset):
        ids = [str(id) for id in list(queryset.filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE).values_list('id', flat=True))]
        parametros = []
        parametros.append('rit_id={}'.format(request.GET.get('rit_atividade__rit')))
        parametros.append('action={}'.format(request.POST.getlist('action')[0]))
        parametros.append('checks=' + '&checks='.join(ids))
        parametros.append(f'p={self.perfil}')
        parametros = mark_safe('&'.join(parametros))
        return HttpResponseRedirect(f'/pgd/servidor_chefe_operacoes_entrega_rit/?{parametros}')

    reverter_entrega_entregue.short_description = 'Reverter Entrega'

    def remover_entrega(self, request, queryset):
        ids = [str(id) for id in list(queryset.exclude(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE).values_list('id', flat=True))]
        parametros = []
        parametros.append('rit_id={}'.format(request.GET.get('rit_atividade__rit')))
        parametros.append('action={}'.format(request.POST.getlist('action')[0]))
        parametros.append('checks=' + '&checks='.join(ids))
        parametros.append(f'p={self.perfil}')
        parametros = mark_safe('&'.join(parametros))
        return HttpResponseRedirect(f'/pgd/servidor_chefe_operacoes_entrega_rit/?{parametros}')

    remover_entrega.short_description = 'Remover Entrega'

    def get_actions(self, request):
        actions = super().get_actions(request)

        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))

        pode_entregar_entrega = rit.pode_entregar_entrega(request.user)
        pode_receber_entregas = rit.pode_receber_entregas(request.user)

        pode_remover_entrega = rit.pode_receber_entregas(request.user) and rit.pit.adesao.servidor == request.user.get_relacionamento()

        if not pode_entregar_entrega and 'entregar_entrega' in actions:
            del actions['entregar_entrega']

        if not pode_receber_entregas and 'reverter_entrega_entregue' in actions:
            del actions['reverter_entrega_entregue']

        if not pode_remover_entrega and 'remover_entrega' in actions:
            del actions['remover_entrega']

        return actions

    def get_changelist_form(self, request, **kwargs):
        return EditarEntregaEmLoteForm

    def get_opcoes(self, obj):
        texto = '-'
        if obj.pode_remover(self.request.user):
            texto = '<ul class="action-bar">'
            texto += f'<li><a href="/pgd/remover_entrega_rit/{obj.id}/?p={self.perfil}" class="btn danger">Remover</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def get_descricao(self, obj):
        return break_lines_safe(obj.descricao)

    get_descricao.short_description = 'Descrição'
    get_descricao.admin_order_field = 'descricao'

    def get_botao_alternar_edicao(self, request):
        parametros = request.META.get('QUERY_STRING', None)
        parametros = parametros.replace('&editar_em_lote=1', '')
        parametros = parametros.replace('editar_em_lote=1', '')
        parametros_botao_editar_em_lote = None
        parametros_botao_sair_editar_em_lote = None
        if parametros:
            parametros_botao_editar_em_lote = parametros + '&editar_em_lote=1'
            parametros_botao_sair_editar_em_lote = parametros
        return parametros_botao_editar_em_lote, parametros_botao_sair_editar_em_lote

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        if not request.GET.get('rit_atividade__rit'):
            raise PermissionDenied

        try:
            int(request.GET.get('rit_atividade__rit'))
        except Exception:
            raise PermissionDenied

        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))

        if not rit.pode_visualizar(request.user):
            raise PermissionDenied

        extra_context['perfil'] = self.perfil
        extra_context['rit'] = rit
        extra_context['pit'] = rit.pit
        extra_context['servidor'] = rit.pit.adesao.servidor

        ptss_relacionados = rit.pit.get_pts_relacionados()
        if ptss_relacionados:
            for pts_relacionados in ptss_relacionados:
                pts_relacionados.sincrononiza_inativacao_atividades()

        extra_context['url'] = '/admin/pgd/relatorioindividualtrabalhoatividadeentregaservidorregistrar/'
        if self.perfil == 'chefe':
            extra_context['url'] = '/admin/pgd/relatorioindividualtrabalhoatividadeentregacheferegistrar/'

        extra_context['url_voltar'] = f'/pgd/visualizar_plano_individual_trabalho/{rit.pit.id}/'
        if self.perfil == 'chefe':
            extra_context['url_voltar'] = '/admin/pgd/relatorioindividualtrabalho/'

        extra_context['pode_entregar_rit'] = rit.pode_entregar_rit(request.user)

        pode_receber_entregas = rit.pode_receber_entregas(request.user)
        extra_context['pode_receber_entregas'] = pode_receber_entregas

        extra_context['pode_recalcular_pit_rit'] = rit.pit.pode_recalcular_pit_rit(request.user)

        atividades_pode_receber_entregas = rit.get_atividades_pode_receber_entregas().order_by(
            'atividade_pts__plano_trabalho_setorial__setor', 'atividade_pts__atividade__titulo'
        )
        # Se for o chefe que estiver acessando deve mostrar apenas as atividades do PTS do chefe
        if self.perfil == 'chefe':
            setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
            if setores:
                atividades_pode_receber_entregas = atividades_pode_receber_entregas.filter(atividade_pts__plano_trabalho_setorial__setor__in=setores)
        extra_context['atividades_pode_receber_entregas'] = atividades_pode_receber_entregas

        title = f'Execução - {rit.get_verbose_rit_servidor()}'
        extra_context['title'] = title

        # Botao de alterar modo de edicao
        if atividades_pode_receber_entregas:
            parametros_botao_editar_em_lote, parametros_botao_sair_editar_em_lote = self.get_botao_alternar_edicao(request)
            extra_context['parametros_botao_editar_em_lote'] = parametros_botao_editar_em_lote
            extra_context['parametros_botao_sair_editar_em_lote'] = parametros_botao_sair_editar_em_lote

        # Altera elementos de tela de acordo com o modo de edicao
        self.list_per_page = 1000
        self.list_display = (
            'get_pts',
            'get_atividade_aviso_desligamento',
            'get_situacao',
            'get_prioridade',
            'tipo_entrega',
            'get_descricao',
            'qtd_entregas',
            'get_tempo_executado',
            'get_tempo_medio_por_entrega_entrega',
            'data_iniciou',
            'data_finalizou',
            'executada_em_teletrabalho',
            'get_foi_aprovado_homologado',
            'get_opcoes',
        )
        self.list_display_icons = True
        self.list_editable = []
        self.actions = ['entregar_entrega', 'reverter_entrega_entregue', 'remover_entrega']
        self.sortable_by = self.get_list_display(request)

        # Lista de pendências de Avaliação de Entregas e Homologação do RIT
        quem_deve_avaliar_entregas = rit.get_ptss_das_entregas_a_avaliar_do_rit()
        quem_deve_homologar_rit = rit.get_setor_a_homologar_rit()
        extra_context['quem_deve_avaliar_entregas'] = quem_deve_avaliar_entregas
        extra_context['quem_deve_homologar_rit'] = quem_deve_homologar_rit

        extra_context['msg_adesao_relacionada'] = rit.pit.adesao

        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(rit_atividade__rit__pk=request.GET.get('rit_atividade__rit'))

        if self.perfil == 'chefe':
            # Se for o chefe que estiver acessando deve mostrar apenas as do PTS do chefe
            setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
            if setores:
                qs = qs.filter(rit_atividade__atividade_pts__plano_trabalho_setorial__setor__in=setores)

        return qs


# Chefe - Visualizar, Editar, Adicionar Entregas ao RIT
# ------------------------------------------------------------
@admin.register(RelatorioIndividualTrabalhoAtividadeEntregaChefeRegistrar)
class RelatorioIndividualTrabalhoAtividadeEntregaChefeRegistrarAdmin(RelatorioIndividualTrabalhoAtividadeEntregaServidorRegistrarAdmin):
    perfil = 'chefe'


# Chefe - Visualizar lista de RITs que pode interagir
# ------------------------------------------------------------
class AgrupamentoRitsFilter(admin.SimpleListFilter):
    title = 'Agrupamento'
    parameter_name = 'rit_ag'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'Somente os meus'),
            ('2', 'Todos menos os meus'),
            ('3', 'Todos que sou chefe imediato'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value():
            servidor = request.user.get_relacionamento()
            if self.value() == '1':
                return queryset.filter(pit__adesao__servidor=servidor)

            elif self.value() == '2':
                return queryset.exclude(pit__adesao__servidor=servidor)

            elif self.value() == '3':
                setores_que_sou_chefe_hoje = servidor.historico_funcao_ativa.filter(
                    funcao__codigo__in=Funcao.get_codigos_funcao_chefia()
                ).values_list('setor_suap', flat=True)
                queryset = queryset.exclude(pit__adesao__servidor=servidor)
                if setores_que_sou_chefe_hoje:
                    return queryset.filter(
                        Q(pit__adesao__servidor__setor__in=setores_que_sou_chefe_hoje)
                        | (
                            Q(pit__adesao__servidor__setor__superior__in=setores_que_sou_chefe_hoje)
                            & Q(pit__adesao__servidor__funcao__isnull=False)
                            & Q(pit__adesao__servidor__funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
                        )
                    )
            else:
                queryset.none()
        return queryset


class SetorRitsFilter(admin.SimpleListFilter):
    title = 'Setor'
    parameter_name = 'fsetor'

    def lookups(self, request, model_admin):
        # Ver todos
        # --------------------------------
        # estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        # estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')
        # if estah_em_gestao_pgd and estah_em_comissao_vigente:
        #    return [(s.id, s) for s in Setor.objects.suap_ativos().all()]

        # Apenas que sou chefe
        # --------------------------------
        setores = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        return [(s.id, s) for s in setores]

    def queryset(self, request, queryset):
        return queryset


class PeriodoRitFilter(admin.SimpleListFilter):
    title = 'Período'
    parameter_name = 'prit'

    def lookups(self, request, model_admin):
        periodos = PeriodoPitRit.objects.filter(cancelado=False).order_by('data_inicio')
        dados = []
        for s in periodos:
            d = f'{s.ano} - {s.titulo} - ({format_datetime(s.rit_data_inicio_1)} a {format_datetime(s.rit_data_fim_1)})'
            dados.append((s.id, d))
        return dados

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(pit__periodo_pit_rit=self.value())
        return queryset


class AvaliadoRitFilter(admin.SimpleListFilter):
    title = 'Avaliação'
    parameter_name = 'avrit'

    def lookups(self, request, model_admin):
        OPCOES = (
            ('1', 'A avaliar'),
            ('2', 'Já avaliado'),
        )
        return OPCOES

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == '1':
                return queryset.filter(aprovado_definitivo__isnull=True, homologado_definitivo__isnull=True)

            elif self.value() == '2':
                return queryset.exclude(aprovado_definitivo__isnull=True, homologado_definitivo__isnull=True)
        return queryset


@admin.register(RelatorioIndividualTrabalho)
class RelatorioIndividualTrabalhoVisualizarAvaliarAdmin(ModelAdminPlus):
    list_display = ('get_adesao_servidor', 'get_adesao_servidor_setor', 'get_pit', 'get_rit', 'entregue', 'foi_avaliado', 'get_acoes')
    list_filter = (AgrupamentoRitsFilter, SetorRitsFilter, 'entregue', AvaliadoRitFilter, PeriodoRitFilter)
    search_fields = ('pit__adesao__servidor__pessoa_fisica__nome', 'pit__adesao__servidor__matricula')
    list_display_icons = True
    filters_ajax = False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def get_rit(self, obj):
        return obj.get_verbose_rit()

    get_rit.short_description = 'RIT'

    def get_pit(self, obj):
        return str(obj.pit.get_verbose_periodo())

    get_pit.short_description = 'PIT'

    def get_adesao_servidor(self, obj):
        return str(obj.pit.adesao.servidor)

    get_adesao_servidor.short_description = 'Servidor'

    def get_adesao_servidor_setor(self, obj):
        return str(obj.pit.adesao.servidor.setor)

    get_adesao_servidor_setor.short_description = 'Setor'

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('visualizar_opcoes_rit', args=[obj_pk]))

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # estah_em_gestao_pgd = request.user.has_group_cached('Gestor do PGD')
        # estah_em_comissao_vigente = request.user.has_group_cached('Comissão Sistêmica PGD')

        # Ver todos
        # --------------------------------
        # if estah_em_gestao_pgd and estah_em_comissao_vigente:
        #    return qs

        # Ver os que pode visualizar/aprovar
        # --------------------------------
        lista_setores_que_sou_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())

        q_filter = request.GET.get('q', None)
        setor_filter = request.GET.get('fsetor', None)
        agrupamento_filter = request.GET.get(AgrupamentoRitsFilter.parameter_name, None)
        if (agrupamento_filter == '2' and len(lista_setores_que_sou_chefe_hoje) > 5) and (not q_filter and not setor_filter):
            messages.error(request, 'Selecione um Setor e/ou informe um Nome ou Matrícula do Servidor desejado.')
            return RelatorioIndividualTrabalho.objects.none()
        if q_filter:
            qs = qs.filter(Q(pit__adesao__servidor__pessoa_fisica__nome__icontains=q_filter) | Q(pit__adesao__servidor__matricula=q_filter))
        if setor_filter:
            qs = qs.filter(pit__adesao__servidor__setor_id=setor_filter)

        if qs.exists():
            qs = RelatorioIndividualTrabalho.get_rits_relacionados_ao_chefe(request.user, lista_setores_que_sou_chefe_hoje, queryset=qs)

        return qs

    def get_action_bar(self, request):
        items = []
        # rits_relacionados_ao_chefe = RelatorioIndividualTrabalho.get_rits_relacionados_ao_chefe(request.user).exists()
        # if rits_relacionados_ao_chefe:
        #    items.append(dict(url=reverse('avaliar_entregas_em_lote'), label='Avaliar Entregas em Lote', css_class='success'))
        return items

    def get_acoes(self, obj):
        lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(self.request.user.get_relacionamento())

        strs = []
        if obj.pode_avaliar_entregas_rit(self.request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
            strs.append(
                f"""
                <ul class="action-bar">
                    <li><a href="/admin/pgd/relatorioindividualtrabalhoatividadeentregaavaliar/?rit_atividade__rit={obj.id}" class="btn primary">Avaliar e Homologar (RIT)</a></li>
                </ul>
            """.format(id=obj.id)
            )
        if obj.pode_reabrir_rit(self.request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
            strs.append(
                f"""
                <ul class="action-bar">
                    <li><a href="/pgd/devolver_rit_servidor/{obj.id}" class="btn primary">Devolver RIT</a></li>
                </ul>
            """.format(id=obj.id)
            )

        return mark_safe(' '.join(strs))

    get_acoes.short_description = 'Ações'


# Chefe - Analisar Entregas e RIT
# ------------------------------------------------------------


class EntregaFoiAvaliadaFilter(admin.SimpleListFilter):
    title = 'Foi avaliada'
    parameter_name = 'foi_avaliada'

    def lookups(self, request, model_admin):
        return [('1', 'Foi avaliado'), ('2', 'Não foi avaliado')]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(aprovado__isnull=False, homologado__isnull=False)
        if self.value() == '2':
            return queryset.filter(aprovado__isnull=True, homologado__isnull=True)
        return queryset


@admin.register(RelatorioIndividualTrabalhoAtividadeEntregaAvaliar)
class RelatorioIndividualTrabalhoAtividadeEntregaAvaliarAdmin(ModelAdminPlus):
    # Só o Chefe acesssa - Analisar Entregas e RIT (de um servidor que puder avaliar)
    # Servidor NÃO ACESSA ESSA TELA
    # Comissao NÃO ACESSA ESSA TELA

    list_filter = (
        'rit_atividade__rit',
        FiltroEditarLoteFilter,
        EntregaFoiAvaliadaFilter,
        'rit_atividade',
        'rit_atividade__atividade_pts__plano_trabalho_setorial',
    )
    hidden_filters = ['rit_atividade__rit', 'editar_em_lote']
    filters_ajax = False
    actions = ['avaliar_entrega']

    change_list_template = 'pgd/templates/rit_entregas_analisar.html'

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return True

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('avaliar_entrega_rit', args=[obj_pk]))

    def get_visualizar(self, obj):
        if obj.pode_visualizar(self.request.user):
            return mark_safe(
                f'<a class="icon icon-view" href="/pgd/avaliar_entrega_rit/{obj.id}/" title="Visualizar Entrega"><span class="visually-hidden">Visualizar</span></a>'
            )
        return ''

    get_visualizar.short_description = '#'

    def avaliar_entrega(self, request, queryset):
        parametros = []
        parametros.append('rit_id={}'.format(request.GET.get('rit_atividade__rit')))
        parametros.append('action={}'.format(request.POST.getlist('action')[0]))
        parametros.append('checks=' + '&checks='.join(request.POST.getlist('_selected_action')))
        parametros.append('p=chefe')
        parametros = mark_safe('&'.join(parametros))
        return HttpResponseRedirect(f'/pgd/servidor_chefe_operacoes_entrega_rit/?{parametros}')

    avaliar_entrega.short_description = 'Avaliar Entrega'

    def get_actions(self, request):
        actions = super().get_actions(request)
        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))
        if 'avaliar_entrega' in actions and not rit.pode_avaliar_entregas_rit(request.user):
            del actions['avaliar_entrega']
        return actions

    # def get_periodo(self, obj):
    #    return mark_safe(f'<strong>De:</strong> {format_datetime(obj.data_iniciou)}<br><strong>Até:</strong> {format_datetime(obj.data_finalizou)}')
    # get_periodo.short_description = 'Período'
    # get_periodo.admin_order_field = 'data_iniciou'

    # def get_tempo_execucao(self, obj):
    #    exec_tempo_executado = mark_safe(f'<strong>Total de horas da execução:</strong> {format_hours(obj.tempo_executado)}<br>')
    #    exec_tempo_medio_por_entrega_entrega = mark_safe(f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_entrega)}<br>')
    #    exec_tempo_faixa_complexidade = mark_safe(f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {obj.faixa_complexidade_entrega.faixa_complexidade.complexidade} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega))})<br>')
    #    exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = mark_safe(f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega)}')
    #    return mark_safe(f'{exec_tempo_executado}{exec_tempo_medio_por_entrega_entrega}{exec_tempo_faixa_complexidade}{exec_total_tempo_ajustado_pela_faixa_complexidade_entrega}')
    # get_tempo_execucao.short_description = 'Tempo Execução'

    """
    def get_foi_avaliado(self, obj):
        icone_none = mark_safe('<img src="/static/admin/img/icon-unknown.svg" alt="None">')
        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

        nota = None

        aprovado = icone_none
        if not (obj.aprovado is None):
            aprovado = icone_true if obj.aprovado else icone_false
        homologado = icone_none
        if not (obj.homologado is None):
            homologado = icone_true if obj.homologado else icone_false
            nota = obj.nota

        str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}')
        if nota:
           str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}<br><strong>Nota:</strong> {nota}')
        return mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}')
    get_foi_avaliado.short_description = 'Foi avaliado'

    def get_tempo_avaliado(self, obj):
        aval_tempo = mark_safe(f'<strong>Total de horas homologadas:</strong> {format_hours(obj.tempo_executado_homologado)}<br>')
        aval_tempo_medio_por_entrega = mark_safe(f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_avaliacao)}<br>')

        fx_complex = '-'
        if obj.faixa_complexidade_entrega_avaliacao and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade:
            fx_complex = obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
        aval_tempo_faixa_complexidade = mark_safe(f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {fx_complex} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao))})<br>')

        aval_total_tempo_ajustado_pela_faixa_complexidade = mark_safe(f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao)}')
        return mark_safe(f'{aval_tempo}{aval_tempo_medio_por_entrega}{aval_tempo_faixa_complexidade}{aval_total_tempo_ajustado_pela_faixa_complexidade}')
    get_tempo_avaliado.short_description = 'Tempo Avaliado'
    """

    def has_change_permission(self, request, obj=None):
        return False

    def get_opcoes(self, obj):
        texto = '-'
        if obj.pode_remover(self.request.user):
            texto = '<ul class="action-bar">'
            texto += f'<li><a href="/pgd/remover_entrega_rit/{obj.id}" class="btn danger">Remover</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        if not request.GET.get('rit_atividade__rit'):
            raise PermissionDenied

        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))
        if not rit.pode_visualizar(request.user):
            raise PermissionDenied

        ptss_relacionados = rit.pit.get_pts_relacionados()
        if ptss_relacionados:
            for pts_relacionados in ptss_relacionados:
                pts_relacionados.sincrononiza_inativacao_atividades()

        rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
        rit = RelatorioIndividualTrabalho.objects.get(pk=request.GET.get('rit_atividade__rit'))
        extra_context['rit'] = rit
        extra_context['pit'] = rit.pit
        extra_context['servidor'] = rit.pit.adesao.servidor

        atividades_pode_receber_entregas = rit.get_atividades_pode_receber_entregas()
        extra_context['atividades_pode_receber_entregas'] = atividades_pode_receber_entregas

        relacionamento = request.user.get_relacionamento()
        lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(relacionamento)

        servidor_pode_hr = rit.pode_chefe_editar(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)

        extra_context['pode_homologar_rit'] = rit.pode_homologar_rit(
            request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje, pode_chefe_editar=servidor_pode_hr
        )
        extra_context['pode_reabrir_rit'] = rit.pode_reabrir_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)
        extra_context['pode_avaliar_entregas_rit'] = rit.pode_avaliar_entregas_rit(
            request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje
        )

        extra_context['title'] = f'Avaliação e Homologação - {rit.get_verbose_rit_servidor()}'

        self.list_per_page = 200
        self.list_display = (
            'get_visualizar',
            'id',
            'get_pts',
            'get_atividade_aviso_desligamento',
            'get_prioridade',
            'get_entrega',
            'get_execucao',
            'get_avaliacao',
        )
        # self.list_display_icons = True
        self.sortable_by = self.get_list_display(request)

        # Lista de pendências de Avaliação de Entregas e Homologação do RIT
        quem_deve_avaliar_entregas = rit.get_ptss_das_entregas_a_avaliar_do_rit()
        quem_deve_homologar_rit = rit.get_setor_a_homologar_rit()
        extra_context['quem_deve_avaliar_entregas'] = quem_deve_avaliar_entregas
        extra_context['quem_deve_homologar_rit'] = quem_deve_homologar_rit

        extra_context['msg_adesao_relacionada'] = rit.pit.adesao

        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))

        lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(request.user.get_relacionamento())
        pode_avaliar_entregas_rit = rit.pode_avaliar_entregas_rit(request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)

        if not pode_avaliar_entregas_rit:
            return qs.none()

        return RelatorioIndividualTrabalhoAtividadeEntregaAvaliar.get_entregas_posso_avaliar(
            request.user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje, rit=rit
        ).select_related(
            'rit_atividade__atividade_pts',
            'rit_atividade__atividade_pts__plano_trabalho_setorial',
            'tipo_entrega',
            'rit_atividade__atividade_pts__plano_trabalho_setorial__setor',
        )


class EntregaChefePodeAvaliarFilter(admin.SimpleListFilter):
    title = 'Foi avaliada'
    parameter_name = 'foi_avaliada'

    def lookups(self, request, model_admin):
        return [('1', 'Foi avaliado'), ('2', 'Não foi avaliado')]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(aprovado__isnull=False, homologado__isnull=False)
        if self.value() == '2':
            return queryset.filter(aprovado__isnull=True, homologado__isnull=True)
        return queryset


@admin.register(RelatorioIndividualTrabalhoAtividadeEntregaTodasAvaliar)
class RelatorioIndividualTrabalhoAtividadeEntregaTodasAvaliarAdmin(ModelAdminPlus):
    # Só o Chefe acesssa - Lista todas as entregas que o chefe Deve Avaliar OU Pode Avaliar/Reavaliar (de todos os servidores que puder avaliar)
    # Servidor NÃO ACESSA ESSA TELA
    # Comissao NÃO ACESSA ESSA TELA

    list_filter = (EntregaFoiAvaliadaFilter, 'rit_atividade', 'rit_atividade__atividade_pts__plano_trabalho_setorial')

    def get_atividade(self, obj):
        return mark_safe(f'{obj.rit_atividade.atividade_pts}')

    get_atividade.short_description = 'Atividade'

    def get_pts(self, obj):
        return mark_safe(f'{obj.rit_atividade.atividade_pts.plano_trabalho_setorial}')

    get_pts.short_description = 'PTS'

    def get_prioridade(self, obj):
        return mark_safe(status(obj.get_prioridade_display()))

    get_prioridade.short_description = 'Prioridade'
    get_prioridade.admin_order_field = 'prioridade'

    def get_entrega(self, obj):
        return mark_safe(f'<strong>Tipo:</strong> {obj.tipo_entrega}<br><strong>Descrição:</strong> {obj.descricao}')

    get_entrega.short_description = 'Entrega'
    get_entrega.admin_order_field = 'tipo_entrega__titulo'

    # def get_periodo(self, obj):
    #    return mark_safe(f'<strong>De:</strong> {format_datetime(obj.data_iniciou)}<br><strong>Até:</strong> {format_datetime(obj.data_finalizou)}')
    # get_periodo.short_description = 'Período'
    # get_periodo.admin_order_field = 'data_iniciou'

    # def get_tempo_execucao(self, obj):
    #    exec_tempo_executado = mark_safe(f'<strong>Total de horas da execução:</strong> {format_hours(obj.tempo_executado)}<br>')
    #    exec_tempo_medio_por_entrega_entrega = mark_safe(f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_entrega)}<br>')
    #    exec_tempo_faixa_complexidade = mark_safe(f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {obj.faixa_complexidade_entrega.faixa_complexidade.complexidade} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega))})<br>')
    #    exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = mark_safe(f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega)}')
    #    return mark_safe(f'{exec_tempo_executado}{exec_tempo_medio_por_entrega_entrega}{exec_tempo_faixa_complexidade}{exec_total_tempo_ajustado_pela_faixa_complexidade_entrega}')
    # get_tempo_execucao.short_description = 'Tempo Execução'

    def get_execucao(self, obj):
        periodo = mark_safe(
            f'<strong>De:</strong> {format_datetime(obj.data_iniciou)}<br><strong>Até:</strong> {format_datetime(obj.data_finalizou)}<br>'
        )
        exec_tempo_executado = mark_safe(f'<strong>Total de horas da execução:</strong> {format_hours(obj.tempo_executado)}<br>')

        exec_tempo_medio_por_entrega_entrega = ''
        exec_tempo_faixa_complexidade = ''
        exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = ''
        if obj.rit_atividade.rit.pode_mostrar_ajustado:
            exec_tempo_medio_por_entrega_entrega = mark_safe(
                f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_entrega)}<br>'
            )

            exec_tempo_faixa_complexidade = '-'
            if (
                obj.faixa_complexidade_entrega
                and obj.faixa_complexidade_entrega.faixa_complexidade
                and obj.faixa_complexidade_entrega.faixa_complexidade.complexidade
                and obj.tempo_ajustado_pela_faixa_complexidade_entrega
            ):
                exec_tempo_faixa_complexidade = mark_safe(
                    f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {obj.faixa_complexidade_entrega.faixa_complexidade.complexidade} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega))})<br>'
                )

            exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = mark_safe(
                f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega)}<br>'
            )

        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')
        ico_executada_em_teletrabalho = icone_true if obj.executada_em_teletrabalho else icone_false
        se_executada_em_teletrabalho = f'<strong>Executada em Teletrabalho:</strong> {ico_executada_em_teletrabalho}'

        return mark_safe(
            f'{periodo}{exec_tempo_executado}{exec_tempo_medio_por_entrega_entrega}{exec_tempo_faixa_complexidade}{exec_total_tempo_ajustado_pela_faixa_complexidade_entrega}{se_executada_em_teletrabalho}'
        )

    get_execucao.short_description = 'Execução'
    get_execucao.admin_order_field = 'data_iniciou'

    """
    def get_foi_avaliado(self, obj):
        icone_none = mark_safe('<img src="/static/admin/img/icon-unknown.svg" alt="None">')
        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')

        nota = None

        aprovado = icone_none
        if not (obj.aprovado is None):
            aprovado = icone_true if obj.aprovado else icone_false
        homologado = icone_none
        if not (obj.homologado is None):
            homologado = icone_true if obj.homologado else icone_false
            nota = obj.nota

        str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}')
        if nota:
           str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}<br><strong>Nota:</strong> {nota}')
        return mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}')
    get_foi_avaliado.short_description = 'Foi avaliado'

    def get_tempo_avaliado(self, obj):
        aval_tempo = mark_safe(f'<strong>Total de horas homologadas:</strong> {format_hours(obj.tempo_executado_homologado)}<br>')
        aval_tempo_medio_por_entrega = mark_safe(f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_avaliacao)}<br>')

        fx_complex = '-'
        if obj.faixa_complexidade_entrega_avaliacao and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade:
            fx_complex = obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
        aval_tempo_faixa_complexidade = mark_safe(f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {fx_complex} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao))})<br>')

        aval_total_tempo_ajustado_pela_faixa_complexidade = mark_safe(f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao)}')
        return mark_safe(f'{aval_tempo}{aval_tempo_medio_por_entrega}{aval_tempo_faixa_complexidade}{aval_total_tempo_ajustado_pela_faixa_complexidade}')
    get_tempo_avaliado.short_description = 'Tempo Avaliado'
    """

    def get_avaliacao(self, obj):
        icone_none = mark_safe('<img src="/static/admin/img/icon-unknown.svg" alt="None">')
        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')
        nota = None
        aprovado = icone_none
        if obj.aprovado is not None:
            aprovado = icone_true if obj.aprovado else icone_false
        homologado = icone_none
        if obj.homologado is not None:
            homologado = icone_true if obj.homologado else icone_false
            nota = obj.nota
        str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado} <br>')
        if nota:
            str = mark_safe(
                f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}<br><strong>Nota:</strong> {nota} <br>'
            )
        aprov_hom = str
        # ------------------------
        aval_tempo = mark_safe(f'<strong>Total de horas homologadas:</strong> {format_hours(obj.tempo_executado_homologado)}<br>')

        aval_tempo_medio_por_entrega = ''
        fx_complex = ''
        aval_tempo_faixa_complexidade = ''
        aval_total_tempo_ajustado_pela_faixa_complexidade = ''
        if obj.rit_atividade.rit.pode_mostrar_ajustado:
            aval_tempo_medio_por_entrega = mark_safe(
                f'<strong>Tempo médio por entrega:</strong> {format_hours(obj.tempo_medio_por_entrega_avaliacao)}<br>'
            )
            fx_complex = '-'
            if (
                obj.faixa_complexidade_entrega_avaliacao
                and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade
                and obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
            ):
                fx_complex = obj.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
            aval_tempo_faixa_complexidade = mark_safe(
                f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {fx_complex} ({(format_hours(obj.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao))})<br>'
            )
            aval_total_tempo_ajustado_pela_faixa_complexidade = mark_safe(
                f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(obj.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao)}'
            )

        tempos = mark_safe(
            f'{aval_tempo}{aval_tempo_medio_por_entrega}{aval_tempo_faixa_complexidade}{aval_total_tempo_ajustado_pela_faixa_complexidade}'
        )
        # ------------------------
        return mark_safe(f'{aprov_hom}{tempos}')

    get_avaliacao.short_description = 'Avaliação'

    def has_view_permission(self, request, obj=None):
        if obj:
            return obj.pode_visualizar(request.user)
        return True

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('avaliar_entrega_rit', args=[obj_pk]))

    def has_change_permission(self, request, obj=None):
        return False

    def get_opcoes(self, obj):
        texto = '-'
        if obj.pode_remover(self.request.user):
            texto = '<ul class="action-bar">'
            texto += f'<li><a href="/pgd/remover_entrega_rit/{obj.id}" class="btn danger">Remover</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}

        if not request.GET.get('rit_atividade__rit'):
            raise PermissionDenied

        rit = get_object_or_404(RelatorioIndividualTrabalho, pk=request.GET.get('rit_atividade__rit'))
        extra_context['rit'] = rit
        extra_context['pit'] = rit.pit
        extra_context['servidor'] = rit.pit.adesao.servidor

        # servidor = request.user.get_relacionamento()
        if not rit.pode_visualizar(request.user):
            raise PermissionDenied

        rit.pit.calcular_pit(forcar_recalcular_tempo_previsto=True)
        rit = RelatorioIndividualTrabalho.objects.get(pk=request.GET.get('rit_atividade__rit'))

        atividades_pode_receber_entregas = rit.get_atividades_pode_receber_entregas()
        extra_context['atividades_pode_receber_entregas'] = atividades_pode_receber_entregas

        extra_context['title'] = f'Avaliação e Homologação - {rit.get_verbose_rit_servidor()}'

        self.list_per_page = 1000
        self.list_display = ('get_pts', 'get_atividade_aviso_desligamento', 'get_prioridade', 'get_entrega', 'get_execucao', 'get_avaliacao')
        self.list_display_icons = True
        self.sortable_by = self.get_list_display(request)

        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        ids_pode_avaliar = []
        for entrega in qs:
            if entrega.pode_avaliar(request.user):
                ids_pode_avaliar.append(entrega.id)
        if ids_pode_avaliar:
            return qs.filter(id__in=ids_pode_avaliar)

        return RelatorioIndividualTrabalhoAtividadeEntregaTodasAvaliar.objects.none()
