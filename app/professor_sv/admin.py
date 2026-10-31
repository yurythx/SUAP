from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse

from djtools.contrib.admin import ModelAdminPlus
from professor_sv.forms import ContratoForm, GrupoForm
from professor_sv.models import Categoria, Configuracao, Contrato, Grupo, SolicitacaoEmprestimoVaga, TempoExpiracao, Vaga
from rh.models import Setor, UnidadeOrganizacional


@admin.register(Categoria)
class CategoriaAdmin(ModelAdminPlus):
    list_display = ('titulo', 'get_perfis_display')
    list_display_icons = True

    def has_delete_permission(self, request, obj=None):
        pode = super().has_delete_permission(request, obj)
        return pode and obj and not obj.existem_relacionados()


@admin.register(Grupo)
class GrupoAdmin(ModelAdminPlus):
    list_display = ('titulo', 'uo')
    list_display_icons = True
    form = GrupoForm

    def get_fields(self, request, obj):
        uo = None
        if not obj:
            uo = UnidadeOrganizacional.objects.suap().filter(id=request.GET.get('uo_id')).first()
        else:
            uo = obj.uo
        if not uo.eh_reitoria:
            return ('titulo', 'setor_dg', 'setores_cogpe', 'setores_cogpe_gerenciar', 'vinculos_pode_gerenciar_vaga')
        return ('titulo', 'setores_cogpe_gerenciar', 'vinculos_pode_gerenciar_vaga')

    def add_view(self, request, form_url='', extra_context=None):
        if not request.GET.get('uo_id'):
            return HttpResponseRedirect(reverse('seleciona_campus'))
        uo = UnidadeOrganizacional.objects.suap().filter(id=request.GET.get('uo_id')).first()
        extra_context = extra_context or {}
        extra_context['title'] = f'Adicionar Grupo - Campus {uo}'
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj=obj, **kwargs)
        uo = None
        if not obj:
            uo = UnidadeOrganizacional.objects.suap().filter(id=request.GET.get('uo_id')).first()
        else:
            uo = obj.uo

        if not uo.eh_reitoria:
            form.base_fields['setor_dg'].queryset = Setor.objects.suap_ativos().filter(uo=uo)
            form.base_fields['setores_cogpe'].queryset = Setor.objects.suap_ativos().filter(uo=uo)

        form.base_fields['setores_cogpe_gerenciar'].queryset = Setor.objects.suap_ativos().filter(uo=uo)

        return form

    def change_view(self, request, object_id, form_url='', extra_context=None):
        grupo = Grupo.objects.get(id=object_id)
        extra_context = extra_context or {}
        extra_context['title'] = f'Editar {grupo} - Campus {grupo.uo}'
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if obj and not obj.id:
            obj.uo = UnidadeOrganizacional.objects.suap().filter(id=request.GET.get('uo_id')).first()
        obj.save()

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(reverse('admin:professor_sv_grupo_changelist'))


class VagasOcupadasFilter(admin.SimpleListFilter):
    title = 'Ocupadas'
    parameter_name = 'vo'

    def lookups(self, request, model_admin):
        opcoes = []
        opcoes.append(('1', 'Sim'))
        opcoes.append(('2', 'Não'))
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            ids = Vaga.get_vagas_ocupadas().values('id')
            return queryset.filter(id__in=ids)
        if self.value() == '2':
            ids = Vaga.get_vagas_desocupadas().values('id')
            return queryset.filter(id__in=ids)
        return queryset


class VagasGrupoDonoTomadorFilter(admin.SimpleListFilter):
    title = 'Grupo dono ou tomador'
    parameter_name = 'gdt'

    def lookups(self, request, model_admin):
        ids = list(Vaga.objects.values_list('grupo_dono_id', flat=True).distinct())
        ids.extend(list(Vaga.objects.values_list('grupo_tomador_id', flat=True).distinct()))
        return [(g.id, g.titulo) for g in Grupo.objects.filter(id__in=ids)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter((Q(grupo_dono_id=self.value()) & Q(grupo_tomador__isnull=True)) | (Q(grupo_tomador_id=self.value())))
        return queryset


class ExpiracaoEmprestimoVagaFilter(admin.SimpleListFilter):
    title = 'Empréstimo a expirar em'
    parameter_name = 'vex'

    def lookups(self, request, model_admin):
        return TempoExpiracao.DIAS_EXPIRA_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            qtd_dias_alerta = int(self.value())
            return queryset.filter(id__in=Vaga.get_vagas_emprestimos_a_vencer(qtd_dias_alerta=qtd_dias_alerta).values_list('id', flat=True))
        return queryset


@admin.register(Vaga)
class VagaAdmin(ModelAdminPlus):
    list_display = ('codigo', 'perfil', 'categoria', 'grupo_dono', 'get_emprestimo_str', 'estah_ocupada', 'ativo')
    list_filter = (
        'perfil',
        'categoria',
        'grupo_dono',
        'grupo_tomador',
        VagasGrupoDonoTomadorFilter,
        'ativo',
        VagasOcupadasFilter,
        ExpiracaoEmprestimoVagaFilter,
    )
    list_display_icons = True
    search_fields = ('codigo',)
    ordering = ('codigo',)

    def has_change_permission(self, request, obj=None):
        return False

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('gerenciar_vaga', args=[obj_pk]))

    def changelist_view(self, request, extra_context=None):
        if not Configuracao.pode_iniciar_operacao_modulo():
            raise PermissionDenied('Os cadastrados básicos devem ter sido realizados')
        Vaga.atualizar_historico_movimentacao_vagas()
        return super().changelist_view(request, extra_context=extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        return HttpResponseRedirect(reverse('seleciona_categoria'))

    def get_action_bar(self, request, remove_add_button=False):
        botoes = []

        solicitacoes = SolicitacaoEmprestimoVaga.get_solicitacoes_emprestimo_aprovacao_pendente(request.user.get_relacionamento())
        if solicitacoes:
            botoes.append(
                {'url': '/professor_sv/aprovar_solicitacao_emprestimo/', 'label': 'Avaliar Solicitações de Empréstimos', 'css_class': 'default'}
            )

        botoes.append({'url': '/professor_sv/quadro_vagas/', 'label': 'Quadro de Vagas', 'css_class': 'default'})

        return botoes + super().get_action_bar(request)


class SituacaoContratoFilter(admin.SimpleListFilter):
    title = 'Situação'
    parameter_name = 'sc'

    def lookups(self, request, model_admin):
        return Contrato.SITUACAO_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            if int(self.value()) == Contrato.SITUACAO_ATIVO:
                return queryset.ativos()
            if int(self.value()) == Contrato.SITUACAO_A_INICIAR:
                return queryset.a_iniciarem()
            if int(self.value()) == Contrato.SITUACAO_EM_ANDAMENTO:
                return queryset.em_andamento()
            if int(self.value()) == Contrato.SITUACAO_EXPIRADO:
                return queryset.expirados()
            if int(self.value()) == Contrato.SITUACAO_CONCLUIDO:
                return queryset.concluidos()
            if int(self.value()) == Contrato.SITUACAO_CANCELADO:
                return queryset.cancelados()
        return queryset


class ExpiracaoContratoFilter(admin.SimpleListFilter):
    title = 'A expirar em'
    parameter_name = 'cex'

    def lookups(self, request, model_admin):
        return TempoExpiracao.DIAS_EXPIRA_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            qtd_dias_alerta = int(self.value())
            return queryset.filter(id__in=Contrato.get_proximos_a_expirar(qtd_dias_alerta=qtd_dias_alerta).values_list('id', flat=True))
        return queryset


@admin.register(Contrato)
class ContratoAdmin(ModelAdminPlus):
    list_display = (
        'servidor_docente',
        'get_servidor_docente_uo_',
        'vaga',
        'documento_eletronico',
        'data_inicio',
        'data_expira',
        'get_docente_efetivo',
        'get_situacao_display',
    )

    list_display_icons = True

    list_filter = (
        'servidor_docente',
        'servidor_docente__setor__uo',
        'vaga',
        'documento_eletronico',
        SituacaoContratoFilter,
        'vaga__perfil',
        ExpiracaoContratoFilter,
    )

    ordering = ['-data_inicio', 'servidor_docente__pessoa_fisica__nome', '-id']

    # servidor_docente_titular OU codigo_vaga_servidor_docente_titular
    search_fields = (
        'servidor_docente_titular__pessoa_fisica__nome',
        'servidor_docente_titular__matricula',
        'servidor_docente_titular__codigo_vaga',
        'codigo_vaga_servidor_docente_titular',
    )
    label_input_search_fields = 'Nome/Matrícula do Docente Efetivo ou Código da Vaga do Docente Efetivo'

    form = ContratoForm

    def get_action_bar(self, request, remove_add_button=False):
        botoes = []

        botoes.append({'url': '/professor_sv/quadro_limites/', 'label': 'Quadro de Limites de Vagas', 'css_class': 'default'})

        return botoes + super().get_action_bar(request)

    def add_view(self, request, form_url='', extra_context=None):
        return HttpResponseRedirect(reverse('seleciona_vaga_para_contrato'))

    def get_servidor_docente_uo_(self, obj):
        if obj:
            return obj.get_servidor_docente_uo()
        return None

    get_servidor_docente_uo_.short_description = 'Campus'
    get_servidor_docente_uo_.admin_order_field = 'servidor_docente__setor__uo'

    def has_add_permission(self, request):
        return Contrato.user_pode_cadastrar_contrato(user=request.user)

    def has_change_permission(self, request, obj=None):
        return False

    def render_view_object(self, request, obj_pk):
        return HttpResponseRedirect(reverse('gerenciar_contrato', args=[obj_pk]))

    def changelist_view(self, request, extra_context=None):
        if not Configuracao.pode_iniciar_operacao_modulo():
            raise PermissionDenied('Os cadastrados básicos devem ter sido realizados')
        return super().changelist_view(request, extra_context=extra_context)
