import datetime
import html

from django.contrib import admin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from cnpq.models import Parametro
from comum.utils import get_uo
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import format_, in_group, status
from djtools.templatetags.tags import icon
from pesquisa.forms import (
    AvaliadorExternoForm,
    ColaboradorExternoForm,
    ComissaoEditalPesquisaForm,
    DoacaoEditoraForm,
    EditalForm,
    EditalSubmissaoObraForm,
    EditarHistoricoEquipeForm,
    IncubadoraForm,
    IntegranteEquipeTecnicaForm,
    LaboratorioPesquisaForm,
    PessoaExternaObraForm,
    ProgramaPosGraduacaoForm,
    RegistroPropriedadeIntelectualForm,
    TransferenciaTecnologicaForm,
)
from pesquisa.models import (
    AnuidadeRegistroPropriedadeIntelectual,
    AtividadeAutorizacaoSISBIO,
    AtividadeAutorizacaoSISGEN,
    AutoavaliacaoProgramaPos,
    Avaliacao,
    AvaliadorExterno,
    AvaliadorIndicado,
    BolsaDisponivel,
    CategoriaEventoIncubadora,
    CategoriaQuesito,
    ColaboradorExterno,
    ComissaoEditalPesquisa,
    CriterioAvaliacaoObra,
    CursoReconhecimentoDiploma,
    DoacaoEditora,
    Edital,
    EditalSubmissaoObra,
    EspecialidadeAssessor,
    FinalidadeServicoLaboratorio,
    FuncaoMembroParceria,
    HistoricoEquipe,
    Incubadora,
    IntegranteEquipeTecnica,
    ItemDoacaoEditora,
    LaboratorioPesquisa,
    LinhaEditorial,
    MaterialConsumoPesquisa,
    ModuloAssessoria,
    Obra,
    OrigemRecursoEdital,
    Parceria,
    ParecerObra,
    Participacao,
    PerguntaQuestionarioObra,
    PesoQuesitoArea,
    PessoaExternaObra,
    ProgramaPosGraduacao,
    Projeto,
    ProjetoCancelado,
    PropriedadeIntelectual,
    PublicacaoPropriedadeIntelectual,
    Quesito,
    QuesitoAutoavaliacao,
    ReconhecimentoDiploma,
    RegistroPropriedadeIntelectual,
    SituacaoParceria,
    TipoParceria,
    TipoQuestionarioObra,
    TipoTitularidadePI,
    TipoVinculo,
    TransferenciaTecnologica,
)
from rh.models import AreaConhecimento
from rh.utils import estah_no_pgd_hoje_pgd1_pgd2


class EditalListFilter(admin.SimpleListFilter):
    title = 'Edital'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        editais = Edital.objects.all().order_by('-inicio_inscricoes')
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


class GrandeAreaConhecimentoFilter(admin.SimpleListFilter):
    title = 'Grande Área'
    parameter_name = 'grande_area'

    def lookups(self, request, model_admin):
        areas = AreaConhecimento.objects.filter(superior__isnull=True)
        return areas.values_list('id', 'descricao')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(area_conhecimento__superior=self.value())


class AreaConhecimentoFilter(admin.SimpleListFilter):
    title = 'Área de Conhecimento'
    parameter_name = 'area_conhecimento'

    def lookups(self, request, model_admin):
        areas = AreaConhecimento.objects.order_by('descricao')
        grande_area = request.GET.get('grande_area')
        if grande_area:
            areas = areas.filter(superior=grande_area).order_by('descricao')
        return areas.values_list('id', 'descricao')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(area_conhecimento=self.value())


class AnoProjetoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        anos = Edital.objects.values_list('inicio_inscricoes__year', flat=True).distinct().order_by('-inicio_inscricoes__year')
        return [(ano, ano) for ano in anos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__inicio_inscricoes__year=self.value())


class PendenteValidacaoFilter(admin.SimpleListFilter):
    title = 'Pendente de validação (edital simplificado)'
    parameter_name = 'pendente_validacao'

    def lookups(self, request, model_admin):
        return [('Sim', 'Sim'), ('Não', 'Não')]

    def queryset(self, request, queryset):
        if self.value():
            projeto_simplificado_pendente_deferimento = Projeto.objects.filter(
                edital__formato=Edital.FORMATO_SIMPLIFICADO,
                data_conclusao_planejamento__isnull=False,
                data_pre_avaliacao__isnull=True,
                vinculo_supervisor__isnull=True,
            ).exclude(id__in=ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True))
            if self.value() == 'Sim':
                return queryset.filter(id__in=projeto_simplificado_pendente_deferimento.values_list('id', flat=True))
            elif self.value() == 'Não':
                return queryset.exclude(id__in=projeto_simplificado_pendente_deferimento.values_list('id', flat=True))


class ProjetoAdmin(ModelAdminPlus):
    title = 'Projetos'
    list_display = (
        'uo',
        'edital',
        'get_coordenador',
        'titulo',
        'get_situacao',
        'get_pre_aprovado',
        'get_aprovado',
        'get_pontuacao',
        'get_pontuacao_curriculo',
        'get_pontuacao_grupo_pesquisa',
        'get_pontuacao_total',
        'icone_imprimir',
    )
    ordering = ('-pontuacao_total', '-pontuacao')
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

    list_filter = (
        CustomTabListFilter,
        AnoProjetoListFilter,
        EditalListFilter,
        'uo',
        GrandeAreaConhecimentoFilter,
        AreaConhecimentoFilter,
        'classificacao_trl',
        'objetivos_desenvolvimento_sustentavel',
        'subobjetivos_desenvolvimento_sustentavel',
        PendenteValidacaoFilter,
    )
    list_per_page = 20
    list_display_icons = True
    show_count_on_tabs = True

    def to_xls(self, request, queryset, processo):
        header = [
            '#',
            'ID',
            'Título',
            'Resumo do Projeto',
            'Edital',
            'Ano do Edital',
            'Coordenador',
            'Área de Conhecimento',
            'TRL',
            'Grupo de Pesquisa',
            'Campus',
            'Período de Execução',
            'Situação Atual',
            'Pré-selecionado',
            'Selecionado',
        ]
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            coordenador = obj.vinculo_coordenador.pessoa.nome
            periodo = 'De {} a {}'.format(obj.inicio_execucao.strftime('%d/%m/%Y'), obj.fim_execucao.strftime('%d/%m/%Y'))
            row = [
                idx + 1,
                obj.id,
                obj.titulo,
                strip_tags(html.unescape(obj.resumo)),
                obj.edital.titulo,
                obj.edital.inicio_inscricoes.year,
                coordenador,
                obj.area_conhecimento,
                obj.classificacao_trl,
                obj.grupo_pesquisa,
                obj.uo,
                periodo,
                obj.get_status(),
                obj.get_pre_selecionado(html=False, user=request.user),
                obj.get_selecionado(html=False, user=request.user),
            ]
            rows.append(row)
        return rows

    def has_add_permission(self, request):
        return False

    def get_pontuacao(self, obj):
        return obj.pontuacao

    get_pontuacao.short_description = 'Pontuação da Avaliação'

    def get_pontuacao_curriculo(self, obj):
        pontuacao_normalizada = obj.pontuacao_curriculo_normalizado or '0.00'
        return f'{pontuacao_normalizada} ({obj.pontuacao_curriculo})'

    get_pontuacao_curriculo.short_description = 'Pontuação do Currículo'

    def get_pontuacao_grupo_pesquisa(self, obj):
        pontuacao_normalizada = obj.pontuacao_grupo_pesquisa_normalizado or '0.00'
        return f'{pontuacao_normalizada} ({obj.pontuacao_grupo_pesquisa})'

    get_pontuacao_grupo_pesquisa.short_description = 'Pontuação do Grupo de Pesquisa'

    def get_pontuacao_total(self, obj):
        return obj.pontuacao_total

    get_pontuacao_total.short_description = 'Pontuação Total'

    def get_coordenador(self, obj):
        participacao = obj.participacao_set.get(responsavel=True)
        if participacao.vinculo == TipoVinculo.BOLSISTA and participacao.bolsa_concedida is True:
            retorno = f'<p>{participacao.get_nome()}</p><p><strong>Bolsista</strong></p>'
        else:
            retorno = participacao.vinculo_pessoa.pessoa.nome
        return mark_safe(retorno)

    get_coordenador.short_description = 'Coordenador'

    def get_pre_aprovado(self, obj):
        return mark_safe(obj.get_pre_selecionado())

    get_pre_aprovado.short_description = 'Pré-selecionado'

    def get_aprovado(self, obj):
        return mark_safe(obj.get_selecionado())

    get_aprovado.short_description = 'Selecionado'

    def get_situacao(self, obj):
        if obj.get_status() == Projeto.STATUS_EM_INSCRICAO:
            retorno = f'<span class="status status-error">{obj.get_status()}</span>'
        elif obj.get_status() == Projeto.STATUS_NAO_ENVIADO:
            retorno = f'<span class="status status-alert">{obj.get_status()}</span>'
        else:
            retorno = status(obj.get_status())
        return mark_safe(retorno)

    get_situacao.short_description = 'Situação Atual'

    def icone_imprimir(self, obj):
        return mark_safe(f'<a href="/pesquisa/imprimir_projeto/{obj.id}/" class="btn">Imprimir</a>')

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
        if request.user.has_group_cached('Diretor de Pesquisa'):
            return queryset.filter(aprovado=True).exclude(projetocancelado__cancelado=True, projetocancelado__data_avaliacao__isnull=False)
        else:
            return queryset.filter(aprovado=True, edital__divulgacao_selecao__lt=hoje).exclude(
                projetocancelado__cancelado=True, data_avaliacao__isnull=False
            )

    tab_selecionados.short_description = 'Selecionados'

    def tab_nao_selecionados(self, request, queryset):
        hoje = datetime.datetime.now()
        if request.user.has_group_cached('Diretor de Pesquisa'):
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
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
        return queryset.filter(pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False).exclude(
            id__in=projetos_cancelados
        )

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
        return queryset.filter(projetocancelado__cancelado=True, projetocancelado__data_avaliacao__isnull=False).distinct()

    tab_cancelados.short_description = 'Cancelados'

    def tab_inativados(self, request, queryset):
        return queryset.filter(inativado=True)

    tab_inativados.short_description = 'Inativados'

    def response_change(self, request, obj):
        self.message_user(request, 'Projeto alterado com sucesso.')
        return HttpResponseRedirect(f'/pesquisa/projeto/{obj.pk}/')

    def response_add(self, request, obj):
        self.message_user(request, 'Projeto cadastrado com sucesso.')
        return HttpResponseRedirect(f'/pesquisa/projeto/{obj.pk}/')

    def add_view(self, request, form_url='', extra_context=None):
        raise PermissionDenied

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return HttpResponseRedirect(f'/pesquisa/editar_projeto/{object_id}/')

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)

        if request.user.has_perm('pesquisa.add_origemrecursoedital') or request.user.has_perm('pesquisa.pode_ver_config_edital'):
            return qs

        elif request.user.has_group_cached('Coordenador de Pesquisa') or request.user.has_perm('pesquisa.pode_acessar_lista_projetos'):
            return qs.filter(uo=get_uo(request.user))

        elif request.user.has_group_cached(['Servidor', 'Aposentado']):
            participacoes = Participacao.objects.filter(responsavel=True, vinculo_pessoa=request.user.get_vinculo())
            ids = []
            for participacao in participacoes:
                ids.append(participacao.projeto.id)
            qs = Projeto.objects.filter(id__in=ids)
            return qs
        else:
            return qs

    def has_delete_permission(self, request, obj=None):
        return obj and obj.pode_remover_projeto()


admin.site.register(Projeto, ProjetoAdmin)


class AnoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'Ano'

    def lookups(self, request, model_admin):
        anos = Edital.objects.values_list('inicio_inscricoes__year', flat=True).distinct().order_by('-inicio_inscricoes__year')
        return [(ano, ano) for ano in anos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(inicio_inscricoes__year=self.value())


class EditalAdmin(ModelAdminPlus):
    form = EditalForm
    list_display = (
        'get_acoes',
        'titulo',
        'descricao',
        'tipo_edital',
        'formato',
        'forma_selecao',
        'tipo_monitoramento',
        'inicio_inscricoes',
        'fim_inscricoes',
        'get_percentual_executado',
        'get_opcoes',
    )
    ordering = ('-inicio_inscricoes',)
    search_fields = ('descricao', 'titulo')
    list_filter = [
        CustomTabListFilter,
        AnoListFilter,
        'tipo_edital',
        'formato',
        'tipo_monitoramento',
    ]
    exclude = ['arquivo']

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'titulo',
                    'descricao',
                    'tipo_edital',
                    'formato',
                    'forma_selecao',
                    'tipo_monitoramento',
                    'campus_especifico',
                    'qtd_bolsa_alunos',
                    'qtd_bolsa_servidores',
                )
            },
        ),
        (
            'Calendário',
            {
                'fields': (
                    'inicio_inscricoes',
                    'fim_inscricoes',
                    'inicio_pre_selecao',
                    'fim_pre_selecao',
                    'data_recurso_pre_selecao',
                    'inicio_selecao',
                    'fim_selecao',
                    'data_recurso',
                    'data_avaliacao_recurso',
                    'divulgacao_selecao',
                )
            },
        ),
        (
            'Configurações do Edital',
            {
                'fields': (
                    'coordenador_pode_receber_bolsa',
                    'permite_coordenador_com_bolsa_previa',
                    'exige_grupo_pesquisa',
                    'lattes_obrigatorio',
                    'titulacoes_avaliador',
                    'participa_aluno',
                    'participa_servidor',
                    'permite_colaborador_externo',
                    'aluno_pos_pode_submeter',
                    'colaborador_externo_pode_submeter',
                    'imprimir_certificado',
                    'qtd_anos_anteriores_publicacao',
                    'peso_avaliacao_lattes_coordenador',
                    'peso_avaliacao_projeto',
                    'peso_avaliacao_grupo_pesquisa',
                    'nota_corte_projeto_fluxo_continuo',
                    'exige_anuencia',
                    'ch_semanal_coordenador',
                    'tempo_maximo_meses_curriculo_desatualizado',
                    'impedir_projeto_sem_anexo',
                    'atividade_todo_mes',
                    'prazo_atividade',
                    'discente_proprio_campus',
                    'impedir_coordenador_com_pendencia',
                    'exige_comissao',
                    'prazo_aceite_indicacao',
                    'prazo_avaliacao',
                    'pontuacao_diferenciada_maternidade',
                    'responsavel_pode_registrar_execucao',
                    'permite_uso_cartao_pesquisador',
                    'utiliza_metodologia_trl',
                    'pode_escolher_campus_submissao',
                    'exigir_participacao_como_avaliador',
                    'anos_avaliacoes_considerar',
                    'quantidade_avaliacoes',
                    'impedir_submissao_de_avaliador',
                    'permitir_finalizar_sem_validacao_desembolsos',
                    'submeter_pelo_campus_exercicio',
                    'permite_indicacao_tardia_equipe',
                    'permite_enviar_um_projeto',
                    'permite_afastado_submeter',
                    'ignorar_termo_pendente',
                    'avaliador_ve_anexos',
                    'exibir_aba_calculo_pontuacao',
                    'publicado',
                    'aviso_aos_avaliadores',
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
                    'termo_compromisso_colaborador_externo',
                    'termo_compromisso_colaborador_externo_en',
                    'termo_compromisso_colaborador_externo_es',
                    'termo_compromisso_colaborador_externo_fr',
                )
            },
        ),
        (
            'Quantidade de Participantes',
            {'fields': ('qtd_maxima_servidores', 'qtd_maxima_servidores_bolsistas', 'qtd_maxima_alunos', 'qtd_maxima_alunos_bolsistas')},
        ),
    )

    def get_acoes(self, obj):
        texto = icon('view', f'/pesquisa/edital/{obj.id}/')
        if self.request.user.has_perm('pesquisa.change_edital'):
            texto = texto + icon('edit', f'/admin/pesquisa/edital/{obj.id}/') + icon('delete', f'/admin/pesquisa/edital/{obj.id}/delete/')
        return mark_safe(texto)

    get_acoes.short_description = 'Ações'

    def get_opcoes(self, obj):
        retorno = '<ul class="action-bar">'
        if self.request.user.has_perm('pesquisa.add_edital'):
            retorno += f'<li><a href="/pesquisa/clonar_edital/{obj.id}/" class="btn primary">Clonar Edital</a></li>'
        if self.request.user.has_perm('pesquisa.tem_acesso_sistemico') and obj.autorizado is None:
            retorno += f"""
                    <li><a href="/pesquisa/autorizar_edital/{obj.id}/1/" class="btn success confirm">Autorizar</a></li>
                    <li><a href="/pesquisa/autorizar_edital/{obj.id}/2/" class="btn danger confirm">Rejeitar</a></li>
               """
        if obj.is_periodo_divulgacao():
            if Projeto.objects.filter(pre_aprovado=True, aprovado=False, edital=obj).exclude(data_avaliacao=None).exists():
                retorno += (
                    f'<li><a href="/pesquisa/projetos_lista_espera/{obj.id}/" class="btn success">Autorizar execução de novos projetos</a></li>'
                )
            if (
                Projeto.objects.filter(pre_aprovado=True, aprovado=False, edital=obj, autorizada_sem_fomento_em=None)
                .exclude(data_avaliacao=None)
                .exists()
            ):
                retorno += (
                    f'<li><a href="/pesquisa/aprovar_projetos_sem_fomento/{obj.id}/" class="btn primary">Aprovar novos projetos sem fomento</a></li>'
                )
        retorno += '</ul>'
        return mark_safe(retorno)

    get_opcoes.short_description = 'Opções'

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
                        <p>{int(total_projetos_encerrados * 100 / total)}%</p>
                    </div>
                    """
        return mark_safe(percentual_html)

    get_percentual_executado.short_description = 'Proporção de Projetos Encerrados'

    def response_change(self, request, obj):
        self.message_user(request, 'Edital alterado com sucesso.')
        return HttpResponseRedirect(f'/pesquisa/edital/{obj.pk}/')

    def response_add(self, request, obj):
        self.message_user(request, 'Edital cadastrado com sucesso.')
        return HttpResponseRedirect(f'/pesquisa/edital/{obj.pk}/')

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'tipo_edital':
            kwargs['choices'] = Edital.TIPO_EDITAL_PESQUISA

        if db_field.name == 'forma_selecao':
            kwargs['choices'] = Edital.TIPO_FORMA_SELECAO_CHOICES
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        self.exclude = ['inclusao_bolsas_ae', 'arquivo', 'exige_licoes_aprendidas', 'valor_financiado_por_projeto', 'data_avaliacao_classificacao']
        return super().get_form(request, obj, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_group_cached('Diretor de Pesquisa'):
            return qs
        elif request.user.has_group_cached('Coordenador de Pesquisa'):
            return qs.filter(cadastrado_por_vinculo__setor__uo=get_uo(request.user)) | qs.filter(
                autorizado_em__isnull=False, id__in=BolsaDisponivel.objects.filter(uo=get_uo(request.user)).values_list('edital', flat=True)
            )
        return qs

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
        # editais_com_projetos_nao_encerrados = Projeto.objects.filter(data_finalizacao_conclusao__isnull=True, aprovado=True).values_list('edital__id', flat=True)
        return queryset.filter(projeto__data_finalizacao_conclusao__isnull=True, projeto__aprovado=True)

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

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.cadastrado_por_vinculo = request.user.get_vinculo()
            obj.cadastrado_em = datetime.datetime.now()
            if request.user.has_group_cached('Coordenador de Pesquisa'):
                obj.autorizado = None
        return super().save_model(request, obj, form, change)


admin.site.register(Edital, EditalAdmin)


class ParametroAdmin(ModelAdminPlus):
    list_display = ('grupo', 'codigo', 'descricao')
    ordering = ('id',)


admin.site.register(Parametro, ParametroAdmin)


class AnoComissaoListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        anos = (
            ComissaoEditalPesquisa.objects.values_list('edital__inicio_inscricoes__year', flat=True)
            .distinct()
            .order_by('-edital__inicio_inscricoes__year')
        )
        return [(ano, ano) for ano in anos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__inicio_inscricoes__year=self.value())


class ComissaoEditalPesquisaAdmin(ModelAdminPlus):
    list_display = ('edital', 'get_uo', 'get_membros', 'get_lista_emails', 'get_adiciona_membros')
    list_display_icons = True
    list_filter = (AnoComissaoListFilter, EditalListFilter, 'uo')
    ordering = ('id',)
    form = ComissaoEditalPesquisaForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_group_cached('Diretor de Pesquisa'):
            return qs
        elif request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Pesquisa') and not request.user.has_group_cached(
            'Coordenador de Pesquisa'
        ):
            return qs.filter(edital__forma_selecao=Edital.GERAL)
        elif request.user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Pesquisa') and request.user.has_group_cached(
            'Coordenador de Pesquisa'
        ):
            return qs.filter(Q(edital__forma_selecao=Edital.GERAL) | Q(uo=get_uo(request.user)))
        else:
            return qs.filter(uo=get_uo(request.user))

    def get_uo(self, obj):
        if obj.uo:
            return mark_safe(obj.uo)
        else:
            return 'Geral'

    get_uo.short_description = 'Campus / Geral'

    def get_membros(self, obj):
        return mark_safe(
            f"""<ul class="action-bar"><li><a class="btn popup" href="/pesquisa/ver_membros_comissao/{obj.id}/">Ver Membros</a></li></ul>"""
        )

    get_membros.short_description = 'Membros'

    def get_lista_emails(self, obj):
        return mark_safe(
            f"""<ul class="action-bar"><li><a class="btn" href="/pesquisa/lista_emails_comissao/{obj.id}/">Lista de Emails dos Membros</a></li></ul>"""
        )

    get_lista_emails.short_description = 'Lista de Emails dos Membros'

    def get_adiciona_membros(self, obj):
        return mark_safe(
            f"""<ul class="action-bar"><li><a href="/pesquisa/adicionar_comissao_por_area/{obj.id}/" class="btn success"> Adicionar Membros por Área de Conhecimento</a></li></ul>"""
        )

    get_adiciona_membros.short_description = 'Opções'

    def get_action_bar(self, request):
        items = super().get_action_bar(request, remove_add_button=True)

        items.append(
            {
                'label': 'Adicionar Comissão de Avaliação',
                'css_class': 'success',
                'subitems': [
                    {'url': '/admin/pesquisa/comissaoeditalpesquisa/add/', 'label': 'Por Indicação de Nomes'},
                    {'url': '/pesquisa/adicionar_comissao/', 'label': 'Por Área de Conhecimento'},
                ],
            }
        )

        return items


admin.site.register(ComissaoEditalPesquisa, ComissaoEditalPesquisaAdmin)


class AvaliadorExternoAdmin(ModelAdminPlus):
    title = 'Avaliadores Externos'
    list_display = ('get_acoes', 'nome', 'titulacao', 'instituicao_origem', 'get_areas_conhecimento', 'email', 'get_indicacoes')
    list_filter = ['titulacao', 'instituicao_origem']
    form = AvaliadorExternoForm
    search_fields = ('nome',)

    def get_acoes(self, obj):
        if self.request.user.has_group_cached('Diretor de Pesquisa'):
            return mark_safe(
                icon('view', f'/admin/pesquisa/avaliadorexterno/{obj.id}/')
                + icon('edit', f'/admin/pesquisa/avaliadorexterno/{obj.id}/')
                + icon('delete', f'/admin/pesquisa/avaliadorexterno/{obj.id}/delete/')
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

    def get_indicacoes(self, obj):
        vinculo_avaliador = obj.vinculo
        return f'{AvaliadorIndicado.objects.filter(vinculo=vinculo_avaliador).count()} indicações, {Avaliacao.objects.filter(vinculo=vinculo_avaliador).count()} avaliações realizadas'

    get_indicacoes.short_description = 'Indicações'


admin.site.register(AvaliadorExterno, AvaliadorExternoAdmin)


class LinhaEditorialAdmin(ModelAdminPlus):
    list_display = ('nome', 'tipo_questionario', 'ativa')
    ordering = ('id',)
    list_filter = ('ativa',)
    list_display_icons = True


admin.site.register(LinhaEditorial, LinhaEditorialAdmin)


class EditalSubmissaoObraAdmin(ModelAdminPlus):
    form = EditalSubmissaoObraForm
    list_display = ('titulo', 'data_inicio_submissao', 'data_termino_submissao', 'get_linha_editorial', 'get_arquivo', 'get_manual', 'get_ficha')
    ordering = ('-data_inicio_submissao',)
    list_display_icons = True
    search_fields = ('titulo',)
    list_filter = ('tipo',)

    fieldsets = (
        ('Dados gerais', {'fields': ('titulo', 'tipo', 'linha_editorial', 'arquivo')}),
        (
            'Etapas',
            {
                'fields': (
                    ('data_inicio_submissao', 'data_termino_submissao'),
                    ('data_inicio_verificacao_plagio', 'data_termino_verificacao_plagio'),
                    ('data_inicio_analise_especialista', 'data_termino_analise_especialista'),
                    ('data_inicio_validacao_conselho', 'data_termino_validacao_conselho'),
                    ('data_inicio_aceite', 'data_termino_aceite'),
                    ('data_inicio_termos', 'data_termino_termos'),
                    ('data_inicio_revisao_linguistica', 'data_termino_revisao_linguistica'),
                    ('data_inicio_diagramacao', 'data_termino_diagramacao'),
                    ('data_inicio_solicitacao_isbn', 'data_termino_solicitacao_isbn'),
                    ('data_inicio_impressao_boneco', 'data_termino_impressao_boneco'),
                    ('data_revisao_layout'),
                    ('data_inicio_correcao_final', 'data_termino_correcao_final'),
                    ('data_inicio_analise_liberacao', 'data_termino_analise_liberacao'),
                    ('data_inicio_impressao', 'data_termino_impressao'),
                    'data_lancamento',
                    'local_lancamento',
                    'observacoes_lancamento',
                )
            },
        ),
        ('Arquivos e Informações', {'fields': ('instrucoes', 'manual', 'questionario_parecerista')}),
    )

    def get_arquivo(self, obj):
        return mark_safe(f'<a href="{obj.arquivo.url}" class="btn default">Ver Arquivo</a>')

    get_arquivo.short_description = 'Edital'

    def get_manual(self, obj):
        if obj.manual:
            return mark_safe(f'<a href="{obj.manual.url}" class="btn default">Ver Arquivo</a>')
        return '-'

    get_manual.short_description = 'Manual do Autor'

    def get_ficha(self, obj):
        if obj.questionario_parecerista:
            return mark_safe(f'<a href="{obj.questionario_parecerista.url}" class="btn default">Ver Arquivo</a>')
        return '-'

    get_ficha.short_description = 'Ficha de Avaliação'

    def get_linha_editorial(self, obj):
        linhas = []
        for linha in obj.linha_editorial.all():
            linhas.append(linha.nome)
        return ', '.join(linhas)

    get_linha_editorial.short_description = 'Linhas Editoriais'


admin.site.register(EditalSubmissaoObra, EditalSubmissaoObraAdmin)


class AnoObraListFilter(admin.SimpleListFilter):
    title = 'Ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        anos = []

        for data in EditalSubmissaoObra.objects.all().dates('data_inicio_submissao', 'year'):
            anos.append((data.year, data.year))
        anos.reverse()
        return anos

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(edital__data_inicio_submissao__year=self.value())


class EditalObraListFilter(admin.SimpleListFilter):
    title = 'Edital'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        editais = EditalSubmissaoObra.objects.order_by('-data_inicio_submissao')
        ano = request.GET.get('ano')
        if ano:
            editais = editais.filter(data_inicio_submissao__year=ano)
        return editais.values_list('id', 'titulo')

    def queryset(self, request, queryset):
        if self.value():
            obras = queryset.filter(edital__pk=request.GET.get(self.parameter_name))
            if 'ano' in request.GET:
                edital = EditalSubmissaoObra.objects.get(id=request.GET.get(self.parameter_name))
                if obras.filter(edital__data_inicio_submissao__year=request.GET.get('ano')).exists():
                    return obras.filter(edital__data_inicio_submissao__year=request.GET.get('ano'))

                elif edital.data_inicio_submissao.year != int(request.GET.get('ano')):
                    return queryset.filter(edital__data_inicio_submissao__year=request.GET.get('ano'))
                else:
                    return obras

            return obras

        return queryset


class ObraAdmin(ModelAdminPlus):
    list_display = ('get_acoes', 'titulo', 'edital', 'area', 'get_submetido_por', 'submetido_em')
    ordering = ('id',)
    list_display_links = None
    search_fields = ('titulo',)
    list_filter = (CustomTabListFilter, 'edital__linha_editorial', AnoObraListFilter, EditalObraListFilter, 'area')
    show_count_on_tabs = True

    def has_add_permission(self, request):
        return False

    def get_acoes(self, obj):
        return icon('view', f'/pesquisa/obra/{obj.id}/')

    get_acoes.short_description = 'Ações'

    def get_submetido_por(self, obj):
        if (
            self.request.user.has_perm('pesquisa.pode_validar_obra')
            or self.request.user.has_perm('pesquisa.pode_avaliar_obra')
            or not obj.submetido_por_vinculo
        ):
            return '-'
        return obj.submetido_por_vinculo.pessoa.nome

    get_submetido_por.short_description = 'Submetido por'

    def get_queryset(self, request, *args, **kwargs):
        qs = super().get_queryset(request, *args, **kwargs)

        if request.user.has_group_cached(['Integrante da Editora', 'Conselheiro Editorial']):
            return qs

        elif request.user.has_group_cached('Parecerista de Obra'):
            pareceres = ParecerObra.objects.filter(parecer_realizado_por_vinculo=request.user.get_vinculo())
            return qs.filter(id__in=pareceres.values_list('obra', flat=True))

        elif request.user.has_group_cached('Revisor de Obra'):
            return qs.filter(revisao_realizada_por_vinculo=request.user.get_vinculo())

        return qs

    def get_tabs(self, request):
        return [
            'tab_submetidas',
            'tab_autenticas',
            'tab_aceitas',
            'tab_aprovadas',
            'tab_validadas',
            'tab_revisadas',
            'tab_diagramadas',
            'tab_corrigidas',
            'tab_isbn',
            'tab_catalogadas',
            'tab_liberadas',
            'tab_concluidas',
            'tab_canceladas',
        ]

    def tab_submetidas(self, request, queryset):
        return queryset.filter(situacao=Obra.SUBMETIDA)

    tab_submetidas.short_description = 'Submetidas'

    def tab_autenticas(self, request, queryset):
        return queryset.filter(situacao=Obra.AUTENTICA)

    tab_autenticas.short_description = 'Autênticas'

    def tab_aceitas(self, request, queryset):
        return queryset.filter(situacao=Obra.ACEITA)

    tab_aceitas.short_description = 'Aceitas'

    def tab_aprovadas(self, request, queryset):
        return queryset.filter(situacao=Obra.CLASSIFICADA)

    tab_aprovadas.short_description = 'Classificadas'

    def tab_validadas(self, request, queryset):
        return queryset.filter(situacao=Obra.VALIDADA)

    tab_validadas.short_description = 'Validadas'

    def tab_revisadas(self, request, queryset):
        return queryset.filter(situacao=Obra.REVISADA)

    tab_revisadas.short_description = 'Revisadas'

    def tab_diagramadas(self, request, queryset):
        return queryset.filter(situacao=Obra.DIAGRAMADA)

    tab_diagramadas.short_description = 'Diagramadas'

    def tab_corrigidas(self, request, queryset):
        return queryset.filter(situacao=Obra.CORRIGIDA)

    tab_corrigidas.short_description = 'Corrigidas'

    def tab_isbn(self, request, queryset):
        return queryset.filter(situacao=Obra.REGISTRADA_ISBN)

    tab_isbn.short_description = 'ISBN Cadastrado'

    def tab_catalogadas(self, request, queryset):
        return queryset.filter(situacao=Obra.CATALOGADA)

    tab_catalogadas.short_description = 'Catalogadas'

    def tab_liberadas(self, request, queryset):
        return queryset.filter(situacao=Obra.LIBERADA)

    tab_liberadas.short_description = 'Liberadas'

    def tab_concluidas(self, request, queryset):
        return queryset.filter(situacao=Obra.CONCLUIDA)

    tab_concluidas.short_description = 'Concluídas'

    def tab_canceladas(self, request, queryset):
        return queryset.filter(situacao=Obra.CANCELADA)

    tab_canceladas.short_description = 'Canceladas'


admin.site.register(Obra, ObraAdmin)


class PessoaExternaObraAdmin(ModelAdminPlus):
    title = 'Pessoas Externas'
    list_display = ('get_acoes', 'nome', 'email', 'telefone', 'get_opcoes')
    list_filter = [
        CustomTabListFilter,
    ]
    search_fields = ('nome', 'email')
    form = PessoaExternaObraForm
    ordering = ['nome']
    show_count_on_tabs = True

    def get_acoes(self, obj):
        if self.request.user.has_perm('pesquisa.add_pessoaexternaobra'):
            return mark_safe(
                icon('view', f'/pesquisa/ver_pessoa_externa/{obj.id}/')
                + icon('edit', f'/admin/pesquisa/pessoaexternaobra/{obj.id}/')
                + icon('delete', f'/admin/pesquisa/pessoaexternaobra/{obj.id}/delete/')
            )
        else:
            return '-'

    get_acoes.short_description = 'Ações'

    def get_opcoes(self, obj):
        opcoes = ''
        if obj.ativo is False and not obj.validado_em:
            opcoes += '<ul class="action-bar">'
            if obj.pessoa_fisica.email_pessoal:
                opcoes += f'<li><a href="/pesquisa/validar_parecerista/{obj.id}/1/" class="btn success confirm" data-confirm="Você tem certeza que deseja validar este cadastro?">Autorizar</a></li>'
            opcoes += f'<li><a href="/pesquisa/validar_parecerista/{obj.id}/2/" class="btn danger confirm" data-confirm="Você tem certeza que deseja rejeitar este cadastro?">Rejeitar</a></li>'
            opcoes += '</ul>'
        return mark_safe(opcoes)

    get_opcoes.short_description = 'Opções'

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_inativos']

    def tab_pendentes(self, request, queryset):
        return queryset.filter(ativo=False, validado_em__isnull=True)

    tab_pendentes.short_description = 'Pendentes de Validação'

    def tab_inativos(self, request, queryset):
        return queryset.filter(ativo=False)

    tab_inativos.short_description = 'Inativos'

    def get_form(self, request, obj=None, **kwargs):
        FormClass = super(ModelAdminPlus, self).get_form(request, obj, **kwargs)
        FormClass.request = request
        return FormClass


admin.site.register(PessoaExternaObra, PessoaExternaObraAdmin)


class LaboratorioPesquisaAdmin(ModelAdminPlus):
    title = 'Laboratórios Multiusuários'
    list_display = ('get_acoes', 'nome', 'coordenador', 'contato')
    list_filter = [CustomTabListFilter, 'uo', 'area_pesquisa']
    search_fields = ('nome', 'coordenador__pessoa_fisica__search_fields_optimized', 'coordenador__matricula')
    form = LaboratorioPesquisaForm

    def get_tabs(self, request):
        if not request.user.eh_aluno:
            return ['tab_meus_laboratorios', 'tab_aguardando_avaliacao']
        return []

    def tab_meus_laboratorios(self, request, queryset):
        relacionamento = request.user.get_relacionamento()
        return queryset.filter(coordenador__matricula=relacionamento.matricula)

    tab_meus_laboratorios.short_description = 'Meus Laboratórios'

    def tab_aguardando_avaliacao(self, request, queryset):
        if request.user.has_group_cached('Diretor de Pesquisa', ignore_groups_if_superuser=False):
            return queryset.filter(aprovado=None)

    tab_aguardando_avaliacao.short_description = 'Aguardando Avaliação'

    def get_acoes(self, obj):
        eh_sistemico = self.request.user.has_perm('pesquisa.add_origemrecursoedital')
        texto = icon('view', f'/pesquisa/laboratorio_pesquisa/{obj.id}/')
        if eh_sistemico or self.request.user.get_relacionamento() == obj.coordenador:
            texto = texto + icon('edit', f'/admin/pesquisa/laboratoriopesquisa/{obj.id}/')

        if eh_sistemico:
            texto = texto + icon('delete', f'/admin/pesquisa/laboratoriopesquisa/{obj.id}/delete/')
        return mark_safe(texto)

    get_acoes.short_description = 'Ações'

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('pesquisa.add_origemrecursoedital') and request.user.get_relacionamento() != obj.coordenador:
                retorno = False
        return retorno


admin.site.register(LaboratorioPesquisa, LaboratorioPesquisaAdmin)


class HistoricoEquipeAdmin(ModelAdminPlus):
    title = 'Histórico da Equipe'
    list_display = ('projeto', 'participante', 'data_movimentacao', 'data_movimentacao_saida')
    form = EditarHistoricoEquipeForm


admin.site.register(HistoricoEquipe, HistoricoEquipeAdmin)


class OrigemRecursoEditalAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'ativo')
    ordering = ('id',)


admin.site.register(OrigemRecursoEdital, OrigemRecursoEditalAdmin)


class MaterialConsumoPesquisaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ['ativo']
    search_fields = ('descricao',)


admin.site.register(MaterialConsumoPesquisa, MaterialConsumoPesquisaAdmin)


class FinalidadeServicoLaboratorioAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ['ativo']
    search_fields = ('descricao',)


admin.site.register(FinalidadeServicoLaboratorio, FinalidadeServicoLaboratorioAdmin)


class ColaboradorExternoAdmin(ModelAdminPlus):
    title = 'Colaboradores Externos'
    list_display = ('get_acoes', 'nome', 'titulacao', 'instituicao_origem', 'email', 'get_documentacao')
    list_filter = ['titulacao', 'instituicao_origem', 'prestador__pessoa_fisica__nacionalidade', 'prestador__pessoa_fisica__pais_origem']
    form = ColaboradorExternoForm
    search_fields = [
        'nome',
        'prestador__matricula',
        'prestador__pessoa_fisica__cpf',
        'prestador__pessoa_fisica__passaporte',
    ]
    fieldsets = (
        ('Dados Pessoais', {'fields': ('nome', 'nacionalidade', 'pais_origem', 'cpf', 'passaporte', 'email', 'telefone')}),
        ('Dados Profissionais', {'fields': ('instituicao_origem', 'titulacao', 'lattes')}),
        ('Outras Informações', {'fields': ('documentacao',)}),
    )

    def get_acoes(self, obj):
        if self.request.user.has_perm('pesquisa.add_colaboradorexterno'):
            icones = icon('view', f'/admin/pesquisa/colaboradorexterno/{obj.id}/') + icon('edit', f'/admin/pesquisa/colaboradorexterno/{obj.id}/')
            if not Participacao.objects.filter(vinculo_pessoa=obj.prestador.get_vinculo()).exists():
                icones += icon('delete', f'/admin/pesquisa/colaboradorexterno/{obj.id}/delete/')
            return mark_safe(icones)
        else:
            return '-'

    get_acoes.short_description = 'Ações'

    def get_documentacao(self, obj):
        if obj.documentacao:
            return mark_safe(f'<a href="{obj.documentacao.url}" class="btn default">Ver Arquivo</a>')
        return '-'

    get_documentacao.short_description = 'Documentação'

    def has_delete_permission(self, request, obj=None):
        return obj and not Participacao.objects.filter(vinculo_pessoa=obj.prestador.get_vinculo()).exists()


admin.site.register(ColaboradorExterno, ColaboradorExternoAdmin)


class ProgramaPosGraduacaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo_capes', 'coordenador', 'modalidade', 'campus_sede', 'ativo')
    ordering = ('id',)
    list_filter = (
        CustomTabListFilter,
        'campus_sede',
        'ativo',
    )
    list_display_icons = True
    show_count_on_tabs = True
    form = ProgramaPosGraduacaoForm

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(ativo=True)

    def get_tabs(self, request):
        return ['tab_lato_sensu', 'tab_stricto_sensu']

    def tab_lato_sensu(self, request, queryset):
        return queryset.filter(nivel=ProgramaPosGraduacao.LATO_SENSU)

    tab_lato_sensu.short_description = 'Lato Sensu'

    def tab_stricto_sensu(self, request, queryset):
        return queryset.filter(nivel=ProgramaPosGraduacao.STRICTO_SENSU)

    tab_stricto_sensu.short_description = 'Stricto Sensu'

    def save_model(self, request, obj, form, change):
        if obj.coordenador:
            user_do_coordenador = obj.coordenador.get_vinculo().user
            if not user_do_coordenador.has_group_cached('Coordenador de Pós-Graduação'):
                user_do_coordenador.groups.add(Group.objects.filter(name='Coordenador de Pós-Graduação').first())
            if change:
                original_obj = self.model.objects.get(pk=obj.pk)
                if original_obj.coordenador and original_obj.coordenador != obj.coordenador:
                    original_obj.coordenador.get_vinculo().user.groups.remove(Group.objects.filter(name='Coordenador de Pós-Graduação').first())
        super().save_model(request, obj, form, change)


admin.site.register(ProgramaPosGraduacao, ProgramaPosGraduacaoAdmin)


class CursoReconhecimentoDiplomaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo')
    ordering = ('nome',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(CursoReconhecimentoDiploma, CursoReconhecimentoDiplomaAdmin)


class ReconhecimentoDiplomaAdmin(ModelAdminPlus):
    list_display = ('vinculo_requerente', 'numero_registro', 'curso', 'data_defesa', 'responsavel', 'cadastrado_em')
    ordering = ('id', 'vinculo_requerente')
    list_filter = ('vinculo_requerente', 'curso_reconhecimento')
    list_display_icons = True
    date_hierarchy = 'data_defesa'

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'vinculo_requerente',
                    ('numero_registro', 'numero_etiqueta'),
                    'processo',
                    'curso',
                    ('instituicao_origem', 'pais_instituicao_origem'),
                    'tipo_curso',
                    'curso_reconhecimento',
                    ('data_defesa', 'data_registro'),
                    ('reitor', 'pro_reitor'),
                )
            },
        ),
    )


admin.site.register(ReconhecimentoDiploma, ReconhecimentoDiplomaAdmin)


class TipoQuestionarioObraAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(TipoQuestionarioObra, TipoQuestionarioObraAdmin)


class CriterioAvaliacaoObraAdmin(ModelAdminPlus):
    list_display = ('descricao', 'nota', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(CriterioAvaliacaoObra, CriterioAvaliacaoObraAdmin)


class PerguntaQuestionarioObraAdmin(ModelAdminPlus):
    list_display = ('descricao', 'tipo_questionario', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(PerguntaQuestionarioObra, PerguntaQuestionarioObraAdmin)


class IncubadoraAdmin(ModelAdminPlus):
    form = IncubadoraForm
    list_display = ('nome', 'sigla', 'uo', 'get_coordenador', 'get_gerente')
    ordering = ('nome',)
    list_filter = ('uo',)
    list_display_icons = True

    def get_coordenador(self, obj):
        return format_(obj.coordenador.user)

    get_coordenador.short_description = 'Coordenador'

    def get_gerente(self, obj):
        return format_(obj.gerente.user)

    get_gerente.short_description = 'Gerente Executivo'


admin.site.register(Incubadora, IncubadoraAdmin)


class NaoLidalListFilter(admin.SimpleListFilter):
    title = 'Com despacho não lido'
    parameter_name = 'nao_lido'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))
        return opcoes

    def queryset(self, request, queryset):
        pendentes = PublicacaoPropriedadeIntelectual.objects.filter(lida=False)
        if self.value() == '1':
            return queryset.filter(id__in=pendentes.values_list('propriedadeintelectual', flat=True))
        elif self.value() == '2':
            return queryset.exclude(id__in=pendentes.values_list('propriedadeintelectual', flat=True))


class PendentePagamentoFilter(admin.SimpleListFilter):
    title = 'Com pagamento de anuidade pendente'
    parameter_name = 'pagamento_pendente'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))
        return opcoes

    def queryset(self, request, queryset):
        hoje = datetime.date.today()
        pendentes = AnuidadeRegistroPropriedadeIntelectual.objects.filter(
            propriedadeintelectual__ativo=True, situacao=AnuidadeRegistroPropriedadeIntelectual.PENDENTE, inicio_ordinario__lte=hoje
        )
        if self.value() == '1':
            return queryset.filter(id__in=pendentes.values_list('propriedadeintelectual', flat=True))
        elif self.value() == '2':
            return queryset.exclude(id__in=pendentes.values_list('propriedadeintelectual', flat=True))


class ConcedidaFilter(admin.SimpleListFilter):
    title = 'Concedido'
    parameter_name = 'concedido'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))
        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.exclude(data_concessao=None)
        elif self.value() == '2':
            return queryset.filter(data_concessao=None)


class DataDepositoFilter(admin.SimpleListFilter):
    title = 'Ano do depósito'
    parameter_name = 'ano_deposito'

    def lookups(self, request, model_admin):
        anos = RegistroPropriedadeIntelectual.objects.values_list('data__year', flat=True).distinct().order_by('-data__year')
        return [(ano, ano) for ano in anos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(data__year=self.value())


class RegistroPropriedadeIntelectualAdmin(ModelAdminPlus):
    form = RegistroPropriedadeIntelectualForm
    list_display = ('get_acoes', 'titulo', 'numero_processo', 'data', 'data_concessao', 'primeira_rpi', 'tipo', 'get_opcoes')
    ordering = ('numero_processo',)
    search_fields = ('titulo', 'titulares', 'inventores', 'numero_processo')
    list_filter = ('tipo', NaoLidalListFilter, PendentePagamentoFilter, DataDepositoFilter)
    export_to_xls = True
    list_xls_display = ('titulo', 'numero_processo', 'data', 'data_concessao', 'primeira_rpi', 'tipo')

    def get_acoes(self, obj):
        mostra_acoes = icon('view', f'/pesquisa/pi_visualizar/{obj.id}/')
        if self.request.user.has_perm('pesquisa.change_registropropriedadeintelectual'):
            mostra_acoes += icon('edit', f'/admin/pesquisa/registropropriedadeintelectual/{obj.id}/')
        return mark_safe(mostra_acoes)

    get_acoes.short_description = 'Ações'

    def get_action_bar(self, request):
        items = super().get_action_bar(request)
        url_base = '/pesquisa/importar_rpi_mais_recente/'
        items.append({'url': url_base, 'label': 'Importar RPI'})
        url_base = '/pesquisa/relatorio_propriedades/'
        items.append({'url': url_base, 'label': 'Relatório'})
        return items

    def get_opcoes(self, obj):
        if PublicacaoPropriedadeIntelectual.objects.filter(propriedadeintelectual=obj).exists():
            return mark_safe(
                f"""<ul class="action-bar">
                    <li><a href="/pesquisa/visualizar_despachos_propriedade/{obj.id}/" class="btn default">Visualizar Despachos</a></li>
                </ul>"""
            )
        else:
            return ''

    get_opcoes.short_description = 'Opções'

    def response_add(self, request, obj):
        self.message_user(request, 'Registro cadastrado com sucesso.')
        return HttpResponseRedirect(f'/pesquisa/pi_visualizar/{obj.pk}/')

    def changelist_view(self, request, extra_context=None):
        list_filter = self.list_filter
        if request.GET.get('tipo') and request.GET.get('tipo') in ['3', '8']:
            if ConcedidaFilter not in list_filter:
                lista = list(self.list_filter)
                lista.insert(3, ConcedidaFilter)
                list_filter = tuple(lista)
        elif ConcedidaFilter in list_filter:
            lista = list(self.list_filter)
            try:
                lista.pop(3)
            except Exception:
                pass
            list_filter = tuple(lista)
        self.list_filter = list_filter
        return super().changelist_view(request, extra_context=extra_context)


admin.site.register(RegistroPropriedadeIntelectual, RegistroPropriedadeIntelectualAdmin)


class TransferenciaTecnologicaAdmin(ModelAdminPlus):
    form = TransferenciaTecnologicaForm
    list_display = ('get_acoes', 'titulo', 'get_empresa', 'get_situacao', 'tipo')
    list_filter = ('titulo', 'tipo')

    def get_acoes(self, obj):
        mostra_acoes = icon('view', f'/pesquisa/transferencia_visualizar/{obj.id}/')
        if in_group(self.request.user, 'Diretor de Pesquisa') or (self.has_change_permission(self.request)):
            mostra_acoes += icon('edit', f'/pesquisa/editar_transferencia/{obj.id}/')
        return mark_safe(mostra_acoes)

    get_acoes.short_description = 'Ações'

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append(
                {'url': '/pesquisa/cadastrar_transferencia/', 'label': 'Cadastrar Licenciamento/ transferência de tecnologia', 'css_class': 'success'}
            )
        url_base = '/pesquisa/relatorio_transferencias/'
        items.append({'url': url_base, 'label': 'Relatório'})
        return items

    def get_situacao(self, obj):
        sit = obj.get_situacao()
        return mark_safe(sit) if sit else '-'

    get_situacao.short_description = 'Situação'

    def get_empresa(self, obj):
        return obj.empresa

    get_empresa.short_description = 'Empresa'


admin.site.register(TransferenciaTecnologica, TransferenciaTecnologicaAdmin)


class PropriedadeIntelectualAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(PropriedadeIntelectual, PropriedadeIntelectualAdmin)


class ItemDoacaoInline(admin.StackedInline):
    model = ItemDoacaoEditora
    extra = 1


class DoacaoEditoraAdmin(ModelAdminPlus):
    form = DoacaoEditoraForm
    list_display = ('get_acoes', 'data', 'destino', 'responsavel', 'get_arquivo', 'get_itens', 'aceite_em')
    ordering = ('data',)
    search_fields = ('destino', 'responsavel')
    list_display_icons = False
    inlines = [ItemDoacaoInline]

    def get_arquivo(self, obj):
        if obj.arquivo:
            return mark_safe(f'<a href="{obj.arquivo.url}" class="btn default">Ver Arquivo</a>')

    get_arquivo.short_description = 'Arquivo'

    def get_itens(self, obj):
        texto = '<ul>'
        for item in obj.itemdoacaoeditora_set.all().order_by('titulo'):
            texto += f'<li>{item.titulo} - {item.quantidade}</li>'
        texto += '</ul>'
        return mark_safe(texto)

    get_itens.short_description = 'itens'

    def get_acoes(self, obj):
        if self.request.user.has_perm('pesquisa.change_doacaoeditora'):
            return icon('edit', f'/admin/pesquisa/doacaoeditora/{obj.id}/') + icon('delete', f'/admin/pesquisa/doacaoeditora/{obj.id}/delete/')
        return ''

    get_acoes.short_description = 'Ações'


admin.site.register(DoacaoEditora, DoacaoEditoraAdmin)


class CategoriaQuesitoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)


admin.site.register(CategoriaQuesito, CategoriaQuesitoAdmin)


class QuesitoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)


admin.site.register(Quesito, QuesitoAdmin)


class PesoQuesitoAreaAdmin(ModelAdminPlus):
    search_fields = ('quesito__descricao',)
    list_filter = ('areacapes',)


admin.site.register(PesoQuesitoArea, PesoQuesitoAreaAdmin)


class QuesitoRespostaInline(admin.StackedInline):
    model = QuesitoAutoavaliacao
    fields = ('quesito',)
    extra = 1


class AutoavaliacaoProgramaPosAdmin(ModelAdminPlus):
    list_display = ('programa', 'ano', 'data_inicio', 'data_fim', 'get_quesitos')
    ordering = ('ano',)
    search_fields = ('programa', 'ano')
    list_display_icons = True
    inlines = [QuesitoRespostaInline]

    def get_quesitos(self, obj):
        quesitos = []
        for quesito in QuesitoAutoavaliacao.objects.filter(autoavaliacao=obj):
            quesitos.append(quesito.quesito.descricao)
        return mark_safe('<br/>'.join(quesitos))

    get_quesitos.short_description = 'Quesitos'


admin.site.register(AutoavaliacaoProgramaPos, AutoavaliacaoProgramaPosAdmin)


class CategoriaEventoIncubadoraAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(CategoriaEventoIncubadora, CategoriaEventoIncubadoraAdmin)


class AtividadeAutorizacaoSISBIOAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(AtividadeAutorizacaoSISBIO, AtividadeAutorizacaoSISBIOAdmin)


class AtividadeAutorizacaoSISGENAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(AtividadeAutorizacaoSISGEN, AtividadeAutorizacaoSISGENAdmin)


class EspecialidadeAssessorAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(EspecialidadeAssessor, EspecialidadeAssessorAdmin)


class ModuloAssessoriaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(ModuloAssessoria, ModuloAssessoriaAdmin)


class IntegranteEquipeTecnicaAdmin(ModelAdminPlus):
    list_display = ('get_acoes', 'get_foto', 'get_info_principal', 'get_contatos', 'get_info_funcional', 'get_especialidades', 'get_opcoes')
    ordering = ('vinculo__pessoa__nome',)
    list_display_icons = False
    list_filter = ('vinculo__setor__uo',)
    form = IntegranteEquipeTecnicaForm

    def get_acoes(self, obj):
        texto = icon('view', f'/pesquisa/visualizar_assessor/{obj.id}/')
        return mark_safe(texto)

    get_acoes.short_description = 'Ações'

    def get_opcoes(self, obj):
        retorno = '<ul class="action-bar">'
        if self.request.user.has_perm('pesquisa.tem_acesso_sistemico'):
            retorno += f"""
                    <li><a href="/pesquisa/excluir_integrante_equipe_tecnica/{obj.id}/" class="btn danger confirm">Excluir</a></li>
               """

        if Incubadora.tem_permissao_gerenciar_incubadora(self.request.user.get_vinculo()):
            retorno += f'<li><a href="/pesquisa/recrutar_assessor/{obj.id}/" class="btn success">Recrutar</a></li>'
        retorno += '</ul>'
        return mark_safe(retorno)

    get_opcoes.short_description = 'Opções'

    def get_especialidades(self, obj):
        return obj.get_especialidades()

    get_especialidades.short_description = 'Especialidades'

    def get_foto(self, obj):
        img_src = obj.vinculo.get_foto_75x100_url()
        return mark_safe(f'<div class="photo-circle"><img src="{img_src}" alt="{obj.__str__()}" /></div>')

    get_foto.short_description = 'Foto'

    def get_info_principal(self, obj):
        mostrar_afast = obj.vinculo.eh_servidor() and obj.vinculo.relacionamento.estah_afastado_ou_de_ferias_ateh(datetime.date.today())
        html_afast = ''
        if mostrar_afast:
            html_afast = f"""<div class="status-container d-flex flex-wrap">
                <span class="status status-default flex-grow-0"><span class="fas fa-info" aria-hidden="true"></span> {mostrar_afast}</span>
            </div>"""

        return mark_safe(f'<h3>{obj.vinculo.__str__()}</h3>{html_afast}')

    get_info_principal.short_description = 'Nome'

    def get_contatos(self, obj):
        show_telefones, show_email, show_pgd = '', '', ''
        if obj.vinculo.pessoa.pessoafisica.telefones_institucionais:
            show_telefones = '<dt>Telefones institucionais:</dt>'
            for telefone in obj.vinculo.pessoa.pessoafisica.telefones_institucionais.split(','):
                show_telefones += f'<dd>{telefone}</dd>'

        if obj.vinculo.email_notificacao:
            show_email = f'<a href="mailto:{obj.vinculo.email_notificacao}">{obj.vinculo.email_notificacao}</a>'

        esta_em_pgd, adesao_pgd = obj.vinculo.eh_servidor() and estah_no_pgd_hoje_pgd1_pgd2(obj.vinculo.relacionamento) or None, None
        if esta_em_pgd and adesao_pgd:
            show_pgd = f"""
                <dt>Contato PGD:</dt>
                <dd>{adesao_pgd.get_contato_preferencia()}</dd>
            """
        if show_email or show_telefones or show_telefones:
            out = f"""<dl>
                <dt>E-mail institucional:</dt><dd>{show_email}</dd>
                {show_telefones}{show_pgd}
            </dl>"""
        else:
            out = f"""<dl>
                <dt>E-mail:</dt><dd>{obj.vinculo.email_notificacao}</dd>
            </dl>"""

        return mark_safe(out)

    get_contatos.short_description = 'Contatos'

    def get_info_funcional(self, obj):
        out = ['<dl>']

        if obj.vinculo.eh_servidor():
            if obj.vinculo.relacionamento.setor_lotacao:
                out.append(f'<dt>SIAPE Lotação:</dt><dd>{obj.vinculo.relacionamento.setor_lotacao.sigla}</dd>')
            if obj.vinculo.eh_servidor() and obj.vinculo.relacionamento.setor_exercicio:
                out.append(f'<dt>SIAPE Exercício:</dt><dd>{obj.vinculo.relacionamento.setor_exercicio.sigla}</dd>')
            if obj.vinculo.relacionamento.setor:
                out.append(f'<dt>SUAP:</dt><dd>{obj.vinculo.relacionamento.setor.sigla}</dd>')
        else:
            out.append('<dt></dt><dd>-</dd>')
        out.append('</dl>')
        return mark_safe(''.join(out))

    get_info_funcional.short_description = 'Setor/Papel'


admin.site.register(IntegranteEquipeTecnica, IntegranteEquipeTecnicaAdmin)


class TipoParceriaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(TipoParceria, TipoParceriaAdmin)


class SituacaoParceriaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(SituacaoParceria, SituacaoParceriaAdmin)


class FuncaoMembroParceriaAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(FuncaoMembroParceria, FuncaoMembroParceriaAdmin)


class TipoTitularidadePIAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    ordering = ('descricao',)
    list_filter = ('ativo',)
    list_display_icons = True


admin.site.register(TipoTitularidadePI, TipoTitularidadePIAdmin)


class ParceriaAdmin(ModelAdminPlus):
    list_display = ('get_acoes', 'titulo', 'coordenador', 'get_parceiros', 'get_recursos', 'get_vigencia', 'tipo', 'area', 'situacao')
    ordering = ('titulo',)
    list_filter = ('tipo', 'area', 'situacao')
    search_fields = ('titulo',)
    list_display_icons = False
    export_to_xls = True
    list_xls_display = ('titulo', 'coordenador', 'get_parceiros', 'get_recursos', 'get_vigencia', 'tipo', 'area', 'situacao')

    def get_action_bar(self, request):
        items = []
        if self.has_add_permission(request):
            items.append({'url': '/pesquisa/cadastrar_parceria/', 'label': 'Cadastrar Parceria', 'css_class': 'success'})
        return items + super().get_action_bar(request, remove_add_button=True)

    def get_acoes(self, obj):
        mostra_acoes = icon('view', f'/pesquisa/parceria/{obj.id}/')
        if self.has_change_permission(self.request):
            mostra_acoes += icon('edit', f'/pesquisa/editar_parceria/{obj.id}/')
        return mark_safe(mostra_acoes)

    get_acoes.short_description = 'Ações'

    def get_parceiros(self, obj):
        return obj.get_parceiros()

    get_parceiros.short_description = 'Parceiros'

    def get_recursos(self, obj):
        return obj.get_recursos()

    get_recursos.short_description = 'Recursos Externos'

    def get_vigencia(self, obj):
        return obj.get_vigencia()

    get_vigencia.short_description = 'Vigência'


admin.site.register(Parceria, ParceriaAdmin)
