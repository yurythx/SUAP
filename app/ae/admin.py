import datetime
from datetime import date

from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.db.models import ExpressionWrapper, F, Q, fields
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.utils.safestring import mark_safe

from ae.forms import (
    AcaoEducativaForm,
    AgendamentoRefeicaoForm,
    AtendimentoSetorForm,
    AtividadeDiversaForm,
    AuxilioEventualForm,
    DatasLiberadasForm,
    DatasRecessoFeriasForm,
    DemandaAlunoAtendidaModelForm,
    EditalForm,
    EditarCriterioSelecaoProgramaForm,
    EditarParametroSelecaoProgramaForm,
    HorarioSolicitacaoForm,
    InscricaoModelForm,
    OfertaAlimentacaoForm,
    OfertaBolsaForm,
    OfertaPasseForm,
    OfertaTurmaForm,
    OfertaValorBolsaForm,
    OfertaValorRefeicaoForm,
    OpcaoRespostaInscricaoProgramaForm,
    OpcaoRespostaPerguntaParticipacaoForm,
    PeriodoInscricaoForm,
    ProgramaForm,
    SolicitacaoAuxilioAlunoForm,
    TipoAuxilioEventualForm,
    TipoProgramaForm,
    ValorTotalAuxiliosForm,
    ValorTotalBolsasForm,
)
from ae.models import (
    AcaoEducativa,
    AgendamentoRefeicao,
    AlteracaoParticipacaoAlimentacao,
    AtendimentoSetor,
    AtividadeDiversa,
    AuxilioEventual,
    BeneficioGovernoFederal,
    Caracterizacao,
    CategoriaAlimentacao,
    CategoriaBolsa,
    ComprovanteParticipacao,
    CriterioSelecaoPrograma,
    DatasLiberadasFaltasAlimentacao,
    DatasRecessoFerias,
    DemandaAluno,
    DemandaAlunoAtendida,
    DocumentoInscricaoAluno,
    Edital,
    HistoricoAlteracaoParecer,
    HistoricoAlteracaoTermoCompromisso,
    HistoricoFaltasAlimentacao,
    HistoricoSuspensoesAlimentacao,
    HorarioJustificativaFalta,
    HorarioSolicitacaoRefeicao,
    Idioma,
    ImportacaoCadunico,
    Inscricao,
    MotivoSolicitacaoRefeicao,
    OfertaAlimentacao,
    OfertaBolsa,
    OfertaPasse,
    OfertaTurma,
    OfertaValorBolsa,
    OfertaValorRefeicao,
    OpcaoRespostaInscricaoPrograma,
    OpcaoRespostaPerguntaParticipacao,
    ParametroSelecaoPrograma,
    Participacao,
    ParticipacaoTrabalho,
    PerguntaInscricaoPrograma,
    PerguntaParticipacao,
    PeriodoInscricao,
    Programa,
    SituacaoTrabalho,
    SolicitacaoAuxilioAluno,
    SolicitacaoRefeicaoAluno,
    TipoAreaResidencial,
    TipoAtendimentoSetor,
    TipoAtividadeDiversa,
    TipoAuxilioEventual,
    TipoEscola,
    TipoImovelResidencial,
    TipoPrograma,
    ValorTotalAuxilios,
    ValorTotalBolsas,
)
from comum.models import Ano, Configuracao
from comum.utils import get_sigla_reitoria, get_uo
from djtools.contrib.admin import ModelAdminPlus, SimpleListModelFilter
from djtools.templatetags.filters import format_, in_group, status
from djtools.templatetags.filters.utils import format_money
from djtools.templatetags.tags import icon
from djtools.utils import httprr
from edu.models import CursoCampus, MatriculaPeriodo, Modalidade, SituacaoMatriculaPeriodo, Turno
from rh.models import UnidadeOrganizacional


class ProgramaAdmin(ModelAdminPlus):
    list_display = (
        'tipo_programa',
        'instituicao',
        'get_publico_alvo',
        'participantes',
        'impedir_solicitacao_beneficio',
        'exige_comprovante_pagamento',
        'exige_folha_frequencia',
        'get_is_configuracao_pendente',
    )
    search_fields = ('titulo',)
    list_filter = ('instituicao', 'tipo_programa')
    ordering = ('instituicao', 'tipo_programa__titulo')

    list_display_icons = True
    form = ProgramaForm
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'tipo_programa',
                    'descricao',
                    'instituicao',
                    'demandas',
                    'publico_alvo',
                )
            },
        ),
        (
            'Configurações',
            {
                'fields': (
                    'impedir_solicitacao_beneficio',
                    'exige_comprovante_pagamento',
                    'exige_folha_frequencia',
                    'qtd_faltas_bloqueio_alimentacao',
                )
            },
        ),
        (
            'Período de Solicitações de Alteração de Dias/Refeições',
            {
                'fields': (
                    'data_inicio_alteracoes',
                    'data_fim_alteracoes',
                )
            },
        ),
    )

    def get_publico_alvo(self, obj):
        return ', '.join([p.sigla for p in obj.publico_alvo.all()])

    get_publico_alvo.short_description = 'Público-Alvo'

    def participantes(self, obj):
        return mark_safe(obj.get_participacoes_abertas().count())

    participantes.short_description = 'Qtd. Participantes'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_group_cached('Nutricionista', ignore_groups_if_superuser=False):
            qs = qs.filter(tipo_programa__sigla=Programa.TIPO_ALIMENTACAO)
            if get_uo(request.user).setor.sigla != get_sigla_reitoria():
                qs = qs.filter(instituicao=get_uo(request.user))
        else:
            if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
                qs = qs.filter(instituicao=get_uo(request.user))
        return qs

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)

        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            if request.user.has_group_cached('Nutricionista'):
                list_filter = ()
            else:
                list_filter = ()
        return list_filter

    def get_is_configuracao_pendente(self, obj):
        return format_(obj.estah_configurado())

    get_is_configuracao_pendente.short_description = 'Configuração Realizada?'

    def save_model(self, request, obj, form, change):
        obj.titulo = '{} ({})'.format(form.cleaned_data['tipo_programa'].titulo, form.cleaned_data['instituicao'])
        obj.save()


admin.site.register(Programa, ProgramaAdmin)


class ProgramaFilter(admin.SimpleListFilter):
    title = 'Programa'
    parameter_name = 'programa'

    def lookups(self, request, model_admin):
        programas = Programa.objects.all()

        if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
            programas = programas.filter(instituicao=get_uo(request.user))

        return [(d.id, d.titulo) for d in programas]

    def queryset(self, request, queryset):
        if self.value() and int(self.value()):
            return queryset.filter(programa_id=self.value())
        return queryset


class EditalFilter(admin.SimpleListFilter):
    title = 'Edital'
    parameter_name = 'edital'

    def lookups(self, request, model_admin):
        editais = Edital.objects.all()
        return [(d.id, d.__str__()) for d in editais]

    def queryset(self, request, queryset):
        if self.value():
            busca = queryset.filter(periodo_inscricao__edital=get_object_or_404(Edital, pk=self.value()))
            if not request.user.has_perm('ae.pode_ver_relatorios_todos'):
                busca = busca.filter(periodo_inscricao__campus=get_uo(request.user))
            return busca


class DocumentacaoChoices:
    EM_DIA = '1'
    NAO_ENTEGUE = '2'
    EXPIRADA = '3'
    AGUARDANDO = '4'

    OPCOES = ((EM_DIA, 'Validada'), (NAO_ENTEGUE, 'Invalidada'), (EXPIRADA, 'Expirada'), (AGUARDANDO, 'Aguardando análise'))


class DocumentacaoFilter(admin.SimpleListFilter):
    title = 'Documentação'
    parameter_name = 'documentacao'

    def lookups(self, request, model_admin):
        return DocumentacaoChoices.OPCOES

    def queryset(self, request, queryset):
        if self.value():
            from djtools.utils import somar_dias

            prazo_expiracao = Configuracao.get_valor_por_chave('ae', 'prazo_expiracao_documentacao')
            total_dias = prazo_expiracao and int(prazo_expiracao) or 365
            data = somar_dias(datetime.datetime.now(), -total_dias)
            if self.value() == DocumentacaoChoices.EM_DIA:
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__documentada=True, aluno__data_documentacao__gte=data)

                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__documentada=True, aluno__data_documentacao__gte=data)

            elif self.value() == DocumentacaoChoices.NAO_ENTEGUE:
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__documentacao_invalidada=True)

                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__documentacao_invalidada=True)

            elif self.value() == DocumentacaoChoices.EXPIRADA:
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__data_documentacao__lt=data, aluno__documentacao_invalidada=False)
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(
                        programa__instituicao=get_uo(request.user), aluno__data_documentacao__lt=data, aluno__documentacao_invalidada=False
                    )
            elif self.value() == DocumentacaoChoices.AGUARDANDO:
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__documentacao_invalidada=False, aluno__documentada=False, aluno__data_documentacao=None)
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(
                        programa__instituicao=get_uo(request.user),
                        aluno__documentacao_invalidada=False,
                        aluno__documentada=False,
                        aluno__data_documentacao=None,
                    )


class RendaChoices:
    ATE_UM_QUARTO = '1'
    ENTRE_UM_QUARTO_E_MEIO = '2'
    ENTRE_MEIO_E_UM = '3'
    ENTRE_UM_E_UM_MEIO = '4'
    ENTRE_UM_MEIO_E_DOIS = '5'
    ENTRE_DOIS_E_DOIS_MEIO = '6'
    ENTRE_DOIS_MEIO_E_TRES = '7'
    ENTRE_TRES_E_TRES_MEIO = '8'
    ENTRE_TRES_MEIO_E_QUATRO = '9'
    ENTRE_QUATRO_E_QUATRO_MEIO = '10'
    ENTRE_QUATRO_MEIO_E_CINCO = '11'
    MAIOR_QUE_CINCO = '12'
    NAO_INFORMADO = '13'
    IGUAL_0_SM = '14'

    OPCOES = (
        (IGUAL_0_SM, 'Igual a 0 SM'),
        (ATE_UM_QUARTO, 'Até ¼ SM'),
        (ENTRE_UM_QUARTO_E_MEIO, 'Entre ¼ SM e ½ SM'),
        (ENTRE_MEIO_E_UM, 'Entre ½ SM e 1 SM'),
        (ENTRE_UM_E_UM_MEIO, 'Entre 1 SM e 1 ½ SM'),
        (ENTRE_UM_MEIO_E_DOIS, 'Entre 1 ½ SM e 2 SM'),
        (ENTRE_DOIS_E_DOIS_MEIO, 'Entre 2 SM e 2 ½ SM'),
        (ENTRE_DOIS_MEIO_E_TRES, 'Entre 2 ½ SM e 3 SM'),
        (ENTRE_TRES_E_TRES_MEIO, 'Entre 3 SM e 3 ½ SM'),
        (ENTRE_TRES_MEIO_E_QUATRO, 'Entre 3 ½ SM e 4 SM'),
        (ENTRE_QUATRO_E_QUATRO_MEIO, 'Entre 4 SM e 4 ½ SM'),
        (ENTRE_QUATRO_MEIO_E_CINCO, 'Entre 4 ½ SM e 5 SM'),
        (MAIOR_QUE_CINCO, 'Maior que 5 SM'),
        (NAO_INFORMADO, 'Não Informado'),
    )


class RendaFilter(admin.SimpleListFilter):
    title = 'Renda per capita'
    parameter_name = 'renda'

    def lookups(self, request, model_admin):
        return RendaChoices.OPCOES

    def queryset(self, request, queryset):
        if self.value():
            from decimal import Decimal

            from comum.models import Configuracao

            sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
            if self.value() == RendaChoices.IGUAL_0_SM:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).filter(renda_bruta_familiar=0)
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ATE_UM_QUARTO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio <= {sm}/4']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_UM_QUARTO_E_MEIO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > {sm}/4 AND renda_bruta_familiar/qtd_pessoas_domicilio <= {sm}/2']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_MEIO_E_UM:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > {sm}/2 AND renda_bruta_familiar/qtd_pessoas_domicilio <= {sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_UM_E_UM_MEIO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > {sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 1.5*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_UM_MEIO_E_DOIS:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 1.5*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 2*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_DOIS_E_DOIS_MEIO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 2*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 2.5*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_DOIS_MEIO_E_TRES:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 2.5*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 3*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_TRES_E_TRES_MEIO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 3*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 3.5*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_TRES_MEIO_E_QUATRO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 3.5*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 4*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_QUATRO_E_QUATRO_MEIO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 4*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 4.5*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.ENTRE_QUATRO_MEIO_E_CINCO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > 4.5*{sm} AND renda_bruta_familiar/qtd_pessoas_domicilio <= 5*{sm}']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.MAIOR_QUE_CINCO:
                caracterizacao = Caracterizacao.objects.filter(~Q(qtd_pessoas_domicilio=0)).extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > ({sm} * 5)']
                )
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))

            elif self.value() == RendaChoices.NAO_INFORMADO:
                caracterizacao = Caracterizacao.objects.filter(qtd_pessoas_domicilio=0)
                if request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
                    return queryset.filter(aluno__in=caracterizacao.values_list('aluno', flat=True))
                elif in_group(request.user, 'Assistente Social'):
                    return queryset.filter(programa__instituicao=get_uo(request.user), aluno__in=caracterizacao.values_list('aluno', flat=True))


class CursoFilter(admin.SimpleListFilter):
    title = 'Curso'
    parameter_name = 'curso'

    def lookups(self, request, model_admin):
        cursos = CursoCampus.objects.filter(ativo=True).order_by('descricao')

        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            cursos = cursos.filter(diretoria__setor__uo=get_uo(request.user))

        return [(d.id, d.descricao) for d in cursos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(aluno__curso_campus=CursoCampus.objects.get(pk=self.value()))


class PrimeiraOpcaoFilter(admin.SimpleListFilter):
    title = 'Primeira Turma'
    parameter_name = 'primeira'

    def lookups(self, request, model_admin):
        opcoes = OfertaTurma.objects.filter(ativa=True)

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(inscricaoidioma__primeira_opcao=self.value())


class SegundaOpcaoFilter(admin.SimpleListFilter):
    title = 'Segunda Turma'
    parameter_name = 'segunda'

    def lookups(self, request, model_admin):
        opcoes = OfertaTurma.objects.filter(ativa=True)

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(inscricaoidioma__segunda_opcao=self.value())


class ProgramaSocialFilter(admin.SimpleListFilter):
    title = 'Programa Social'
    parameter_name = 'programasocial'

    def lookups(self, request, model_admin):
        opcoes = BeneficioGovernoFederal.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            caracterizacoes = Caracterizacao.objects.filter(beneficiario_programa_social=self.value())
            return queryset.filter(aluno__id__in=caracterizacoes.values_list('aluno', flat=True))


class EscolaPublicaFilter(admin.SimpleListFilter):
    title = 'Escola de Origem'
    parameter_name = 'tipoescola'

    def lookups(self, request, model_admin):
        opcoes = TipoEscola.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            caracterizacoes = Caracterizacao.objects.filter(Q(escola_ensino_medio=self.value()) | Q(escola_ensino_fundamental=self.value()))
            return queryset.filter(aluno__id__in=caracterizacoes.values_list('aluno', flat=True))


class ResponsavelFinanceiroFilter(admin.SimpleListFilter):
    title = 'Situação Financeira do Responsável'
    parameter_name = 'situacaoresponsavel'

    def lookups(self, request, model_admin):
        opcoes = SituacaoTrabalho.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            caracterizacoes = Caracterizacao.objects.filter(responsavel_financeir_trabalho_situacao=self.value())
            return queryset.filter(aluno__id__in=caracterizacoes.values_list('aluno', flat=True))


class ModalidadeFilter(admin.SimpleListFilter):
    title = 'Modalidade'
    parameter_name = 'modalidade'

    def lookups(self, request, model_admin):
        opcoes = Modalidade.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(aluno__curso_campus__modalidade=self.value())


class OutrosProgramasFilter(admin.SimpleListFilter):
    title = 'Participa de algum programa do Serviço Social'
    parameter_name = 'progrinstituicao'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))
        return opcoes

    def queryset(self, request, queryset):
        hoje = datetime.date.today()
        participacoes_abertas = Participacao.objects.filter(Q(data_termino__gte=hoje) | Q(data_termino__isnull=True))
        if self.value() == '1':
            return queryset.filter(aluno__in=participacoes_abertas.values_list('aluno', flat=True))
        elif self.value() == '2':
            return queryset.exclude(aluno__in=participacoes_abertas.values_list('aluno', flat=True))


class AnoLetivoFilter(admin.SimpleListFilter):
    title = 'Ano Letivo'
    parameter_name = 'anoletivo'

    def lookups(self, request, model_admin):
        opcoes = Ano.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        return queryset


class PeriodoLetivoFilter(admin.SimpleListFilter):
    title = 'Período Letivo'
    parameter_name = 'periodoletivo'

    def lookups(self, request, model_admin):
        opcoes = (('1', '1'), ('2', '2'))
        return opcoes

    def queryset(self, request, queryset):
        return queryset


class TurnoFilter(admin.SimpleListFilter):
    title = 'Turno'
    parameter_name = 'turno'

    def lookups(self, request, model_admin):
        opcoes = Turno.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        ano = request.GET.get('anoletivo')
        periodo = request.GET.get('periodoletivo')
        if ano and periodo and self.value():
            alunos = MatriculaPeriodo.objects.filter(ano_letivo=ano, periodo_letivo=periodo, turma__turno=self.value())
            return queryset.filter(aluno__in=alunos.values_list('aluno', flat=True))


class SituacaoMatriculaPeriodoFilter(admin.SimpleListFilter):
    title = 'Situação da Matrícula no Período'
    parameter_name = 'situacaomatricula'

    def lookups(self, request, model_admin):
        opcoes = SituacaoMatriculaPeriodo.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        ano = request.GET.get('anoletivo')
        periodo = request.GET.get('periodoletivo')
        if ano and periodo and self.value():
            alunos = MatriculaPeriodo.objects.filter(ano_letivo=ano, periodo_letivo=periodo, situacao=self.value())
            return queryset.filter(aluno__in=alunos.values_list('aluno', flat=True))


class ParticipanteProgramaFilter(admin.SimpleListFilter):
    title = 'Participante do Programa'
    parameter_name = 'participanteprograma'

    def lookups(self, request, model_admin):
        opcoes = Programa.objects.all()

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            programa = Programa.objects.get(id=self.value())
            participacoes_abertas = programa.get_participacoes_abertas()
            return queryset.filter(aluno__in=participacoes_abertas.values_list('aluno', flat=True))


class ParticipanteProgramaDaInscricaoFilter(admin.SimpleListFilter):
    title = ' Tem participação ativa no mesmo Programa'
    parameter_name = 'participanteprogramadainscricao'

    def lookups(self, request, model_admin):
        return [('Sim', 'Sim'), ('Não', 'Não')]

    def queryset(self, request, queryset):
        if self.value():
            participacoes_abertas = Participacao.abertas.filter(programa__in=queryset.values_list('programa', flat=True)).only('aluno', 'programa')
            ids_inscricoes = []
            for participacao in participacoes_abertas:
                if queryset.filter(aluno=participacao.aluno, programa=participacao.programa).exists():
                    ids_inscricoes.append(queryset.filter(aluno=participacao.aluno, programa=participacao.programa)[0].id)
            if self.value() == 'Sim':
                return queryset.filter(id__in=ids_inscricoes)
            elif self.value() == 'Não':
                return queryset.exclude(id__in=ids_inscricoes)


class PeriodoInscricaoFilter(admin.SimpleListFilter):
    title = 'Período de Inscrição'
    parameter_name = 'periodoinscricao'

    def lookups(self, request, model_admin):
        opcoes = PeriodoInscricao.objects.all().order_by('-data_inicio').select_related('edital', 'campus')
        edital = request.GET.get('edital')
        if edital:
            opcoes = opcoes.filter(edital_id=edital)

        return [(d.id, d) for d in opcoes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(periodo_inscricao=self.value())


class ValidacaoTermoFilter(admin.SimpleListFilter):
    title = 'Validação do Termo de Compromisso:'
    parameter_name = 'validacao_termo'

    def lookups(self, request, model_admin):
        return Inscricao.VALIDACAO_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            if self.value() == 'Pendente':
                return queryset.filter(
                    termo_compromisso_digitalizado__isnull=False,
                    validacao_termo_compromisso=Inscricao.PENDENTE,
                    aluno__curso_campus__diretoria__setor__uo=get_uo(request.user),
                ).exclude(termo_compromisso_digitalizado='')
            else:
                return queryset.filter(validacao_termo_compromisso=self.value())


class DocEspecificaPendenteFilter(admin.SimpleListFilter):
    title = 'Documentação específica pendente de aprovação'
    parameter_name = 'doc_especifica_pendente'

    def lookups(self, request, model_admin):
        return [('Sim', 'Sim'), ('Não', 'Não')]

    def queryset(self, request, queryset):
        if self.value():
            docs = DocumentoInscricaoAluno.objects.filter(validado=None).exclude(inscricao_caracterizacao=None)
            if self.value() == 'Sim':
                return queryset.filter(aluno__in=docs.values_list('aluno', flat=True))
            elif self.value() == 'Não':
                return queryset.exclude(aluno__in=docs.values_list('aluno', flat=True))


class InscricaoAdmin(ModelAdminPlus):
    list_display = (
        'get_aluno',
        'get_programa',
        'data_cadastro',
        'get_situacao',
        'get_documentada',
        'get_situacao_parecer',
        'get_participacao',
        'get_opcoes',
    )
    list_filter = (
        'programa__instituicao',
        ProgramaFilter,
        'programa__tipo_programa',
        EditalFilter,
        PeriodoInscricaoFilter,
        'ativa',
        DocumentacaoFilter,
        RendaFilter,
        CursoFilter,
        ProgramaSocialFilter,
        EscolaPublicaFilter,
        ResponsavelFinanceiroFilter,
        ModalidadeFilter,
        OutrosProgramasFilter,
        ParticipanteProgramaDaInscricaoFilter,
        AnoLetivoFilter,
        PeriodoLetivoFilter,
        TurnoFilter,
        'situacao_parecer',
        ValidacaoTermoFilter,
        DocEspecificaPendenteFilter,
        'entrega_doc_atualizada_por',
        'parecer_autor_vinculo',
    )
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    date_hierarchy = 'data_cadastro'
    exclude = ('ativa', 'documentada', 'prioritaria', 'data_documentacao')
    list_display_icons = True

    ordering = ('-data_cadastro',)

    form = InscricaoModelForm

    actions = [
        'registrar_entrega_documentacao',
        'registrar_ausencia_documentacao',
        'registrar_parecer_deferido',
        'registrar_parecer_indeferido',
        'registrar_parecer_deferido_sem_recurso',
        'ativar_inscricao',
        'inativar_inscricao',
    ]
    actions_on_top = True
    actions_on_bottom = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_display_links = None

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def change_view(self, request, object_id, form_url='', extra_context=None):
        raise PermissionDenied

    def changelist_view(self, request, extra_context=None):
        list_filter = self.list_filter
        if request.GET.get('progrinstituicao') and request.GET.get('progrinstituicao') == '1':
            if ParticipanteProgramaFilter not in list_filter:
                lista = list(self.list_filter)
                lista.insert(14, ParticipanteProgramaFilter)
                list_filter = tuple(lista)
        elif ParticipanteProgramaFilter in list_filter:
            lista = list(self.list_filter)
            try:
                lista.pop(15)
            except Exception:
                pass
            list_filter = tuple(lista)
        if (
            request.GET.get('programa')
            and Programa.objects.filter(id=request.GET.get('programa'), tipo_programa__sigla=Programa.TIPO_IDIOMA).exists()
        ):
            if PrimeiraOpcaoFilter not in list_filter:
                list_filter += (PrimeiraOpcaoFilter, SegundaOpcaoFilter)
        if request.GET.get('anoletivo') and request.GET.get('periodoletivo'):
            if TurnoFilter not in list_filter:
                list_filter += (TurnoFilter, SituacaoMatriculaPeriodoFilter)
        self.list_filter = list_filter
        if not request.user.has_perm('ae.pode_ver_comprovante_inscricao'):
            if 'get_opcoes' in self.list_display:
                self.list_display = list(self.list_display)
                self.list_display.remove('get_opcoes')
        elif 'get_opcoes' not in self.list_display:
            self.list_display = [*self.list_display, 'get_opcoes']
        return super().changelist_view(request, extra_context=extra_context)

    def has_change_permission(self, request, obj=None):
        return False

    def get_aluno(self, obj):
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}">({obj.aluno.matricula})</a>')

    get_aluno.admin_order_field = 'aluno__pessoa_fisica__nome'
    get_aluno.short_description = 'Aluno'

    def get_programa(self, obj):
        return mark_safe(f'<a href="{obj.programa.get_absolute_url()}">{obj.programa}</a>')

    get_programa.short_description = 'Programa'

    def get_action_bar(self, request):
        items = []
        if request.user.has_perms(Inscricao.PERMS_EFETUAR_INSCRICAO):
            items.append({'url': '/ae/inscricao_identificacao/', 'label': 'Efetuar Inscrição', 'css_class': 'success'})
        return items

    def get_actions(self, request):
        if in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            return super().get_actions(request)
        return []

    def add_view(self, request):
        return httprr('/ae/inscricao_identificacao/')

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/admin/ae/inscricao/'
        return result

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        Aluno = apps.get_model('edu', 'aluno')
        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            if in_group(request.user, 'Assistente Social'):
                qs = qs.filter(programa__instituicao=get_uo(request.user))
            else:
                qs = qs.filter(aluno=Aluno.objects.get(matricula=request.user.get_relacionamento().matricula))
        return qs.select_related('aluno', 'programa', 'programa__instituicao', 'programa__tipo_programa')

    def get_situacao(self, obj):
        return mark_safe(obj.ativa and '<span class="status status-ativa">Ativa</span>' or '<span class="status status-inativa">Inativa</span>')

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'ativa'

    def get_documentada(self, obj):
        return obj.aluno.get_situacao_documentacao()

    get_documentada.short_description = 'Documentação'
    get_documentada.admin_order_field = 'documentada'

    def get_participacao(self, obj):
        return mark_safe(
            obj.get_participacao_aberta()
            and '<span class="status status-participante">Participante</span>'
            or '<span class="status status-error">Não participante</span>'
        )

    get_participacao.short_description = 'Participação'

    def get_prioritaria(self, obj):
        return mark_safe(
            obj.prioritaria and '<span class="status status-alert">Prioritária</span>' or '<span class="status status-info">Normal</span>'
        )

    get_prioritaria.short_description = 'Prioridade'
    get_prioritaria.admin_order_field = 'prioritaria'

    def get_selecionada(self, obj):
        return mark_safe(obj.selecionada and '<span class="status status-success">Sim</span>' or '<span class="status status-error">Não</span>')

    get_selecionada.short_description = 'Seleção'
    get_selecionada.admin_order_field = 'selecionada'

    def get_situacao_parecer(self, obj):
        if (
            self.request.user.has_group_cached(['Aluno'])
            and obj.periodo_inscricao
            and obj.periodo_inscricao.data_resultado
            and obj.periodo_inscricao.data_resultado > datetime.datetime.now()
        ):
            return mark_safe(status(Inscricao.SEM_PARECER))
        return mark_safe(status(obj.situacao_parecer))

    get_situacao_parecer.short_description = 'Parecer'

    def get_opcoes(self, obj):
        if self.request.user.has_group_cached(['Assistente Social', 'Coordenador de Atividades Estudantis Sistêmico']):
            texto = '<ul class="action-bar">'
            if obj.possui_parecer:
                texto += f'<li><a href="/ae/parecer_inscricao/{obj.pk:d}/" class="btn primary"><span class="fas fa-edit" aria-hidden="true"></span> Editar Parecer</a></li>'
            else:
                texto += f'<li><a href="/ae/parecer_inscricao/{obj.pk:d}/" class="btn success"><span class="fas fa-plus" aria-hidden="true"></span> Adicionar Parecer</a></li>'

            texto += (
                f'<li><a href="/ae/documentacao_pendente/{obj.aluno.pk}/{obj.id}/" class="btn"><span class="fas fa-folder" aria-hidden="true"></span> Documentação</a></li>'
                f'<li><a href="/ae/comprovante_inscricao/{obj.pk}/" class="btn default"><span class="fas fa-file-alt" aria-hidden="true"></span> Comprovante de Inscrição</a></li>'
            )
            if obj.termo_compromisso_digitalizado:
                texto += f'<li><a href="{obj.termo_compromisso_digitalizado.url}" class="btn default"><span class="fas fa-file-alt" aria-hidden="true"></span> Termo de Compromisso</a></li>'
            elif obj.id_documento_termo_compromisso and obj.validacao_termo_compromisso == Inscricao.VALIDADO:
                texto += f'<li><a href="/documento_eletronico/visualizar_documento/{obj.id_documento_termo_compromisso}/" class="btn default"><span class="fas fa-file-alt" aria-hidden="true"></span> Termo de Compromisso</a></li>'

            if obj.termo_compromisso_digitalizado and obj.validacao_termo_compromisso == Inscricao.PENDENTE:
                texto += f'<li><a href="/ae/validar_termo_compromisso/{obj.pk:d}/" class="btn success"><span class="fas fa-plus" aria-hidden="true"></span> Validar Termo de Compromisso</a></li>'
            if HistoricoAlteracaoParecer.objects.filter(inscricao=obj).exists():
                texto += f'<li><a href="/ae/historico_parecer/{obj.pk:d}/" class="btn default popup"><span class="fas fa-history" aria-hidden="true"></span>Histórico de Parecer</a></li>'
            if HistoricoAlteracaoTermoCompromisso.objects.filter(inscricao=obj).exists():
                texto += f'<li><a href="/ae/historico_termo_compromisso/{obj.pk:d}/" class="btn default popup"><span class="fas fa-history" aria-hidden="true"></span>Histórico de Termo de Compromisso</a></li>'
            texto += '</ul>'
        else:
            texto = '-'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    # Actions -----------------------------------------------------------------
    def adicionar_lista_selecionados(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.count()
        count = queryset.filter(selecionada=False).update(selecionada=True)

        if total == count:
            mensagem = 'Inclusão na lista de selecionadas realizada com sucesso.'
            tag = messages.SUCCESS
        elif total == 1:  # count == 0
            mensagem = 'A inscrição não pôde ser incluída na lista de selecionadas.'
            tag = messages.ERROR
        else:
            mensagem = f'{count} de {total} inscrições incluídas na lista de selecionadas com sucesso.'
            tag = messages.SUCCESS

        self.message_user(request, mensagem, level=tag)

    adicionar_lista_selecionados.short_description = 'Adicionar à lista de selecionadas'

    def remover_lista_selecionados(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.filter(selecionada=True).update(selecionada=False)

        if total == 0:
            mensagem = 'Nenhuma inscrição foi removida da lista de selecionadas.'
        elif total == 1:
            mensagem = '1 inscrição foi removida da lista de selecionadas com sucesso.'
        else:
            mensagem = f'{total:d} inscrições removidas da lista de selecionadas com sucesso.'

        self.message_user(request, mensagem)

    remover_lista_selecionados.short_description = 'Remover da lista de selecionadas'

    def adicionar_lista_prioridade(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.count()
        count = queryset.filter(aluno__documentada=True, prioritaria=False).update(prioritaria=True)

        if total == count:
            mensagem = 'Inclusão na lista de prioridades realizada com sucesso.'
            tag = messages.SUCCESS
        elif total == 1:  # count == 0
            mensagem = 'A inscrição não pôde ser incluída na lista de prioridades, pois para isso é necessário que a documentação tenha sido previamente entregue.'
            tag = messages.ERROR
        else:
            mensagem = f'{count} de {total} inscrições incluídas na lista de prioridades com sucesso. Para essa operação é necessário que a documentação tenha sido entregue.'
            tag = messages.SUCCESS

        self.message_user(request, mensagem, level=tag)

    adicionar_lista_prioridade.short_description = 'Adicionar à lista de prioridades'

    def remover_lista_prioridade(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.filter(prioritaria=True).update(prioritaria=False)

        if total == 0:
            mensagem = 'Nenhuma inscrição foi removida da lista de prioridades.'
        elif total == 1:
            mensagem = '1 inscrição foi removida da lista de prioridades com sucesso.'
        else:
            mensagem = f'{total:d} inscrições removidas da lista de prioridades com sucesso.'

        self.message_user(request, mensagem)

    remover_lista_prioridade.short_description = 'Remover da lista de prioridades'

    def registrar_entrega_documentacao(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/ae/informar_data_entrega_documentacao/?ids={}'.format(','.join(selected)))

    registrar_entrega_documentacao.short_description = 'Validar documentação'

    def registrar_ausencia_documentacao(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/ae/informar_ausencia_documentacao/?ids={}'.format(','.join(selected)))

    registrar_ausencia_documentacao.short_description = 'Invalidar documentação'

    def ativar_inscricao(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        for inscricao in queryset:
            inscricao.ativa = True
            inscricao.save()
        self.message_user(request, 'Ativação registrada com sucesso.')

    ativar_inscricao.short_description = 'Ativar inscrição'

    def inativar_inscricao(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        atendidas = 0
        impedidas = 0
        for inscricao in queryset:
            if inscricao.get_participacao_aberta():
                impedidas += 1
            else:
                atendidas += 1
                inscricao.ativa = False
                inscricao.save()

        mensagem = ''
        if atendidas > 1:
            mensagem = f'{atendidas} inscrições inativadas.'
            tag = messages.SUCCESS
        elif atendidas == 1:
            mensagem = f'{atendidas} inscrição inativada.'
            tag = messages.SUCCESS

        if impedidas == 1:
            mensagem = f'{mensagem} {impedidas} inscrição não foi inativada porque o aluno é participante do programa.'
            tag = messages.ERROR
        if impedidas > 1:
            mensagem = f'{mensagem} {impedidas} inscricões não foram inativadas porque os alunos são participantes dos programas.'
            tag = messages.ERROR
        if mensagem:
            self.message_user(request, mensagem, level=tag)

    inativar_inscricao.short_description = 'Inativar inscrição'

    def registrar_parecer_deferido(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return
        total = queryset.count()
        for inscricao in queryset:
            inscricao.salvar_parecer(request, Inscricao.DEFERIDO)

        mensagem = f'{total:d} inscriç{pluralize(total, "ão,ões")} registrada{pluralize(total)} com parecer deferido.'

        self.message_user(request, mensagem)

    registrar_parecer_deferido.short_description = 'Alterar Parecer para Deferido'

    def registrar_parecer_indeferido(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.count()
        for inscricao in queryset:
            inscricao.salvar_parecer(request, Inscricao.INDEFERIDO)

        mensagem = f'{total:d} inscriç{pluralize(total, "ão,ões")} registrada{pluralize(total)} com parecer indeferido.'

        self.message_user(request, mensagem)

    registrar_parecer_indeferido.short_description = 'Alterar Parecer para Indeferido'

    def registrar_parecer_deferido_sem_recurso(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        total = queryset.count()
        for inscricao in queryset:
            inscricao.salvar_parecer(request, Inscricao.DEFERIDO_SEM_RECURSO)

        mensagem = f'{total:d} inscriç{pluralize(total, "ão,ões")} registrada{pluralize(total)} com parecer deferido mas sem recurso disponível.'

        self.message_user(request, mensagem)

    registrar_parecer_deferido_sem_recurso.short_description = 'Alterar Parecer para Deferido mas sem recurso disponível'


admin.site.register(Inscricao, InscricaoAdmin)


class TipoAtendimentoSetorAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    ordering = ('nome',)
    search_fields = ('nome', 'descricao')
    list_display_icons = True


admin.site.register(TipoAtendimentoSetor, TipoAtendimentoSetorAdmin)


class AtendimentoSetorAdmin(ModelAdminPlus):
    form = AtendimentoSetorForm
    list_display = ('campus', 'tipoatendimentosetor', 'data', 'data_termino', 'valor', 'numero_processo', 'atualizado_por', 'atualizado_em')
    ordering = ('campus', '-data', 'tipoatendimentosetor')
    list_filter = ('tipoatendimentosetor',)
    list_display_icons = True
    date_hierarchy = 'data'
    search_fields = ('tipoatendimentosetor__nome', 'tipoatendimentosetor__descricao', 'observacao', 'numero_processo')

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.pode_detalhar_programa_todos'):
            list_filter = ('campus', 'tipoatendimentosetor')
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(AtendimentoSetor, AtendimentoSetorAdmin)


class DemandaAlunoAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'custeio', 'atualizado_por', 'atualizado_em', 'ativa')
    list_filter = (
        'eh_kit_alimentacao',
        'ativa',
    )
    search_fields = ('nome', 'descricao', 'custeio', 'ativa')
    list_display_icons = True
    add_exclude = ('atualizado_em', 'atualizado_por')

    def add_view(self, *args, **kwargs):
        self.exclude = getattr(self, 'add_exclude', ())
        return super().add_view(*args, **kwargs)

    def change_view(self, *args, **kwargs):
        self.exclude = getattr(self, 'add_exclude', ())
        return super().change_view(*args, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(DemandaAluno, DemandaAlunoAdmin)


class CategoriaAlimentacaoAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao')
    search_fields = ('nome', 'descricao')
    list_display_icons = True


admin.site.register(CategoriaAlimentacao, CategoriaAlimentacaoAdmin)


class CategoriaBolsaAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'tipo_bolsa', 'ativa')
    search_fields = ('nome', 'descricao')
    list_filter = ('tipo_bolsa', 'ativa')
    list_display_icons = True


admin.site.register(CategoriaBolsa, CategoriaBolsaAdmin)


class IdiomaAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    search_fields = ('descricao',)


admin.site.register(Idioma, IdiomaAdmin)


class DemandaAlunoFilter(admin.SimpleListFilter):
    title = 'Tipo de Atendimento'
    parameter_name = 'demanda'

    def lookups(self, request, model_admin):
        return DemandaAluno.ativas.values_list('id', 'nome')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(demanda=self.value())


class DemandaAlunoAtendidaAdmin(ModelAdminPlus):
    list_display = (
        'get_acoes',
        'demanda',
        'get_aluno',
        'data',
        'get_quantidade',
        'valor',
        'responsavel_vinculo',
        'data_registro',
        'terminal',
        'get_arquivo',
    )
    date_hierarchy = 'data'
    ordering = ('-data',)
    list_filter = (DemandaAlunoFilter, 'demanda__eh_kit_alimentacao', 'terminal')
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    form = DemandaAlunoAtendidaModelForm
    list_display_icons = False
    list_per_page = 40

    def get_acoes(self, obj):
        texto = icon('view', f'/ae/atendimento/{obj.id:d}/')
        if self.request.user.has_perm('ae.change_demandaalunoatendida') and (
            not self.request.user.has_group_cached('Bolsista do Serviço Social') or self.request.user.get_vinculo() == obj.responsavel_vinculo
        ):
            texto = texto + icon('edit', f'/admin/ae/demandaalunoatendida/{obj.id:d}/change/')
        texto = texto + '</ul>'

        return mark_safe(texto)

    get_acoes.short_description = 'Ações'

    def get_aluno(self, obj):
        if self.request.user.has_group_cached('Nutricionista'):
            texto = f'{obj.aluno.pessoa_fisica.nome} ({obj.aluno.matricula})'
        else:
            texto = f'{obj.aluno.pessoa_fisica.nome} <a href="{obj.aluno.get_absolute_url()}">({obj.aluno.matricula})</a>'
        if obj.demanda_id in [DemandaAluno.CAFE, DemandaAluno.ALMOCO, DemandaAluno.JANTAR] and not obj.aluno.pessoa_fisica.template:
            texto += '<span class="status status-error">Sem digital cadastrada</span>'
        return mark_safe(texto)

    get_aluno.short_description = 'Aluno'

    def get_quantidade(self, obj):
        return f'{obj.quantidade}'.replace('.0', '')

    get_quantidade.short_description = 'Quantidade'
    get_quantidade.admin_order_field = 'quantidade'

    def get_arquivo(self, obj):
        if obj.arquivo:
            return mark_safe(f"<a href='{obj.arquivo.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_arquivo.short_description = 'Arquivo'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            qs = qs.filter(campus=get_uo(request.user))
            if request.user.has_group_cached('Nutricionista'):
                qs = qs.filter(demanda__in=[DemandaAluno.CAFE, DemandaAluno.ALMOCO, DemandaAluno.JANTAR]) | qs.filter(
                    demanda__eh_kit_alimentacao=True
                )
            if request.user.has_group_cached('Coordenador de Atividades Estudantis') and not request.user.has_group_cached(
                ['Coordenador de Atividades Estudantis Sistêmico', 'Bolsista do Serviço Social', 'Assistente Social']
            ):
                qs = qs.filter(demanda__eh_kit_alimentacao=True)
        return qs.filter(demanda__ativa=True)

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            list_display = (*list_display, 'campus')
        return list_display

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            list_filter = ('demanda', 'campus', 'demanda__eh_kit_alimentacao', 'terminal')
        return list_filter

    def changelist_view(self, request, extra_context=None):
        if get_uo(request.user):
            return super().changelist_view(request, extra_context)
        raise PermissionDenied('Usuário não tem Setor SUAP.')

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('ae.change_demandaalunoatendida') or (
                request.user.has_group_cached('Bolsista do Serviço Social') and request.user.get_vinculo() != obj.responsavel_vinculo
            ):
                retorno = False
        return retorno

    def has_delete_permission(self, request, obj=None):
        retorno = super().has_delete_permission(request)
        if retorno and obj is not None:
            if request.user.has_perm('ae.add_programa') or obj.campus == get_uo(request.user):
                return True
        return False

    def delete_view(self, request, object_id):
        result = super().delete_view(request, object_id)
        result['Location'] = '/ae/lista_alunodemandaatendida/'
        return result


admin.site.register(DemandaAlunoAtendida, DemandaAlunoAtendidaAdmin)


class OfertaAlimentacaoAdmin(ModelAdminPlus):
    form = OfertaAlimentacaoForm
    list_display = (
        'get_campus',
        'dia_inicio',
        'dia_termino',
        'cafe_seg',
        'cafe_ter',
        'cafe_qua',
        'cafe_qui',
        'cafe_sex',
        'almoco_seg',
        'almoco_ter',
        'almoco_qua',
        'almoco_qui',
        'almoco_sex',
        'janta_seg',
        'janta_ter',
        'janta_qua',
        'janta_qui',
        'janta_sex',
        'situacao_ocasional',
        'get_arquivo_situacao_ocasional',
    )
    list_display_icons = True
    date_hierarchy = 'dia_inicio'
    fieldsets = (
        ('Localização', {'fields': (('campus',),)}),
        ('Período da Oferta', {'fields': (('dia_inicio', 'dia_termino'),)}),
        ('Café da manhã', {'fields': (('cafe_seg', 'cafe_ter', 'cafe_qua', 'cafe_qui', 'cafe_sex'),)}),
        ('Almoço', {'fields': (('almoco_seg', 'almoco_ter', 'almoco_qua', 'almoco_qui', 'almoco_sex'),)}),
        ('Jantar', {'fields': (('janta_seg', 'janta_ter', 'janta_qua', 'janta_qui', 'janta_sex'),)}),
        (
            'Situação Ocasional',
            {
                'fields': (
                    'situacao_ocasional',
                    'arquivo_situacao_ocasional',
                )
            },
        ),
    )

    def get_campus(self, obj):
        return obj.campus.setor.nome

    get_campus.short_description = 'Campus'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_group_cached('Nutricionista'):
            if get_uo(request.user).setor.sigla != get_sigla_reitoria():
                qs = qs.filter(campus=get_uo(request.user))
        else:
            if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
                qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.pode_detalhar_programa_todos'):
            list_filter = ('campus',)

        return list_filter

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['campus'].queryset = UnidadeOrganizacional.objects.uo()
        return form

    def get_arquivo_situacao_ocasional(self, obj):
        if obj.arquivo_situacao_ocasional:
            return mark_safe(f"<a href='{obj.arquivo_situacao_ocasional.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_arquivo_situacao_ocasional.short_description = 'Situação Ocasional (evidências)'


admin.site.register(OfertaAlimentacao, OfertaAlimentacaoAdmin)


class OfertaValorRefeicaoAdmin(ModelAdminPlus):
    form = OfertaValorRefeicaoForm
    list_display = ('campus', 'get_valor', 'data_inicio', 'data_termino')
    ordering = ('campus', 'data_inicio')
    list_filter = ('campus',)
    list_display_icons = True
    date_hierarchy = 'data_inicio'

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            list_filter = ()
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def get_valor(self, obj):
        return format_money(obj.valor)

    get_valor.short_description = 'Valor Unitário (R$)'


admin.site.register(OfertaValorRefeicao, OfertaValorRefeicaoAdmin)


class OfertaTurmaAdmin(ModelAdminPlus):
    form = OfertaTurmaForm
    list_display = ('campus', 'idioma', 'turma', 'dia1', 'dia2', 'horario1', 'horario2', 'professor', 'ativa', 'numero_vagas')
    ordering = ('ano', 'semestre')
    list_filter = ('campus', 'idioma', 'ano', 'semestre', 'ativa')
    search_fields = ('horario1', 'horario2', 'professor', 'turma')
    list_display_icons = True

    actions = ['ativar_oferta', 'inativar_oferta']
    actions_on_top = True
    actions_on_bottom = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
            list_filter = ('idioma', 'ano', 'semestre', 'ativa')
        return list_filter

    def get_actions(self, request):
        if in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            return super().get_actions(request)
        return []

    def ativar_oferta(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        queryset.update(ativa=True)

        self.message_user(request, 'Ativação registrada com sucesso.')

    ativar_oferta.short_description = 'Ativar oferta(s)'

    def inativar_oferta(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        queryset.update(ativa=False)

        self.message_user(request, 'Inativação registrada com sucesso.')

    inativar_oferta.short_description = 'Inativar oferta(s)'

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(OfertaTurma, OfertaTurmaAdmin)


class OfertaBolsaAdmin(ModelAdminPlus):
    form = OfertaBolsaForm
    list_display = ('get_setor', 'descricao_funcao', 'get_participante', 'campus', 'turno', 'disponivel', 'ativa')
    ordering = ('-disponivel',)
    list_filter = ('setor', 'campus', 'disponivel', 'ativa')
    search_fields = ('descricao_funcao',)
    list_display_icons = True

    actions = ['ativar_oferta', 'inativar_oferta']
    actions_on_top = True
    actions_on_bottom = True

    def get_setor(self, obj):
        return obj.setor.nome

    get_setor.short_description = 'Setor'

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
            list_filter = ('disponivel', 'ativa')
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_detalhar_programa_todos'):
            qs = qs.filter(setor__uo=get_uo(request.user))
        return qs

    def get_actions(self, request):
        if in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            return super().get_actions(request)
        return []

    def ativar_oferta(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        queryset.update(ativa=True)

        self.message_user(request, 'Ativação registrada com sucesso.')

    ativar_oferta.short_description = 'Ativar oferta(s)'

    def inativar_oferta(self, request, queryset):
        if not in_group(request.user, 'Assistente Social, Coordenador de Atividades Estudantis Sistêmico'):
            messages.error(request, 'Você não tem permissão para realizar este procedimento.')
            return

        queryset.update(ativa=False)

        self.message_user(request, 'Inativação registrada com sucesso.')

    inativar_oferta.short_description = 'Inativar oferta(s)'

    def get_participante(self, obj):
        texto = ''
        hoje = date.today()
        participacao = ParticipacaoTrabalho.objects.filter(
            Q(bolsa_concedida=obj), Q(participacao__data_termino__isnull=True) | Q(participacao__data_termino__gte=hoje)
        )
        if participacao.exists():
            registro = participacao[0]
            texto = texto + f'{registro.participacao.aluno.pessoa_fisica.nome}, desde {format_(registro.participacao.data_inicio)}'
        return mark_safe(texto)

    get_participante.short_description = 'Participante'

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(OfertaBolsa, OfertaBolsaAdmin)


class OfertaValorBolsaAdmin(ModelAdminPlus):
    form = OfertaValorBolsaForm
    list_display = ('campus', 'get_valor', 'data_inicio', 'data_termino')
    ordering = ('campus', '-data_inicio')
    list_filter = ('campus',)
    list_display_icons = True
    date_hierarchy = 'data_inicio'

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            list_filter = ()
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def get_valor(self, obj):
        return format_money(obj.valor)

    get_valor.short_description = 'Valor Mensal da Bolsa (R$)'


admin.site.register(OfertaValorBolsa, OfertaValorBolsaAdmin)


class OfertaPasseAdmin(ModelAdminPlus):
    form = OfertaPasseForm
    list_display = ('campus', 'get_valor_passe', 'data_inicio', 'data_termino')
    list_display_icons = True
    list_filter = ('campus',)
    date_hierarchy = 'data_inicio'
    ordering = ('campus', '-data_inicio')

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            list_filter = ()
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()

    def get_valor_passe(self, obj):
        return format_money(obj.valor_passe)

    get_valor_passe.short_description = 'Recurso Planejado (R$)'


admin.site.register(OfertaPasse, OfertaPasseAdmin)


class ValorTotalAuxiliosAdmin(ModelAdminPlus):
    form = ValorTotalAuxiliosForm
    list_display = ('campus', 'tipoatendimentosetor', 'get_valor', 'data_inicio', 'data_termino')
    ordering = ('campus', '-data_inicio')
    list_filter = ('campus', 'tipoatendimentosetor')
    list_display_icons = True
    date_hierarchy = 'data_inicio'

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            list_filter = ()
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_valor(self, obj):
        return format_money(obj.valor)

    get_valor.short_description = 'Recurso Planejado (R$)'


admin.site.register(ValorTotalAuxilios, ValorTotalAuxiliosAdmin)


class ValorTotalBolsasAdmin(ModelAdminPlus):
    form = ValorTotalBolsasForm
    list_display = ('campus', 'categoriabolsa', 'get_valor', 'data_inicio', 'data_termino')
    ordering = ('campus', '-data_inicio')
    list_filter = ('campus', 'categoriabolsa')
    list_display_icons = True
    date_hierarchy = 'data_inicio'

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            list_filter = ()
        return list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_financeiro_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_valor(self, obj):
        return format_money(obj.valor)

    get_valor.short_description = 'Recurso Planejado (R$)'


admin.site.register(ValorTotalBolsas, ValorTotalBolsasAdmin)


class AgendamentoRefeicaoAdmin(ModelAdminPlus):
    date_hierarchy = 'data'
    ordering = ('-data', 'aluno', 'tipo_refeicao')
    list_display = (
        'id',
        'get_aluno',
        'data',
        'tipo_refeicao',
        'atualizado_por',
        'atualizado_em',
        'cancelado',
        'cancelado_por',
        'cancelado_em',
        'get_opcoes',
    )
    list_display_icons = False
    list_display_links = None
    list_filter = ('programa__instituicao', 'tipo_refeicao', 'cancelado')
    list_per_page = 50
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    form = AgendamentoRefeicaoForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            return qs.filter(programa__instituicao=get_uo(request.user))

    def get_aluno(self, obj):
        if self.request.user.has_group_cached('Nutricionista'):
            return mark_safe(f'{obj.aluno.pessoa_fisica.nome} ({obj.aluno.matricula})')
        return mark_safe(f'{obj.aluno.pessoa_fisica.nome} <a href="/edu/aluno/{obj.aluno.matricula}/">({obj.aluno.matricula})</a>')

    get_aluno.short_description = 'Aluno'

    def get_opcoes(self, obj):
        super().get_queryset(self.request)
        hoje = datetime.datetime.today()
        if (
            not obj.cancelado
            and obj.data >= datetime.datetime(hoje.year, hoje.month, hoje.day, 0, 0, 0)
            and self.request.user.has_perm('ae.add_solicitacaoalimentacao')
        ):
            return mark_safe(f'<a href="/ae/remover_agendamento_refeicao/?id={obj.pk}" class="btn danger">Cancelar</a>')
        return mark_safe('-')

    get_opcoes.short_description = 'Opções'

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(AgendamentoRefeicao, AgendamentoRefeicaoAdmin)


class HorarioSolicitacaoRefeicaoAdmin(ModelAdminPlus):
    form = HorarioSolicitacaoForm
    list_display = ('uo', 'tipo_refeicao', 'hora_inicio', 'dia_inicio', 'hora_fim', 'dia_fim')
    list_filter = ('uo',)
    list_display_icons = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            return qs.filter(uo=get_uo(request.user))

    def has_add_permission(self, request):
        return request.user.has_perm('ae.pode_ver_listas_campus')

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('ae.pode_ver_listas_campus'):
                retorno = False
        return retorno

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(HorarioSolicitacaoRefeicao, HorarioSolicitacaoRefeicaoAdmin)


class HorarioJustificativaFaltaAdmin(ModelAdminPlus):
    form = HorarioSolicitacaoForm
    list_display = ('uo', 'tipo_refeicao', 'hora_inicio', 'dia_inicio', 'hora_fim', 'dia_fim')
    list_filter = ('uo',)
    list_display_icons = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            uo = request.user.get_vinculo().setor.uo
            return qs.filter(uo=uo)

    def has_add_permission(self, request):
        return request.user.has_perm('ae.pode_ver_listas_campus')

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('ae.pode_ver_listas_campus'):
                retorno = False
        return retorno

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(HorarioJustificativaFalta, HorarioJustificativaFaltaAdmin)


class CampusFilter(SimpleListModelFilter):
    title = 'Campus'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            campus = UnidadeOrganizacional.objects.uo().all()
        else:
            campus_usuario = get_uo(request.user)
            if campus_usuario:
                campus = UnidadeOrganizacional.objects.uo().filter(id=campus_usuario.id)
            else:
                campus = UnidadeOrganizacional.objects.none()
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(aluno__curso_campus__diretoria__setor__uo=self.value())


class JustificadaFilter(admin.SimpleListFilter):
    title = 'Justificada'
    parameter_name = 'justificada'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Sim'), ('2', 'Não'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(justificativa__isnull=False)
        elif self.value() == '2':
            return queryset.filter(justificativa__isnull=True)


class CategoriaFilter(admin.SimpleListFilter):
    title = 'Categoria'
    parameter_name = 'categoria'

    def lookups(self, request, model_admin):
        opcoes = (('1', 'Participantes'), ('2', 'Agendados'))

        return opcoes

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(participacao__isnull=False)
        elif self.value() == '2':
            return queryset.filter(participacao__isnull=True)


class HistoricoFaltasAlimentacaoAdmin(ModelAdminPlus):
    list_display = ('aluno', 'tipo_refeicao', 'data', 'justificativa', 'justificada_em')
    date_hierarchy = 'data'
    ordering = ('-data',)
    list_filter = (CampusFilter, 'tipo_refeicao', JustificadaFilter, CategoriaFilter)
    list_display_icons = False
    list_display_links = None
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            return qs.filter(aluno__curso_campus__diretoria__setor__uo=get_uo(request.user))

    def has_add_permission(self, request):
        return False


admin.site.register(HistoricoFaltasAlimentacao, HistoricoFaltasAlimentacaoAdmin)


class DatasLiberadasFaltasAlimentacaoAdmin(ModelAdminPlus):
    form = DatasLiberadasForm
    list_display = ('campus', 'data', 'recorrente', 'atualizado_por_vinculo', 'atualizado_em')
    ordering = ('campus', '-data')
    list_filter = ('campus', 'recorrente')
    list_display_icons = True
    list_display_links = None
    date_hierarchy = 'data'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            return qs.filter(campus=get_uo(request.user))

    def has_add_permission(self, request):
        return request.user.has_perm('ae.pode_ver_listas_campus')

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if retorno and obj is not None:
            if not request.user.has_perm('ae.pode_ver_listas_campus') and not request.user.has_perm('ae.add_programa'):
                retorno = False
        return retorno

    def save_model(self, request, obj, form, change):
        obj.atualizado_por_vinculo = request.user.get_vinculo()
        obj.atualizado_em = datetime.datetime.now()
        obj.save()


admin.site.register(DatasLiberadasFaltasAlimentacao, DatasLiberadasFaltasAlimentacaoAdmin)


class HistoricoSuspensoesCampusFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'descricao'

    def lookups(self, request, model_admin):
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            campus = UnidadeOrganizacional.objects.uo().all()
        else:
            campus = UnidadeOrganizacional.objects.uo().filter(id=get_uo(request.user).id)
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(participacao__aluno__curso_campus__diretoria__setor__uo=self.value())


class HistoricoSuspensoesAlimentacaoAdmin(ModelAdminPlus):
    list_display = ('get_aluno', 'data_inicio', 'data_termino', 'get_liberado_por_vinculo')
    date_hierarchy = 'data_inicio'
    ordering = ('-data_inicio',)
    list_filter = (HistoricoSuspensoesCampusFilter,)
    list_display_icons = False
    list_display_links = None
    search_fields = ('participacao__aluno__pessoa_fisica__nome', 'participacao__aluno__matricula')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.pode_ver_listas_todos'):
            return qs
        else:
            return qs.filter(participacao__aluno__curso_campus__diretoria__setor__uo=get_uo(request.user))

    def has_add_permission(self, request):
        return False

    def get_aluno(self, obj):
        return mark_safe(obj.participacao.aluno)

    get_aluno.short_description = 'Aluno'

    def get_liberado_por_vinculo(self, obj):
        return f'{obj.liberado_por_vinculo.pessoa.nome} - {obj.liberado_por_vinculo.relacionamento.matricula}'

    get_liberado_por_vinculo.short_description = 'Responsável pela Liberação'


admin.site.register(HistoricoSuspensoesAlimentacao, HistoricoSuspensoesAlimentacaoAdmin)


class TipoAtividadeDiversaAdmin(ModelAdminPlus):
    list_display = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True


admin.site.register(TipoAtividadeDiversa, TipoAtividadeDiversaAdmin)


class AtividadeDiversaAdmin(ModelAdminPlus):
    list_display = ('tipo', 'data_inicio', 'data_termino', 'cancelada', 'atualizado_por_vinculo', 'atualizado_em')
    list_filter = ('tipo', 'data_inicio', 'data_termino', 'cadastrado_por', 'cancelada')
    search_fields = ('observacao',)
    list_display_icons = True
    ordering = ('-data_inicio',)

    form = AtividadeDiversaForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_perm('ae.change_atividadediversa'):
            list_display += ('get_opcoes',)
        return list_display

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            list_filter = ('campus', *list_filter)
        return list_filter

    def get_opcoes(self, obj):
        texto = ''
        if self.request.user.has_perm('ae.change_atividadediversa'):
            if not obj.cancelada:
                texto = f'<ul class="action-bar"><li><a href="/ae/cancelar_atividade_diversa/{obj.pk}/" class="btn danger">Cancelar</a></li></ul>'
            else:
                texto = f'<ul class="action-bar"><li><a href="/ae/cancelar_atividade_diversa/{obj.pk}/" class="btn success">Ativar</a></li></ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por_vinculo = request.user.get_vinculo()
        obj.save()


admin.site.register(AtividadeDiversa, AtividadeDiversaAdmin)


class AcaoEducativaAdmin(ModelAdminPlus):
    list_display = ('titulo', 'data_inicio', 'data_termino', 'cancelada', 'atualizado_por_vinculo', 'atualizado_em', 'get_opcoes')
    list_filter = ('data_inicio', 'data_termino', 'cadastrado_por', 'cancelada')
    search_fields = ('titulo', 'descricao')
    list_display_icons = True
    ordering = ('-data_inicio',)

    form = AcaoEducativaForm

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            list_display += ('get_opcoes',)
        return list_display

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.has_perm('ae.pode_ver_relatorio_atendimento_todos'):
            list_filter = ('campus', *list_filter)
        return list_filter

    def get_opcoes(self, obj):
        texto = ''
        if self.request.user.has_perm('ae.change_acaoeducativa'):
            if not obj.cancelada:
                texto = f'<ul class="action-bar"><li><a href="/ae/cancelar_acao_educativa/{obj.pk}/" class="btn danger">Cancelar</a></li></ul>'
            else:
                texto = f'<ul class="action-bar"><li><a href="/ae/cancelar_acao_educativa/{obj.pk}/" class="btn success">Ativar</a></li></ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por_vinculo = request.user.get_vinculo()
        obj.save()


admin.site.register(AcaoEducativa, AcaoEducativaAdmin)


class CampusSolicitacaoRefeicaoFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'uo'

    def lookups(self, request, model_admin):
        if request.user.has_perm('ae.view_solicitacaorefeicaoaluno'):
            campus = UnidadeOrganizacional.objects.uo().all()
        else:
            campus = UnidadeOrganizacional.objects.uo().filter(id=get_uo(request.user).id)
        return campus.values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(programa__instituicao=self.value())


class SolicitacaoRefeicaoDeferidaFilter(admin.SimpleListFilter):
    title = 'Situação'
    parameter_name = 'situacao'

    def lookups(self, request, model_admin):
        OPCOES = (('1', 'Deferidas'), ('2', 'Indeferidas'), ('3', 'Aguardando Avaliação'))
        return OPCOES

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(deferida=True)
        elif self.value() == '2':
            return queryset.filter(deferida=False)
        if self.value() == '3':
            return queryset.filter(deferida__isnull=True)


class SolicitacaoRefeicaoAlunoAdmin(ModelAdminPlus):
    list_display = (
        'get_campus_aluno',
        'programa',
        'aluno',
        'data_auxilio',
        'data_solicitacao',
        'tipo_refeicao',
        'motivo_solicitacao',
        'get_deferida',
        'get_avaliador',
    )
    date_hierarchy = 'data_auxilio'
    ordering = ('-data_auxilio', '-data_solicitacao', 'programa', 'aluno')
    list_filter = (CampusSolicitacaoRefeicaoFilter, 'programa', 'tipo_refeicao', SolicitacaoRefeicaoDeferidaFilter)
    list_per_page = 50
    list_display_icons = False
    list_display_links = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.has_perm('ae.view_solicitacaorefeicaoaluno'):
            return qs
        else:
            return qs.filter(programa__instituicao=get_uo(request.user))

    def get_campus_aluno(self, obj):
        return obj.programa.instituicao

    get_campus_aluno.short_description = 'Campus'

    def get_avaliador(self, obj):
        if obj.avaliador_vinculo:
            return f'{obj.avaliador_vinculo.pessoa.nome} - {obj.avaliador_vinculo.relacionamento.matricula}'
        else:
            return '-'

    get_avaliador.short_description = 'Avaliador'

    def get_deferida(self, obj):
        if obj.deferida:
            return mark_safe('<span class="status status-success">Deferida</span>')
        elif obj.deferida is False:
            return mark_safe('<span class="status status-error">Indeferida</span>')
        elif obj.deferida is None:
            return mark_safe('<span class="status status-alert">Aguardando avaliação</span>')

    get_deferida.short_description = 'Situação'


admin.site.register(SolicitacaoRefeicaoAluno, SolicitacaoRefeicaoAlunoAdmin)


class EditalAdmin(ModelAdminPlus):
    list_display = ('descricao', 'get_tipos_programas', 'link_edital', 'ativo', 'get_opcoes')
    list_filter = ('ativo',)
    search_fields = ('descricao',)
    list_display_icons = True
    form = EditalForm

    def get_tipos_programas(self, obj):
        programas = []
        for programa in obj.tipo_programa.all():
            programas.append(programa.titulo)
        return ', '.join(programas)

    get_tipos_programas.short_description = 'Tipos de Programas'

    def get_opcoes(self, obj):
        texto = ''
        if self.request.user.has_perm('ae.add_edital'):
            texto = '<ul class="action-bar">'
            if obj.ativo:
                texto = texto + f'<li><a href="/ae/alterar_situacao_edital/{obj.pk:d}/" class="btn danger">Inativar</a></li>'
            else:
                texto = texto + f'<li><a href="/ae/alterar_situacao_edital/{obj.pk:d}/" class="btn success">Ativar</a></li>'
            texto += '</ul>'
        return mark_safe(texto)

    get_opcoes.short_description = 'Opções'


admin.site.register(Edital, EditalAdmin)


class PeriodoAtivoFilter(admin.SimpleListFilter):
    title = 'Ativo'
    parameter_name = 'ativo'

    def lookups(self, request, model_admin):
        OPCOES = (('1', 'Sim'), ('2', 'Não'))
        return OPCOES

    def queryset(self, request, queryset):
        hoje = datetime.datetime.now().date()
        if self.value() == '1':
            return queryset.filter(data_inicio__lte=hoje, data_termino__gte=hoje)
        elif self.value() == '2':
            return queryset.filter(Q(data_inicio__gt=hoje) | Q(data_termino__lt=hoje))


class PeriodoInscricaoAdmin(ModelAdminPlus):
    list_display = ('campus', 'edital', 'get_programa', 'data_inicio', 'data_termino', 'data_resultado', 'apenas_participantes')
    list_filter = ('campus', 'edital', PeriodoAtivoFilter)
    search_fields = ('edital__descricao',)
    list_display_icons = True
    ordering = ('-data_inicio',)
    form = PeriodoInscricaoForm

    def get_programa(self, obj):
        programas = []
        for programa in obj.programa.all():
            programas.append(programa.titulo)
        return ', '.join(programas)

    get_programa.short_description = 'Programas'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('inativar_inscricoes'):
            for programa in form.cleaned_data.get('programa'):
                Inscricao.objects.filter(programa=programa).update(ativa=False)
        obj.save()


admin.site.register(PeriodoInscricao, PeriodoInscricaoAdmin)


class MotivoSolicitacaoRefeicaoAdmin(ModelAdminPlus):
    list_display = (
        'descricao',
        'exibir_adicionar_participacao',
        'exibir_inscricao_programa',
        'exibir_solicitacao_refeicao',
        'exibir_agendamento_refeicao',
        'ativo',
    )
    list_filter = (
        'exibir_adicionar_participacao',
        'exibir_inscricao_programa',
        'exibir_solicitacao_refeicao',
        'exibir_agendamento_refeicao',
        'ativo',
    )
    ordering = ('-descricao',)
    list_display_icons = True
    search_fields = ('descricao',)


admin.site.register(MotivoSolicitacaoRefeicao, MotivoSolicitacaoRefeicaoAdmin)


class DatasRecessoFeriasAdmin(ModelAdminPlus):
    form = DatasRecessoFeriasForm
    list_display = ('campus', 'data', 'atualizado_por', 'atualizado_em')
    list_filter = ('campus',)
    ordering = ('campus', '-data')
    list_display_icons = True
    list_display_links = None
    date_hierarchy = 'data'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            qs = qs.filter(campus=get_uo(request.user))
        return qs

    def save_model(self, request, obj, form, change):
        obj.atualizado_em = datetime.datetime.now()
        obj.atualizado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(DatasRecessoFerias, DatasRecessoFeriasAdmin)


class TipoProgramaAdmin(ModelAdminPlus):
    list_display = ('titulo', 'descricao', 'exige_inscricao_alimentacao', 'ativo')
    list_filter = ('exige_inscricao_alimentacao',)
    ordering = ('titulo',)
    search_fields = ('titulo', 'descricao')
    list_display_icons = True
    form = TipoProgramaForm

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('modelo_documento'):
            obj.id_modelo_termo_compromisso = form.cleaned_data.get('modelo_documento').id
            obj.modelo_termo_indicado_por = request.user.get_vinculo()
        obj.save()


admin.site.register(TipoPrograma, TipoProgramaAdmin)


class PerguntaInscricaoProgramaAdmin(ModelAdminPlus):
    list_display = ('ordem', 'tipo_programa', 'pergunta', 'tipo_resposta', 'obrigatoria', 'deve_compor_analise', 'ativo')
    ordering = ('tipo_programa', 'pergunta')
    search_fields = ('pergunta__pergunta', 'descricao')
    list_filter = ('tipo_programa', 'tipo_resposta', 'obrigatoria', 'deve_compor_analise', 'ativo')
    list_display_icons = True


admin.site.register(PerguntaInscricaoPrograma, PerguntaInscricaoProgramaAdmin)


class OpcaoRespostaInscricaoProgramaAdmin(ModelAdminPlus):
    list_display = ('get_programa', 'pergunta', 'valor', 'ativo')
    ordering = ('pergunta',)
    search_fields = (
        'pergunta__pergunta',
        'valor',
    )
    list_filter = ('pergunta', 'ativo')
    list_display_icons = True
    form = OpcaoRespostaInscricaoProgramaForm

    def get_programa(self, obj):
        return obj.pergunta.tipo_programa.titulo

    get_programa.short_description = 'Programa'


admin.site.register(OpcaoRespostaInscricaoPrograma, OpcaoRespostaInscricaoProgramaAdmin)


class PerguntaParticipacaoAdmin(ModelAdminPlus):
    list_display = ('tipo_programa', 'pergunta', 'tipo_resposta', 'obrigatoria', 'eh_info_financeira', 'ativo')
    ordering = ('tipo_programa', 'pergunta')
    search_fields = ('pergunta',)
    list_filter = ('tipo_programa', 'tipo_resposta', 'obrigatoria', 'ativo')
    list_display_icons = True


admin.site.register(PerguntaParticipacao, PerguntaParticipacaoAdmin)


class OpcaoRespostaPerguntaParticipacaoAdmin(ModelAdminPlus):
    list_display = ('get_programa', 'pergunta', 'valor', 'ativo')
    ordering = ('pergunta',)
    search_fields = ('pergunta__pergunta', 'valor')
    list_filter = ('pergunta', 'ativo')
    list_display_icons = True
    form = OpcaoRespostaPerguntaParticipacaoForm

    def get_programa(self, obj):
        return obj.pergunta.tipo_programa.titulo

    get_programa.short_description = 'Programa'


admin.site.register(OpcaoRespostaPerguntaParticipacao, OpcaoRespostaPerguntaParticipacaoAdmin)


class TipoAuxilioEventualAdmin(ModelAdminPlus):
    list_display = ('nome', 'descricao', 'exige_comprovante', 'prazo_comprovante_utilizacao', 'ativo', 'get_campi_que_ofertam', 'get_opcoes')
    list_filter = ('ativo',)
    search_fields = ('nome', 'descricao', 'ativo')
    list_display_icons = True
    form = TipoAuxilioEventualForm

    def get_opcoes(self, obj):
        if obj.ativo:
            meu_campus = get_uo(self.request.user)
            texto = '<ul class="action-bar">'
            if meu_campus in obj.campi_que_ofertam.all():
                texto += f'<li><a href="/ae/gerenciar_oferta_auxilio_eventual/{obj.pk:d}/" class="btn danger">Excluir meu campus</a></li></ul>'
            else:
                texto += f'<li><a href="/ae/gerenciar_oferta_auxilio_eventual/{obj.pk:d}/" class="btn success">Incluir meu campus</a></li></ul>'
            texto += '</ul>'
            return mark_safe(texto)
        return '-'

    get_opcoes.short_description = 'Opções'

    def get_campi_que_ofertam(self, obj):
        return ', '.join([campus.sigla for campus in obj.campi_que_ofertam.all()])

    get_campi_que_ofertam.short_description = 'Campi que ofertam'


admin.site.register(TipoAuxilioEventual, TipoAuxilioEventualAdmin)


class ComprovanteAtrasadoFilter(admin.SimpleListFilter):
    title = 'Comprovantes em Atraso'
    parameter_name = 'comprovante_atraso'

    def lookups(self, request, model_admin):
        return [('Sim', 'Sim'), ('Não', 'Não')]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset

        queryset = queryset.filter(
            deferida=True,
            comprovacao_pendente=True,
        ).exclude(
            tipo_auxilio__prazo_comprovante_utilizacao=None,
        )
        vencimento_expr = ExpressionWrapper(
            F('data_avaliacao') + F('tipo_auxilio__prazo_comprovante_utilizacao') * datetime.timedelta(days=1), output_field=fields.DateTimeField()
        )
        queryset = queryset.annotate(vencimento=vencimento_expr)

        if self.value() == 'Sim':
            return queryset.filter(vencimento__lt=datetime.datetime.now())
        elif self.value() == 'Não':
            return queryset.filter(vencimento__gte=datetime.datetime.now())


class SolicitacaoAuxilioAlunoAdmin(ModelAdminPlus):
    list_display = (
        'get_campus',
        'get_aluno',
        'tipo_auxilio',
        'data_solicitacao',
        'get_comprovante',
        'get_situacao',
        'get_parecer_avaliacao',
        'get_comprovante_utilizacao',
        'get_comprovacao_validada',
        'get_opcoes',
    )
    ordering = ('aluno',)
    list_filter = (CampusFilter, 'deferida', 'comprovacao_pendente', 'comprovacao_validada', ComprovanteAtrasadoFilter)
    list_display_icons = True
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    form = SolicitacaoAuxilioAlunoForm
    date_hierarchy = 'data_solicitacao'

    def get_situacao(self, obj):
        if obj.deferida:
            return mark_safe('<span class="status status-success">Deferida</span>')
        elif obj.deferida is False:
            return mark_safe('<span class="status status-error">Indeferida</span>')
        elif obj.deferida is None:
            return mark_safe('<span class="status status-alert">Aguardando avaliação</span>')

    get_situacao.short_description = 'Situação'

    def get_aluno(self, obj):
        return mark_safe(f'<a href="/edu/aluno/{obj.aluno.matricula}/">{obj.aluno}</a>')

    get_aluno.short_description = 'Aluno'

    def get_campus(self, obj):
        return obj.aluno.curso_campus.diretoria.setor.uo

    get_campus.short_description = 'Campus'

    def get_comprovante(self, obj):
        if obj.comprovante:
            return mark_safe(f"<a href='{obj.comprovante.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_comprovante.short_description = 'Comprovantes'

    def get_comprovante_utilizacao(self, obj):
        if obj.comprovante_utilizacao:
            return mark_safe(f"<a href='{obj.comprovante_utilizacao.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_comprovante_utilizacao.short_description = 'Comprovante de Utilização'

    def get_parecer_avaliacao(self, obj):
        if obj.parecer_avaliacao:
            return mark_safe(
                '{} <small>{} em {}</small>'.format(obj.parecer_avaliacao, obj.avaliador_vinculo.pessoa.nome, obj.data_avaliacao.strftime('%d/%m/%Y'))
            )
        return '-'

    get_parecer_avaliacao.short_description = 'Parecer'

    def get_comprovacao_validada(self, obj):
        if obj.comprovante_cadastrado_em:
            if obj.comprovacao_validada:
                return mark_safe('<span class="status status-success">Sim</span>')
            elif obj.comprovante_avaliado_por:
                return mark_safe(f'<span class="status status-error">Não: {obj.parecer_avaliacao_comprovacao}</span>')
            else:
                return mark_safe('<span class="status status-alert">Aguardando</span>')
        elif obj.comprovacao_pendente:
            return mark_safe('<span class="status status-alert">Aguardando Comprovante</span>')
        else:
            return mark_safe('<span class="status status-info">Não se aplica</span>')

    get_comprovacao_validada.short_description = 'Comprovação validada'

    def get_opcoes(self, obj):
        if self.request.user.has_perm('ae.pode_abrir_inscricao_do_campus'):
            texto = '<ul class="action-bar">'
            if obj.deferida is None:
                texto = texto + f'<li><a href="/ae/avaliar_solicitacao_auxilio/{obj.pk:d}/" class="btn success">Avaliar</a></li></ul>'
            elif not obj.comprovante_utilizacao:
                texto = texto + f'<li><a href="/ae/avaliar_solicitacao_auxilio/{obj.pk:d}/" class="btn primary">Editar Avaliação</a></li></ul>'
            elif not obj.comprovacao_validada and not obj.comprovacao_pendente:
                texto = (
                    texto
                    + f'<li><a href="/ae/avaliar_comprovante_utilizacao_auxilio/{obj.pk:d}/" class="btn success">Avaliar comprovante</a></li></ul>'
                )

            return mark_safe(texto)
        else:
            if obj.comprovacao_pendente:
                return mark_safe(
                    f'<ul class="action-bar"><li><a href="/ae/adicionar_comprovante_solicitacao_auxilio/{obj.pk:d}/" class="btn success">Adicionar comprovante de utilização</a></li></ul>'
                )
        return '-'

    get_opcoes.short_description = 'Opções'

    def has_add_permission(self, request, obj=None):
        return request.user.eh_aluno and request.user.has_perm('ae.add_solicitacaoauxilioaluno')

    def has_change_permission(self, request, obj=None):
        retorno = super().has_change_permission(request, obj)
        if obj and not request.user.has_perm('ae.add_solicitacaoauxilioaluno'):
            retorno = False
        if obj and obj.aluno == request.user.get_relacionamento() and obj.deferida is not None:
            retorno = False
        return retorno

    def has_view_permission(self, request, obj=None):
        super().has_view_permission(request, obj)
        return (not request.user.has_perm('ae.add_solicitacaoauxilioaluno')) or (obj and obj.aluno == request.user.get_relacionamento())

    def add_view(self, request):
        if request.user.eh_aluno and request.user.has_perm('ae.add_solicitacaoauxilioaluno'):
            aluno = request.user.get_relacionamento()
            if not Caracterizacao.objects.filter(aluno=aluno).exists():
                return httprr(
                    f'/ae/caracterizacao/{aluno.pk}/', 'Por favor, efetue sua caracterização social antes de solicitar o auxílio.', tag='error'
                )
            else:
                return super().add_view(request)
        else:
            return httprr('/admin/ae/solicitacaoauxilioaluno/', 'Permissão negada.', tag='error')

    def save_model(self, request, obj, form, change):
        obj.aluno = request.user.get_relacionamento()
        obj.save()

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.has_perm('ae.add_solicitacaoauxilioaluno') and request.user.eh_aluno:
            qs = qs.filter(aluno=request.user.get_relacionamento())
        elif not request.user.has_perm('ae.add_programa'):
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo=get_uo(request.user))
        return qs


admin.site.register(SolicitacaoAuxilioAluno, SolicitacaoAuxilioAlunoAdmin)


class AuxilioEventualAdmin(ModelAdminPlus):
    form = AuxilioEventualForm
    list_display = ('campus', 'aluno', 'data', 'tipo_auxilio', 'quantidade', 'valor', 'responsavel', 'atualizado_em', 'observacao')
    date_hierarchy = 'data'
    ordering = ('-data',)
    list_filter = ('campus', 'tipo_auxilio')
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    list_display_icons = True
    list_per_page = 40

    def save_model(self, request, obj, form, change):
        obj.responsavel = request.user.get_vinculo()
        obj.atualizado_em = datetime.datetime.now()
        obj.save()


admin.site.register(AuxilioEventual, AuxilioEventualAdmin)


class SituacaoTrabalhoAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    list_display_links = None


admin.site.register(SituacaoTrabalho, SituacaoTrabalhoAdmin)


class TipoImovelResidencialAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('descricao', 'ativo')
    list_display_icons = True


admin.site.register(TipoImovelResidencial, TipoImovelResidencialAdmin)


class BeneficioGovernoFederalAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('descricao', 'ativo')
    list_display_icons = True


admin.site.register(BeneficioGovernoFederal, BeneficioGovernoFederalAdmin)


class ComprovanteParticipacaoAdmin(ModelAdminPlus):
    list_display = (
        'aluno',
        'programa',
        'tipo',
        'get_mes_ano',
        'pendente',
        'valido',
        'get_arquivo',
        'get_avaliado_por',
        'justificativa',
        'get_opcoes',
    )
    list_filter = (
        'campus',
        'tipo',
        'mes',
        'ano',
        'pendente',
    )
    search_fields = ('aluno__pessoa_fisica__nome', 'aluno__matricula')
    list_display_icons = False
    list_display_links = None

    def get_arquivo(self, obj):
        if obj.arquivo:
            return mark_safe(f"<a href='{obj.arquivo.url}' class='btn default'>Visualizar Arquivo</a>")
        return '-'

    get_arquivo.short_description = 'Arquivo'

    def get_opcoes(self, obj):
        if obj.arquivo and not obj.pendente:
            texto = '<ul class="action-bar">'
            if not obj.valido:
                texto = texto + f'<li><a href="/ae/validar_comprovante_mensal/{obj.pk:d}/" class="btn success">Validar</a></li>'
            texto = texto + f'<li><a href="/ae/invalidar_comprovante_mensal/{obj.pk:d}/" class="btn danger">Invalidar</a></li>'
            texto = texto + '</ul>'
            return mark_safe(texto)
        return '-'

    get_opcoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            qs = qs.filter(programa__instituicao_id=get_uo(request.user).id)
        return qs

    def get_avaliado_por(self, obj):
        if obj.avaliado_por:
            return mark_safe(f'{obj.avaliado_por.user}<br><small>em {obj.avaliado_em.strftime("%d/%m/%Y")}</small>')
        return '-'

    get_avaliado_por.short_description = 'Avaliador'

    def get_mes_ano(self, obj):
        return f'{obj.mes}/{obj.ano}'

    get_mes_ano.short_description = 'Mês/Ano'


admin.site.register(ComprovanteParticipacao, ComprovanteParticipacaoAdmin)


class AlteracaoParticipacaoAlimentacaoAdmin(ModelAdminPlus):
    list_display = ('get_aluno', 'get_dias', 'motivo', 'solicitada_em', 'deferida', 'avaliada_por', 'avaliada_em', 'justificativa', 'get_opcoes')
    list_filter = ('deferida',)
    search_fields = ('participacao__aluno__matricula',)
    list_display_icons = False
    list_display_links = None

    def get_aluno(self, obj):
        return mark_safe(obj.participacao.aluno)

    get_aluno.short_description = 'Aluno'

    def get_dias(self, obj):
        texto = ''
        if obj.solicitacao_cafe.valida():
            texto += f'<p>Café da manhã: {obj.solicitacao_cafe}</p>'
        if obj.solicitacao_almoco.valida():
            texto += f'<p>Almoço: {obj.solicitacao_almoco}</p>'
        if obj.solicitacao_jantar.valida():
            texto += f'<p>Jantar: {obj.solicitacao_jantar}</p>'
        return mark_safe(texto)

    get_dias.short_description = 'Dias Solicitados'

    def get_opcoes(self, obj):
        if obj.deferida is None:
            texto = f'<ul class="action-bar"><li><a href="/ae/deferir_solicitacao_alteracao/{obj.pk:d}/" class="btn success popup">Deferir</a></li>'
            texto = texto + f'<li><a href="/ae/indeferir_solicitacao_alteracao/{obj.pk:d}/" class="btn danger popup">Indeferir</a></li>'
            texto = texto + '</ul>'
            return mark_safe(texto)
        return '-'

    get_opcoes.short_description = 'Opções'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.filter(participacao__aluno__curso_campus__diretoria__setor__uo_id=get_uo(request.user).id)
        return qs


admin.site.register(AlteracaoParticipacaoAlimentacao, AlteracaoParticipacaoAlimentacaoAdmin)


class CriterioSelecaoProgramaAdmin(ModelAdminPlus):
    list_display = ('get_nomes_programas', 'criterio', 'opcao', 'pontuacao', 'gera_pontuacao', 'restritivo')
    list_filter = (
        'criterio',
        'gera_pontuacao',
        'restritivo',
    )
    search_fields = ('criterio', 'opcao')
    list_display_icons = True
    ordering = ['criterio', '-pontuacao']
    form = EditarCriterioSelecaoProgramaForm

    def add_view(self, request):
        return httprr('/ae/adicionar_criterio_selecao_programa/')

    def get_nomes_programas(self, obj):
        return obj.get_tipos_programas()

    get_nomes_programas.short_description = 'Tipo de Programa'


admin.site.register(CriterioSelecaoPrograma, CriterioSelecaoProgramaAdmin)


class ParametroSelecaoProgramaAdmin(ModelAdminPlus):
    list_display = ('uo', 'tipo_programa', 'get_parametro', 'pontuacao_minima')
    list_filter = ('tipo_programa', 'uo')
    search_fields = ('tipo_programa',)
    list_display_icons = True
    form = EditarParametroSelecaoProgramaForm
    ordering = [
        'uo',
        'tipo_programa',
        '-pontuacao_minima',
    ]

    def add_view(self, request):
        return httprr('/ae/adicionar_parametro_selecao_programa/')

    def get_parametro(self, obj):
        if obj.tipo_programa.sigla == Programa.TIPO_ALIMENTACAO:
            return f'Refeições sugeridas: {obj.dias_sugeridos}'
        else:
            return f'Porcentagem sugerida: {obj.porcentagem_sugerida}%'

    get_parametro.short_description = 'Parâmetro'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('ae.pode_ver_relatorio_inscricao_todos'):
            qs = qs.filter(uo_id=get_uo(request.user).id)
        return qs


admin.site.register(ParametroSelecaoPrograma, ParametroSelecaoProgramaAdmin)


class ImportacaoCadunicoAdmin(ModelAdminPlus):
    list_display = ('data_importacao', 'atualizar_todos_alunos', 'execucao_concluida', 'qtde_alunos_cadunico', 'qtde_alunos_nao_cadunico')
    list_filter = ('data_importacao', 'execucao_concluida')
    search_fields = ('data_importacao', 'qtde_alunos_cadunico', 'qtde_alunos_nao_cadunico')
    list_display_icons = False
    ordering = [
        '-data_importacao',
        'execucao_concluida',
    ]
    exclude = ['usuario_criacao', 'criado_em', 'qtde_alunos_cadunico', 'qtde_alunos_nao_cadunico', 'execucao_concluida']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.usuario_criacao = request.user.get_vinculo()

        obj.save()

    def _pode_gerenciar_importacao(self, request):
        return request.user.has_group_cached('Coordenador de Atividades Estudantis Sistêmico', 'Coordenador de Sistemas')

    def has_change_permission(self, request, obj=None):
        if not self._pode_gerenciar_importacao(request):
            return False
        return True if obj is None else not obj.execucao_concluida

    def has_delete_permission(self, request, obj=None):
        if not self._pode_gerenciar_importacao(request):
            return False
        return True if obj is None else not obj.execucao_concluida


admin.site.register(ImportacaoCadunico, ImportacaoCadunicoAdmin)


class TipoAreaResidencialAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True


admin.site.register(TipoAreaResidencial, TipoAreaResidencialAdmin)
