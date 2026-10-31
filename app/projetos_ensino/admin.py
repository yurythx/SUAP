import datetime
import html

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from comum.models import Vinculo
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_
from djtools.templatetags.tags import icon
from projetos_ensino.forms import (
    AvaliadorExternoForm,
    CampusAdicionalForm,
    ColaboradorExternoForm,
    ComissaoAcompanhamentoForm,
    ComissaoEditalForm,
    EditalForm,
    EditarHistoricoEquipeForm,
)
from projetos_ensino.models import (
    AreaLicaoAprendida,
    AvaliadorExterno,
    CampusAdicional,
    CaracterizacaoBeneficiario,
    ColaboradorExterno,
    ComissaoAcompanhamento,
    ComissaoEdital,
    CriterioAvaliacaoAluno,
    Edital,
    EixoTematico,
    HistoricoEquipe,
    OfertaProjeto,
    OrigemRecursoEdital,
    Parametro,
    Participacao,
    Projeto,
    ProjetoCancelado,
    TipoBeneficiario,
    TipoVinculo,
)
from rh.models import UnidadeOrganizacional


class EditalListFilter(admin.SimpleListFilter):
    title = 'Edital'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        editais = Edital.objects
        ano = request.GET.get('ano')
        if ano:
            editais = editais.filter(inicio_inscricoes__year=ano)
        return editais.values_list('id', 'titulo')

    def queryset(self, request, queryset):
        if self.value():
            projetos = queryset.filter(edital__pk=request.GET.get(self.parameter_name))
            if 'ano' in request.GET:
                edital = Edital.objects.get(id=request.GET.get(self.parameter_name))
                if projetos.filter(edital__inicio_inscricoes__year=request.GET.get('ano')).exists():
                    return projetos.filter(edital__inicio_inscricoes__year=request.GET.get('ano'))

                elif edital.inicio_inscricoes.year != int(request.GET.get('ano')):
                    return queryset.filter(edital__inicio_inscricoes__year=request.GET.get('ano'))
                else:
                    return projetos

            return projetos

        return queryset


class AnoProjetoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        anos = []

        for data in Edital.objects.all().dates('inicio_inscricoes', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__inicio_inscricoes__year=self.value())


class ProjetoAdmin(ModelAdminPlus):
    title = 'Projetos'
    list_display = (
        'icones',
        'uo',
        'edital',
        'get_coordenador',
        'titulo',
        'get_situacao',
        'get_pre_aprovado',
        'get_aprovado',
        'get_pontuacao',
        'icone_imprimir',
    )
    ordering = ('classificacao', '-pontuacao')
    search_fields = ('titulo', 'resumo', 'vinculo_coordenador__pessoa__nome')
    export_to_xls = True
    fieldsets = (
        (None, {'fields': ('edital', 'uo')}),
        (
            'Dados do Projeto',
            {
                'fields': (
                    'titulo',
                    'area_conhecimento',
                    'eixo_tematico',
                    'justificativa',
                    'resumo',
                    'objetivo_geral',
                    'metodologia',
                    'acompanhamento_e_avaliacao',
                    'resultados_esperados',
                    'inicio_execucao',
                    'fim_execucao',
                )
            },
        ),
    )

    list_filter = (CustomTabListFilter, AnoProjetoListFilter, EditalListFilter, 'uo')
    list_per_page = 20
    list_display_icons = False
    show_count_on_tabs = True

    def to_xls(self, request, queryset, processo):
        header = [
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            'Quantidade Prevista de Pessoas a Atender',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            'Quantidade de Pessoas Atendidas',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
        ]

        rows = [header]
        tipos_beneficiarios = []
        for tipo in TipoBeneficiario.objects.all().order_by('descricao'):
            tipos_beneficiarios.append(f'{tipo.descricao}')
        header = [
            '#',
            'Título',
            'Situação',
            'Resumo do Projeto',
            'Edital',
            'Ano do Edital',
            'Coordenador',
            'Email do Coordenador',
            'Campus',
            'Período de Execução',
            'Pontuação',
        ]
        for item in tipos_beneficiarios:
            header.append(item)
        for item in tipos_beneficiarios:
            header.append(item)
        rows.append(header)
        for idx, obj in enumerate(queryset):
            if obj.vinculo_coordenador:
                coordenador = obj.vinculo_coordenador
            else:
                coordenador = obj.get_responsavel()
            periodo = f'De {format_(obj.inicio_execucao)} a {format_(obj.fim_execucao)}'

            row = [
                idx + 1,
                obj.titulo,
                obj.get_status(),
                strip_tags(html.unescape(obj.resumo)),
                obj.edital.titulo,
                obj.edital.inicio_inscricoes.year,
                coordenador.pessoa.nome,
                coordenador.email_notificacao,
                obj.uo,
                periodo,
                mark_safe(obj.pontuacao),
            ]
            for tipo in TipoBeneficiario.objects.all().order_by('descricao'):
                caracterizacao = CaracterizacaoBeneficiario.objects.filter(projeto=obj, tipo_beneficiario=tipo)
                if caracterizacao.exists():
                    row.append(caracterizacao[0].quantidade)
                else:
                    row.append('0')
            for tipo in TipoBeneficiario.objects.all().order_by('descricao'):
                caracterizacao = CaracterizacaoBeneficiario.objects.filter(projeto=obj, tipo_beneficiario=tipo)
                if caracterizacao.exists():
                    row.append(caracterizacao[0].quantidade_atendida)
                else:
                    row.append('0')

            rows.append(row)
        return rows

    def icones(self, obj):
        return mark_safe(icon('view', f'/projetos_ensino/projeto/{obj.id}/'))

    icones.short_description = 'Ações'

    def get_pontuacao(self, obj):
        return mark_safe(obj.pontuacao)

    get_pontuacao.short_description = 'Pontuação'

    def has_add_permission(self, request):
        return False

    def get_coordenador(self, obj):
        participacao = obj.participacao_set.get(responsavel=True)
        retorno = participacao.get_nome()
        if participacao.vinculo == TipoVinculo.BOLSISTA and participacao.bolsa_concedida is True:
            retorno = retorno + '<br><b>Bolsista</b>'

        return mark_safe(retorno)

    get_coordenador.short_description = 'Coordenador'

    def get_pre_aprovado(self, obj):
        return mark_safe(obj.get_pre_selecionado())

    get_pre_aprovado.short_description = 'Pré-selecionado'

    def get_aprovado(self, obj):
        return mark_safe(obj.get_selecionado())

    get_aprovado.short_description = 'Selecionado'

    def get_situacao(self, obj):
        if obj.get_status() == Projeto.STATUS_CONCLUIDO:
            retorno = f'<span class="status status-success">{obj.get_status()}</span>'
        elif (
            obj.get_status() == Projeto.STATUS_NAO_SELECIONADO
            or obj.get_status() == Projeto.STATUS_NAO_ACEITO
            or obj.get_status() == Projeto.STATUS_NAO_ENVIADO
            or obj.get_status() == Projeto.STATUS_CANCELADO
            or obj.inativado
        ):
            retorno = f'<span class="status status-error">{obj.get_status()}</span>'
        else:
            retorno = f'<span class="status status-alert">{obj.get_status()}</span>'
        return mark_safe(retorno)

    get_situacao.short_description = 'Situação Atual'

    def icone_imprimir(self, obj):
        return mark_safe(f'<a href="/projetos_ensino/imprimir_projeto/{obj.id}/" class="btn">Imprimir</a>')

    icone_imprimir.short_description = 'Opções'

    def get_tabs(self, request):
        return [
            'tab_em_edicao',
            'tab_enviados',
            'tab_pre_selecionados',
            'tab_selecionados',
            'tab_em_execucao',
            'tab_concluidos',
            'tab_nao_enviados',
            'tab_nao_pre_selecionados',
            'tab_nao_selecionados',
            'tab_inativados',
            'tab_cancelados',
        ]

    def tab_selecionados(self, request, queryset):
        hoje = datetime.datetime.now()
        cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
        if request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return queryset.filter(aprovado=True).exclude(id__in=cancelados)
        else:
            return queryset.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje).exclude(id__in=cancelados)

    tab_selecionados.short_description = 'Selecionados'

    def tab_nao_selecionados(self, request, queryset):
        hoje = datetime.datetime.now()
        if request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return queryset.filter(aprovado=False, pre_aprovado=True)
        else:
            return queryset.filter(aprovado=False, pre_aprovado=True, edital__divulgacao_selecao__lt=hoje)

    tab_nao_selecionados.short_description = 'Não Selecionados'

    def tab_pre_selecionados(self, request, queryset):
        return queryset.filter(pre_aprovado=True)

    tab_pre_selecionados.short_description = 'Pré-Selecionados'

    def tab_nao_pre_selecionados(self, request, queryset):
        return queryset.filter(pre_aprovado=False, data_conclusao_planejamento__isnull=False)

    tab_nao_pre_selecionados.short_description = 'Não Pré-Selecionados'

    def tab_em_execucao(self, request, queryset):
        hoje = datetime.datetime.now()
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
        return queryset.filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            edital__divulgacao_selecao__lt=hoje,
            inativado=False,
        ).exclude(id__in=projetos_cancelados)

    tab_em_execucao.short_description = 'Em Execução'

    def tab_concluidos(self, request, queryset):
        return queryset.filter(registroconclusaoprojeto__dt_avaliacao__isnull=False)

    tab_concluidos.short_description = 'Concluídos'

    def tab_em_edicao(self, request, queryset):
        hoje = datetime.datetime.now()
        return queryset.filter(data_conclusao_planejamento__isnull=True, edital__fim_inscricoes__gte=hoje)

    tab_em_edicao.short_description = 'Em Edição'

    def tab_enviados(self, request, queryset):
        return queryset.filter(
            Q(data_conclusao_planejamento__isnull=False) | Q(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=False)
        )

    tab_enviados.short_description = 'Enviados'

    def tab_nao_enviados(self, request, queryset):
        hoje = datetime.datetime.now()
        return queryset.filter(data_conclusao_planejamento__isnull=True, data_pre_avaliacao__isnull=True, edital__fim_inscricoes__lt=hoje)

    tab_nao_enviados.short_description = 'Não Enviados'

    def tab_cancelados(self, request, queryset):
        cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
        return queryset.filter(id__in=cancelados)

    tab_cancelados.short_description = 'Cancelados'

    def tab_inativados(self, request, queryset):
        return queryset.filter(inativado=True)

    tab_inativados.short_description = 'Inativados'

    def response_change(self, request, obj):
        self.message_user(request, 'Projeto alterado com sucesso.')
        return HttpResponseRedirect(f'/projetos_ensino/projeto/{obj.pk}/')

    def response_add(self, request, obj):
        self.message_user(request, 'Projeto cadastrado com sucesso.')
        return HttpResponseRedirect(f'/projetos_ensino/projeto/{obj.pk}/')

    def response_delete(self, request, obj_display, obj_id):
        self.message_user(request, 'Projeto excluído com sucesso.')
        return HttpResponseRedirect('/projetos_ensino/meus_projetos/')

    def add_view(self, request, form_url='', extra_context=None):
        raise PermissionDenied

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return HttpResponseRedirect(f'/projetos_ensino/editar_projeto/{object_id}/')

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)

        if (
            request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino', 'Gerente Sistêmico de Projetos de Ensino'])
            or request.user.is_superuser
        ):
            return qs

        elif request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']).exists():
            # return qs.filter(uo=get_uo(request.user))
            return qs.filter(uo__in=CampusAdicional.get_campi_user(request.user))

        elif request.user.groups.filter(name__in=['Avaliador de Projetos de Ensino']).exists():
            return qs.filter(uo=get_uo(request.user))

        elif request.user.groups.filter(name__in=['Servidor', 'Aposentado']).exists():
            participacoes = Participacao.objects.filter(responsavel=True, vinculo_pessoa=request.user.get_vinculo())
            ids = []
            for participacao in participacoes:
                ids.append(participacao.projeto.id)
            qs = Projeto.objects.filter(id__in=ids)
            return qs
        else:
            return qs.filter(id=0)

    def has_delete_permission(self, request, obj=None):
        return obj and obj.pode_remover_projeto()


admin.site.register(Projeto, ProjetoAdmin)


class AnoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'Ano'

    def lookups(self, request, model_admin):
        anos = []
        for data in Edital.objects.all().dates('inicio_inscricoes', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(inicio_inscricoes__year=self.value())


class EditalAdmin(ModelAdminPlus):
    form = EditalForm
    list_display = (
        'icones',
        'titulo',
        'descricao',
        'tipo_edital',
        'forma_selecao',
        'inicio_inscricoes',
        'fim_inscricoes',
        'get_percentual_executado',
    )
    ordering = ('titulo',)
    search_fields = (
        'descricao',
        'titulo',
    )
    list_filter = [
        CustomTabListFilter,
        AnoListFilter,
        'campus_especifico',
    ]

    fieldsets = (
        (
            'Dados gerais',
            {'fields': ('titulo', 'descricao', 'tipo_edital', 'forma_selecao', 'campus_especifico', 'qtd_projetos_selecionados', 'arquivo')},
        ),
        (
            'Calendário',
            {
                'fields': (
                    'inicio_inscricoes',
                    'fim_inscricoes',
                    'inicio_pre_selecao',
                    'inicio_selecao',
                    'fim_selecao',
                    'inicio_recurso',
                    'fim_recurso',
                    'divulgacao_selecao',
                )
            },
        ),
        (
            'Configurações do Edital',
            {
                'fields': (
                    'participa_aluno',
                    'participa_servidor',
                    'valor_financiado_por_projeto',
                    'exige_licoes_aprendidas',
                    'exige_avaliacao_aluno',
                    'permite_indicacao_tardia_equipe',
                    'aluno_pode_submeter',
                    'pode_escolher_campus_submissao',
                )
            },
        ),
        (
            'Termos de Compromisso',
            {
                'fields': (
                    'termo_compromisso_coordenador',
                    'termo_compromisso_servidor',
                    'termo_compromisso_aluno',
                    'termo_compromisso_colaborador_voluntario',
                )
            },
        ),
    )

    def icones(self, obj):
        return mark_safe(
            icon('view', f'/projetos_ensino/edital/{obj.id}/')
            + icon('edit', f'/admin/projetos_ensino/edital/{obj.id}/')
            + icon('delete', f'/admin/projetos_ensino/edital/{obj.id}/delete/')
        )

    icones.short_description = '-'

    def get_percentual_executado(self, obj):
        projetos_aprovados = Projeto.objects.filter(edital=obj, aprovado=True)
        total_projetos = projetos_aprovados.count()
        total_projetos_encerrados = projetos_aprovados.filter(data_finalizacao_conclusao__isnull=False).count()
        total = total_projetos
        if total == 0:
            total = 1
        percentual_html = f"""
                    {total_projetos_encerrados}/{total_projetos}
                    <div class="progress">
                        <p>{int(total_projetos_encerrados * 100 / total)}%%</p>
                    </div>
                    """
        return mark_safe(percentual_html)

    get_percentual_executado.short_description = 'Proporção de Projetos Encerrados'

    def response_change(self, request, obj):
        self.message_user(request, 'Edital alterado com sucesso.')
        return HttpResponseRedirect(f'/projetos_ensino/edital/{obj.pk}/')

    def response_add(self, request, obj):
        self.message_user(request, 'Edital cadastrado com sucesso.')
        return HttpResponseRedirect(f'/projetos_ensino/edital/{obj.pk}/')

    def get_tabs(self, request):
        return ['tab_abertos', 'tab_em_execucao', 'tab_encerrados']

    def tab_abertos(self, request, queryset):
        """
        Retorna os editais com resultados ainda não divulgados
        """
        hoje = datetime.datetime.now()
        return queryset.filter(divulgacao_selecao__gt=hoje)

    tab_abertos.short_description = 'Abertos'

    def tab_em_execucao(self, request, queryset):
        """
        Retorna os editais que existem ao menos um projeto não encerrado
        """
        editais_com_projetos_nao_encerrados = Projeto.objects.filter(data_finalizacao_conclusao__isnull=True, aprovado=True).values_list(
            'edital__id', flat=True
        )
        return queryset.filter(id__in=editais_com_projetos_nao_encerrados)

    tab_em_execucao.short_description = 'Em Execução'

    def tab_encerrados(self, request, queryset):
        """
        Retorna os editais em que todos os projetos estejam encerrados
        """
        editais_com_projetos_nao_encerrados = Projeto.objects.filter(data_finalizacao_conclusao__isnull=True, aprovado=True).values_list(
            'edital__id', flat=True
        )
        editais_com_projetos_encerrados = Projeto.objects.filter(data_finalizacao_conclusao__isnull=False, aprovado=True).values_list(
            'edital__id', flat=True
        )
        return queryset.filter(id__in=editais_com_projetos_encerrados).exclude(id__in=editais_com_projetos_nao_encerrados)

    tab_encerrados.short_description = 'Encerrados'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return qs
        else:
            return qs.filter(cadastrado_por__setor__uo=get_uo(request.user)) | qs.filter(
                id__in=OfertaProjeto.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True)
            )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.cadastrado_por = request.user.get_vinculo()
        return super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        hoje = datetime.datetime.now()
        return (
            obj
            and obj.fim_selecao
            and obj.fim_selecao > hoje
            and (
                request.user.has_perm('projetos_ensino.pode_gerenciar_edital')
                or (obj.cadastrado_por and obj.cadastrado_por == request.user.get_vinculo())
            )
        )


admin.site.register(Edital, EditalAdmin)


class EixoTematicoAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'descricao',
    )
    ordering = ('id',)


admin.site.register(EixoTematico, EixoTematicoAdmin)


class ParametroAdmin(ModelAdminPlus):
    list_display = (
        'grupo',
        'codigo',
        'descricao',
    )
    ordering = ('id',)


admin.site.register(Parametro, ParametroAdmin)


class TipoBeneficiarioAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'descricao',
    )
    ordering = ('id',)


admin.site.register(TipoBeneficiario, TipoBeneficiarioAdmin)


class AreaLicaoAprendidaAdmin(ModelAdminPlus):
    list_display = (
        'id',
        'descricao',
    )
    ordering = ('id',)


admin.site.register(AreaLicaoAprendida, AreaLicaoAprendidaAdmin)


class AnoComissaoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        anos = []

        for data in ComissaoEdital.objects.all().dates('edital__inicio_inscricoes', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__inicio_inscricoes__year=self.value())


class ComissaoEditalAdmin(ModelAdminPlus):
    list_display = ('edital', 'get_membros', 'get_lista_emails')
    list_filter = (AnoComissaoListFilter, EditalListFilter)
    list_display_icons = True
    ordering = ('id',)
    form = ComissaoEditalForm

    def get_membros(self, obj):
        return mark_safe(obj.get_membros())

    get_membros.short_description = 'Membros'

    def get_lista_emails(self, obj):
        return mark_safe(
            f"""<ul class="action-bar"><li><a href="/projetos_ensino/lista_emails_comissao/{obj.id}/" class="btn"> Lista de Emails dos Membros </a></li></ul>"""
        )

    get_lista_emails.short_description = 'Lista de Emails dos Membros'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return qs
        else:
            return qs.filter(edital__in=OfertaProjeto.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        return form


admin.site.register(ComissaoEdital, ComissaoEditalAdmin)


class CriterioAvaliacaoAlunoAdmin(ModelAdminPlus):
    list_display = (
        'nome',
        'ativo',
    )
    ordering = (
        'nome',
        'ativo',
    )


admin.site.register(CriterioAvaliacaoAluno, CriterioAvaliacaoAlunoAdmin)


class OrigemRecursoEditalAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'ativo')
    ordering = ('id',)


admin.site.register(OrigemRecursoEdital, OrigemRecursoEditalAdmin)


class HistoricoEquipeAdmin(ModelAdminPlus):
    title = 'Histórico da Equipe'
    list_display = ('projeto', 'participante', 'data_movimentacao', 'data_movimentacao_saida')
    form = EditarHistoricoEquipeForm

    def has_delete_permission(self, request, obj=None):
        return obj and obj.projeto.pode_remover_projeto()


admin.site.register(HistoricoEquipe, HistoricoEquipeAdmin)


class ComissaoAcompanhamentoAdmin(ModelAdminPlus):
    list_display = (
        'uo',
        'coordenador',
        'get_membros',
    )
    list_filter = ('uo',)
    list_display_icons = True
    ordering = ('id',)
    form = ComissaoAcompanhamentoForm

    def get_membros(self, obj):
        return mark_safe(obj.get_membros())

    get_membros.short_description = 'Membros'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['uo'].queryset = UnidadeOrganizacional.objects.uo()
        if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            uo_do_usuario = get_uo(request.user)
            form.base_fields['uo'].queryset = UnidadeOrganizacional.objects.uo().filter(id=uo_do_usuario.id)
            form.base_fields['uo'].initial = uo_do_usuario.id
            form.base_fields['coordenador'].queryset = Vinculo.objects.servidores().filter(ativo=True, setor__uo=uo_do_usuario)
            form.base_fields['membros'].queryset = Vinculo.objects.servidores().filter(ativo=True, setor__uo=uo_do_usuario)
        return form

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)
        if not request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return qs.filter(uo=get_uo(request.user))
        return qs


admin.site.register(ComissaoAcompanhamento, ComissaoAcompanhamentoAdmin)


class ColaboradorExternoAdmin(ModelAdminPlus):
    title = 'Colaboradores Externos'
    list_display = ('icones', 'nome', 'titulacao', 'instituicao_origem', 'email', 'get_documentacao')
    list_filter = ['titulacao', 'instituicao_origem']
    search_fields = [
        'nome',
        'prestador__matricula',
        'prestador__pessoa_fisica__cpf',
        'prestador__pessoa_fisica__passaporte',
    ]
    form = ColaboradorExternoForm

    fieldsets = (
        ('Dados Pessoais', {'fields': ('nome', 'nacionalidade', 'pais_origem', 'cpf', 'passaporte', 'email', 'telefone')}),
        ('Dados Profissionais', {'fields': ('instituicao_origem', 'titulacao', 'lattes')}),
        ('Outras Informações', {'fields': ('documentacao',)}),
    )

    def icones(self, obj):
        if self.request.user.has_perm('projetos.pode_avaliar_cancelamento_projeto'):
            icones = icon('view', f'/admin/projetos_ensino/colaboradorexterno/{obj.id}/') + icon(
                'edit', f'/admin/projetos_ensino/colaboradorexterno/{obj.id}/'
            )
            if not Participacao.objects.filter(vinculo_pessoa=obj.prestador.get_vinculo()).exists():
                icones += icon('delete', f'/admin/projetos_ensino/colaboradorexterno/{obj.id}/delete/')
            return mark_safe(icones)
        else:
            return '-'

    icones.short_description = 'Ações'

    def get_documentacao(self, obj):
        if obj.documentacao:
            return mark_safe(f'<a href="{obj.documentacao.url}" class="btn default">Ver Arquivo</a>')

    get_documentacao.short_description = 'Documentação'

    def has_delete_permission(self, request, obj=None):
        return obj and not Participacao.objects.filter(vinculo_pessoa=obj.prestador.get_vinculo()).exists()


admin.site.register(ColaboradorExterno, ColaboradorExternoAdmin)


class AvaliadorExternoAdmin(ModelAdminPlus):
    title = 'Avaliadores Externos'
    list_display = ('get_acoes', 'nome', 'titulacao', 'instituicao_origem', 'get_areas_conhecimento', 'email')
    list_filter = ['titulacao', 'instituicao_origem']
    form = AvaliadorExternoForm

    def get_acoes(self, obj):
        if self.request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            return mark_safe(
                icon('view', f'/admin/projetos_ensino/avaliadorexterno/{obj.id}/')
                + icon('edit', f'/admin/projetos_ensino/avaliadorexterno/{obj.id}/')
                + icon('delete', f'/admin/projetos_ensino/avaliadorexterno/{obj.id}/delete/')
            )
        else:
            return '-'

    get_acoes.short_description = 'Ações'

    def get_areas_conhecimento(self, obj):
        areas = []
        for area in obj.vinculo.relacionamento.areas_de_conhecimento.all():
            areas.append(area.descricao)
        return ', '.join(areas)

    get_areas_conhecimento.short_description = 'Áreas de Conhecimento'


admin.site.register(AvaliadorExterno, AvaliadorExternoAdmin)


class CampusAdicionalAdmin(ModelAdminPlus):
    list_display = ('usuario', 'get_uos')
    list_filter = ['usuario']
    list_display_icons = True
    form = CampusAdicionalForm
    ordering = ('usuario__vinculo__pessoa__pessoafisica__nome',)

    def get_uos(self, obj):
        uos = []
        for uo in obj.get_campi():
            uos.append(uo.sigla)
        return ', '.join(uos)

    get_uos.short_description = 'Campi'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Campi adicionais - Coordenador de Projetos de Ensino'

        CampusAdicional.sincronizar_campi_adicionais()
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(CampusAdicional, CampusAdicionalAdmin)
