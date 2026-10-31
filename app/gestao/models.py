import datetime
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Avg, Min, Sum
from django.db.models.query_utils import Q

from cnpq.models import Artigo, Capitulo, Livro, TrabalhoEvento
from comum.models import Configuracao, User
from comum.utils import tl
from djtools import db
from djtools.db import models
from djtools.utils import eval_expr, mask_money, split_thousands
from edu.models import Aluno, ConfiguracaoGestao, CursoCampus, MatriculaPeriodo, Modalidade
from edu.models.cadastros_gerais import SituacaoMatricula
from financeiro.models import Evento, UnidadeGestora
from gestao.util import get_cache_expira
from gestao.variaveis_desempenho.variaveis_factory import VariavelFactory
from gestao.variaveis_desempenho.variaveis_gestao_pessoas import VariaveisGestaoPessoaBase
from processo_seletivo.models import Edital, OfertaVagaCurso
from rh.models import Funcao, PessoaFisica, Servidor, Situacao, UnidadeOrganizacional

# = = = = = = = = = =
# Grupos de Variáveis
# = = = = = = = = = =
VARIAVEIS_ACADEMICO_ALUNOS_TODOS = {
    'grupo': 'Academico',
    'subgrupo': 'AlunosTodos',
    'titulo': 'Acadêmico',
    'subtitulo': 'Todos os alunos',
    'variaveis': [
        'AM',
        'AM_NR',
        'AMPRES',
        'AMPRESF',
        'AMEAD',
        'AMF',
        'AMNF',
        'AMTEC',
        'AMTEC_EAD',
        'AMTEC_PRES',
        'AMGRAD',
        'AMGRAD_EAD',
        'AMGRAD_PRES',
        'AMLIC',
        'AMMEST',
        'AMEJA',
        'CO',
        'COPRES',
        'COEAD',
        'AC',
        'AE',
        'AR',
        'AJ',
        'AI',
        'AICOR',
        'AICOR_NR',
        'AIC',
    ],
}

VARIAVEIS_ACADEMICO_ALUNOS_COM_CONVENIO = {
    'grupo': 'Academico',
    'subgrupo': 'AlunosComConvenio',
    'titulo': 'Acadêmico',
    'subtitulo': 'Alunos com convênio',
    'variaveis': [
        'AM_EX',
        'AMPRES_EX',
        'AMPRESF_EX',
        'AMEAD_EX',
        'AMTEC_EX',
        'AMTEC_EAD_EX',
        'AMTEC_PRES_EX',
        'AMGRAD_EX',
        'AMGRAD_EAD_EX',
        'AMGRAD_PRES_EX',
        'AMLIC_EX',
        'AMMEST_EX',
        'AMEJA_EX',
        'COEAD_EX',
        'AC_EX',
        'AE_EX',
        'AI_EX',
        'AICOR_EX',
        'AIC_EX',
        'AJ_EX',
        'AR_EX',
    ],
}

VARIAVEIS_ACADEMICO_ALUNOS_SEM_CONVENIO = {
    'grupo': 'Academico',
    'subgrupo': 'AlunosSemConvenio',
    'titulo': 'Acadêmico',
    'subtitulo': 'Alunos sem convênio',
    'variaveis': [
        'AM_OR',
        'AMPRES_OR',
        'AMPRESF_OR',
        'AMEAD_OR',
        'AMTEC_OR',
        'AMTEC_EAD_OR',
        'AMTEC_PRES_OR',
        'AMGRAD_OR',
        'AMGRAD_EAD_OR',
        'AMGRAD_PRES_OR',
        'AMLIC_OR',
        'AMMEST_OR',
        'AMEJA_OR',
        'COEAD_OR',
        'AC_OR',
        'AE_OR',
        'AI_OR',
        'AICOR_OR',
        'AIC_OR',
        'AJ_OR',
        'AR_OR',
    ],
}

VARIAVEIS_ACADEMICO_ALUNOS_EQUIVALENTES = {
    'grupo': 'Academico',
    'subgrupo': 'AlunosEquivalentes',
    'titulo': 'Acadêmico',
    'subtitulo': 'Alunos equivalentes',
    'variaveis': ['AEQ', 'AEQ_PROEJA', 'AEQ_TECNICO', 'AEQ_DOCENTE', 'AEQ_FENC', 'IAEQ'],
}

VARIAVEIS_RH = VariaveisGestaoPessoaBase.VARIAVEIS

# DESATIVADA
# VARIAVEIS_FINANCEIRO = {'grupo': 'Financeiro',
#                         'titulo': 'Financeiro',
#                         'variaveis': ['GOC', 'GPE', 'GCO', 'GCA', 'GPA', 'GTO']}

VARIAVEIS_EXTENSAO = {'grupo': 'Extensao', 'titulo': 'Extensão', 'variaveis': ['DEE', 'TAEE', 'DISCEE']}

VARIAVEIS_PESQUISA = {'grupo': 'Pesquisa', 'titulo': 'Pesquisa', 'variaveis': ['NAA', 'NLA', 'NTA', 'NRA', 'NA', 'NL', 'NT', 'NR', 'DOAP']}

VARIAVEIS_PS = {'grupo': 'Ps', 'titulo': 'Processo Seletivo', 'variaveis': ['VO', 'I']}

VARIAVEIS_SOCIAL = {'grupo': 'Social', 'titulo': 'Socioeconômico', 'variaveis': ['RFP', 'AANF']}

VARIAVEIS_TI = {'grupo': 'Ti', 'titulo': 'Tecnologia da Informação', 'variaveis': ['C']}

VARIAVEIS_GRUPOS = [
    VARIAVEIS_ACADEMICO_ALUNOS_TODOS,
    VARIAVEIS_ACADEMICO_ALUNOS_COM_CONVENIO,
    VARIAVEIS_ACADEMICO_ALUNOS_SEM_CONVENIO,
    VARIAVEIS_ACADEMICO_ALUNOS_EQUIVALENTES,
    VARIAVEIS_RH,
    VARIAVEIS_EXTENSAO,
    VARIAVEIS_PESQUISA,
    VARIAVEIS_PS,
    VARIAVEIS_SOCIAL,
    VARIAVEIS_TI,
]


# Indicadores que foram desavitados na auditoria referente ao ano de 2015, atendendo a pedido de Anna Catharina.
# Obs: O indicador 'RAM (MEC)' foi desativado atendendo a pedido de Solange, em 28/12/2018.
INDICADORES_DESATIVADOS = ['GOC (TCU)', 'GI (TCU)', 'RAANF/AMNF', 'GCA', 'GP', 'PMTec (MEC)', 'PMEja (MEC)', 'PMFor (MEC)', 'CEad (MEC)', 'RAM (MEC)']


class PeriodoReferencia(models.ModelPlus):
    user = models.ForeignKeyPlus(User, on_delete=models.CASCADE)
    ano = models.PositiveIntegerField()
    data_base = models.DateFieldPlus()
    data_limite = models.DateFieldPlus()

    class Meta:
        verbose_name = 'Período de Referência'
        verbose_name_plural = 'Períodos de Referências'

        permissions = (
            ('pode_editar_meu_periodo_referencia', 'Pode editar meu período de referência'),
            ('pode_editar_periodo_referencia_global', 'Pode editar período de referência global'),
        )

    def save(self, *args, **kwargs):
        cache_key = PeriodoReferencia._get_cache_key(self.user)
        cache.delete(cache_key)
        super().save(*args, **kwargs)

    @staticmethod
    def _get_cache_key(user):
        user_pk = 0 if user is None else user.pk
        return f'gestao_periodo_{user_pk}'

    @staticmethod
    def set_cache(user, valor):
        cache_key = PeriodoReferencia._get_cache_key(user)
        cache.set(cache_key, valor, get_cache_expira())

    @staticmethod
    def get_cache(user):
        cache_key = PeriodoReferencia._get_cache_key(user)
        return cache.get(cache_key, None)

    @staticmethod
    def _get_referencia_sistema():
        periodo_referencia = PeriodoReferencia()
        ano = Configuracao.get_valor_por_chave('gestao', 'ano_referencia')
        data_base = Configuracao.get_valor_por_chave('gestao', 'data_inicio')
        data_limite = Configuracao.get_valor_por_chave('gestao', 'data_termino')
        if ano and data_base and data_limite:
            periodo_referencia.ano = int(ano)
            periodo_referencia.data_base = datetime.datetime.strptime(data_base, '%d/%m/%Y')
            periodo_referencia.data_limite = datetime.datetime.strptime(data_limite, '%d/%m/%Y')
            return periodo_referencia
        else:
            return None

    # Este metodo também é utilizado no modulo plan_estrategico para extrair valores das variáveis para o farol de desempenho
    @staticmethod
    def get_referencia(user=None):
        if not user:
            user = tl.get_user()

        periodo_referencia_cache = PeriodoReferencia.get_cache(user)
        if periodo_referencia_cache:
            periodo_referencia_pk = periodo_referencia_cache if isinstance(periodo_referencia_cache, int) else periodo_referencia_cache.pk
            periodo_referencia = PeriodoReferencia.objects.filter(pk=periodo_referencia_pk).first()
            if periodo_referencia:
                return periodo_referencia

        if user and user.is_authenticated:
            periodo_referencia = PeriodoReferencia.objects.filter(user=user)
            if periodo_referencia:
                periodo = periodo_referencia[0]
            else:
                ano = datetime.datetime.today().year
                data_base = datetime.date(ano, 4, 15)
                data_limite = datetime.date(ano, 10, 31)
                periodo = PeriodoReferencia.objects.get_or_create(user=tl.get_user(), data_base=data_base, data_limite=data_limite, ano=ano)[0]
        else:
            periodo = PeriodoReferencia._get_referencia_sistema()
        if periodo:
            pk = periodo.pk
        else:
            pk = 0
        PeriodoReferencia.set_cache(user, pk)
        return periodo

    @staticmethod
    def get_ano_referencia():
        return PeriodoReferencia.get_referencia().ano

    @staticmethod
    def get_data_limite():
        return PeriodoReferencia.get_referencia().data_limite

    @staticmethod
    def get_data_base():
        return PeriodoReferencia.get_referencia().data_base

    @staticmethod
    def get_semestre_referencia():
        semestre = 1
        if PeriodoReferencia.get_data_limite().month > 6:
            semestre = 2
        return semestre


class VariavelAcademicoFiltro:
    SOMENTE_ALUNOS_COM_CONVENIO = 0
    SOMENTE_ALUNOS_SEM_CONVENIO = 1


class Variavel(models.ModelPlus):
    __VARIAVEIS_GRUPO = {}

    RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES = Situacao.SITUACOES_EFETIVOS + Situacao.SITUACOES_SUBSTITUTOS_OU_TEMPORARIOS

    sigla = models.CharField(max_length=20, help_text='A sigla é utilizada na fórmula dos indicadores')
    nome = models.CharField(max_length=100)
    descricao = models.TextField('Descrição', max_length=1000)
    fonte = models.CharField(max_length=255, help_text='Origem do dado')
    valor = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Variável'
        verbose_name_plural = 'Variáveis'

        permissions = (
            ('pode_exibir_variaveis', 'Pode exibir variáveis'),
            ('pode_detalhar_variavel', 'Pode detalhar variável'),
            ('pode_comparar_variavel', 'Pode comparar variável'),
        )

    def __init__(self, *args, **kwargs):
        # dicionário útil para identificar o grupo da variável a partir da sigla da variável.
        if not Variavel.__VARIAVEIS_GRUPO:
            for grupo in VARIAVEIS_GRUPOS:
                for variavel_sigla in grupo['variaveis']:
                    if Variavel.__VARIAVEIS_GRUPO.get(variavel_sigla) is None:
                        Variavel.__VARIAVEIS_GRUPO[variavel_sigla] = []
                    Variavel.__VARIAVEIS_GRUPO[variavel_sigla].append(grupo['grupo'])

        super().__init__(*args, **kwargs)

    def __str__(self):
        return f'{self.sigla}: {self.descricao}'

    def get_absolute_url(self):
        return f'/gestao/detalhar_variavel/{self.sigla}/Todas/'

    def has_detalhamento_variavel(self):
        return self.sigla not in ['I', 'VO']

    def is_decimal(self):
        return self.sigla in [
            'DTI',
            'RFP',
            'GOC',
            'GPE',
            'GCA',
            'GPA',
            'GTO',
            'GCO',
            'AEQ',
            'AEQ_PROEJA',
            'AEQ_TECNICO',
            'AEQ_DOCENTE',
            'AEQ_FENC',
            'IAEQ',
        ]

    def get_valor_formatado(self, uo=None):
        if self.is_decimal():
            return mask_money(self.get_valor(uo=uo))
        else:
            return split_thousands(self.get_valor(uo=uo))

    @staticmethod
    def _get_cache_key(variavel_pk, uo_pk, user=None):
        periodo = PeriodoReferencia.get_referencia(user)
        return f'gestao_{periodo.ano}_{periodo.data_base}_{periodo.data_limite}_{variavel_pk}_{uo_pk}'

    @staticmethod
    def recuperar_valor(pk, uo_pk, processar_valor=True):
        cache_key = Variavel._get_cache_key(pk, uo_pk)
        valor = cache.get(cache_key, None)
        if valor is None:
            if processar_valor:
                uo = None
                if uo_pk:
                    uo = UnidadeOrganizacional.objects.suap().get(pk=uo_pk)

                variavel = Variavel.objects.get(pk=pk)
                return variavel.get_valor_formatado(uo)
            else:
                return ''
        else:
            return valor

    def get_valor(self, uo=None, user=None):
        uo_pk = 0 if uo is None else uo.pk
        cache_key = Variavel._get_cache_key(self.pk, uo_pk, user=user)
        valor = cache.get(cache_key, None)
        if valor is None:
            valor = Decimal(0)
            if VARIAVEIS_RH['grupo'] in Variavel.__VARIAVEIS_GRUPO.get(self.sigla, []):
                variaveis_rh = VariavelFactory.get_instance(VARIAVEIS_RH['grupo'])
                if uo is None:
                    valor = variaveis_rh.get_variavel_valor(self.sigla)
                else:
                    valor = variaveis_rh.get_variavel_valor_campus(self.sigla, uo.sigla)

            elif self.sigla == 'RFP':
                valor = self.get_valor_renda_familiar(0, 1000, uo)
            elif self.sigla == 'GOC':
                valor = self.get_valor_GOC(uo=uo)

            elif self.sigla == 'GPE':
                valor = self.get_valor_GPE(uo=uo)

            elif self.sigla == 'GCA':
                valor = self.get_valor_GCA(uo=uo)

            elif self.sigla == 'GPA':
                valor = self.get_valor_GPA(uo=uo)

            elif self.sigla == 'GCO':
                valor = self.get_valor_GCO(uo=uo)

            elif self.sigla == 'GTO':
                valor = self.get_valor_GTO(uo=uo)

            elif self.sigla == 'I':
                valor = self.get_valor_I(uo=uo)

            elif self.sigla == 'VO':
                valor = self.get_valor_VO(uo=uo)

            elif self.sigla == 'AEQ':
                valor = self.get_valor_com_detalhamento_AEQ(uo=uo)[0]

            elif self.sigla == 'AEQ_PROEJA':
                valor = self.get_valor_com_detalhamento_AEQ_PROEJA(uo=uo)[0]

            elif self.sigla == 'AEQ_TECNICO':
                valor = self.get_valor_com_detalhamento_AEQ_TECNICO(uo=uo)[0]

            elif self.sigla == 'AEQ_DOCENTE':
                valor = self.get_valor_com_detalhamento_AEQ_DOCENTE(uo=uo)[0]

            elif self.sigla == 'AEQ_FENC':
                valor = self.get_valor_com_detalhamento_AEQ_FENC(uo=uo)[0]

            elif self.sigla == 'IAEQ':
                valor = self.get_valor_com_detalhamento_IAEQ(uo=uo)[0]

            else:
                querysets = self.get_querysets(uo=uo)
                if querysets:
                    if self.sigla == 'DTI':
                        qs_de_c40h, qs_c20h, qs_fg, qs_cd4, qs_cd123 = querysets
                        valor = (
                            qs_de_c40h.count()
                            + ((qs_c20h.count()) * 0.5)
                            + ((qs_fg.count()) * 0.5)
                            + (qs_cd4.count() * 0.25)
                            + (qs_cd123.count() * 0)
                        )

                    elif self.sigla == 'C':
                        count = 0
                        for qs in querysets:
                            for configuracao_gestao in qs:
                                count += configuracao_gestao.qtd_computadores
                        valor = count
                    else:
                        count = 0
                        for qs in querysets:
                            count += qs.count()
                        valor = count

        cache.set(cache_key, valor, get_cache_expira())
        return valor

    def get_qs_pessoas_envolvidos_extensao(self, uo=None, tipo_pessoa=None):
        PessoaFisica.objects.none()
        if tipo_pessoa == 'docente':
            qs = PessoaFisica.objects.filter(servidor_set__ativo=True, servidor_set__eh_docente=True).distinct()
        elif tipo_pessoa == 'tae':
            qs = PessoaFisica.objects.filter(servidor_set__ativo=True, servidor_set__eh_tecnico_administrativo=True).distinct()
        elif tipo_pessoa == 'discente':
            qs = PessoaFisica.objects.filter(eh_aluno=True).distinct()

        # ----------------------------------------------------------
        from projetos.models import Participacao, Projeto

        projetos = Projeto.objects.filter(aprovado=True)

        projetos = projetos.filter(
            Q(inicio_execucao__gte=PeriodoReferencia.get_data_base()) & Q(inicio_execucao__lte=PeriodoReferencia.get_data_limite())
        )

        participacao = Participacao.objects.filter(projeto_id__in=projetos.values_list('id')).values('vinculo_pessoa__pessoa_id')
        pessoas = participacao.distinct()

        resultado = qs.filter(id__in=pessoas.values_list('vinculo_pessoa__pessoa_id'))

        if uo:
            if tipo_pessoa in ('docente', 'tae'):
                resultado = resultado.filter(servidor_set__setor__uo=uo)
            elif tipo_pessoa == 'discente':
                resultado = resultado.filter(aluno_set__curso_campus__diretoria__setor__uo=uo)

        return [resultado]

    def get_qs_alunos_inscritos(self, uo=None):
        qs = Aluno.objects.filter(ano_letivo__ano=PeriodoReferencia.get_ano_referencia(), curso_campus__modalidade__id__isnull=False)
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    def get_extra_sql(self, com_limite_inferior=True, alias_sql_matricula_periodo=None):
        limite_inferior = " and data >= '{}' ".format(PeriodoReferencia.get_data_base().strftime('%Y-%m-%d'))
        limite_superior = " and data <= '{}' ".format(PeriodoReferencia.get_data_limite().strftime('%Y-%m-%d'))
        if not com_limite_inferior:
            limite_inferior = ''
        extra = '(select t2.codigo_academico from edu_historicosituacaomatriculaperiodo t1 inner join edu_situacaomatriculaperiodo t2 on t1.situacao_id = t2.id where matricula_periodo_id = {}.id {} {} order by data desc limit 1)'.format(
            alias_sql_matricula_periodo or 'edu_matriculaperiodo', limite_inferior, limite_superior
        )
        return extra

    def get_extra_sql2(self, com_limite_inferior=True):
        limite_inferior = ''  # and data >= \'{}\' '%PeriodoReferencia.get_data_base().strftime('%Y-%m-%d')
        limite_superior = " and data <= '{}' ".format(PeriodoReferencia.get_data_limite().strftime('%Y-%m-%d'))
        if not com_limite_inferior:
            limite_inferior = ''
        extra = f'(select t2.codigo_academico from edu_historicosituacaomatricula t1 inner join edu_situacaomatricula t2 on t1.situacao_id = t2.id where aluno_id = edu_aluno.id {limite_inferior} {limite_superior} order by data desc limit 1)'
        return extra

    def get_qs_alunos_matriculados(self, uo=None, alias_sql_matricula_periodo=None):
        """
        Código (não é o id)     Descrição
        - - - - - - - - - -     - - - - - - - - -
                        0       Em Aberto
                        1       Matriculado
                        2       Trancada
                        3       Cancelada (<<< Adicionada atentendo a pedido de Solange e Alessandro (Chamado 41319))
                        4       Afastado
                        9       Dependência
                        10      Aprovado
                        11      Reprovado
                        15      Rep. Falta
                        18      Estágio e/ou Monografia
                        19      Período Fechado
                        23      Matrícula Vínculo Institucional
                        25      Cancelamento Compulsório (<<< Adicionada atentendo a pedido de Solange e Alessandro (Chamado 41319))
        """
        situacao_matricula_periodo_codigo = (0, 1, 2, 3, 4, 9, 10, 11, 15, 18, 19, 23, 25)
        qs1 = MatriculaPeriodo.objects.filter(
            ano_letivo__ano=PeriodoReferencia.get_ano_referencia(), periodo_letivo=1, aluno__curso_campus__modalidade__id__isnull=False
        )
        qs1 = qs1.extra(
            where=[self.get_extra_sql(alias_sql_matricula_periodo=alias_sql_matricula_periodo) + ' IN ' + str(situacao_matricula_periodo_codigo)]
        )
        if uo:
            qs1 = qs1.filter(aluno__curso_campus__diretoria__setor__uo=uo)

        if PeriodoReferencia.get_semestre_referencia() == 2:
            qs2 = MatriculaPeriodo.objects.filter(
                aluno__ano_letivo__ano=PeriodoReferencia.get_ano_referencia(),
                aluno__curso_campus__modalidade__id__isnull=False,
                aluno__situacao__ativo=True,
            ).exclude(aluno__periodo_letivo=1)
            qs2 = qs2.extra(
                where=[self.get_extra_sql(alias_sql_matricula_periodo=alias_sql_matricula_periodo) + ' IN ' + str(situacao_matricula_periodo_codigo)]
            )
            if uo:
                qs2 = qs2.filter(aluno__curso_campus__diretoria__setor__uo=uo)
            qs1 = qs1 | qs2

        qs3 = MatriculaPeriodo.objects.filter(
            ano_letivo__ano=PeriodoReferencia.get_ano_referencia() - 1,
            aluno__curso_campus__modalidade__id__in=[8, 1],
            aluno__situacao__codigo_academico=0,
        )
        qs3 = qs3.extra(
            where=[self.get_extra_sql(alias_sql_matricula_periodo=alias_sql_matricula_periodo) + ' IN ' + str(situacao_matricula_periodo_codigo)]
        )
        if uo:
            qs3 = qs3.filter(aluno__curso_campus__diretoria__setor__uo=uo)
        qs1 = qs1 | qs3

        return [qs1]

    def get_qs_alunos_matriculados_nao_retidos(self, uo=None):
        """
        Este método retorna um queryset de Aluno contendo todos os alunos matriculados na data e período especificados
        no filtro e que o aluno ainda está cursando dentro do período estimado para início e término do curso, ou seja,
        alunos "não retidos".

        A seguir temos um cenário exemplo tendo como ano de referência o ano de 2012 completo:

        Aluno   Ano Ingresso     Ano Previsão Conclusão     Matriculado em 2012     Está presente em AMRN
        -----   ------------     ----------------------     -------------------     ---------------------
        João    2010             2014                       Sim                     Sim
        Maria   2009             2012                       Sim                     Sim
        Carlos  2008             2011                       Sim                     Não
        Pedro   2009             2012                       Não                     Não

        :param uo: a unidade organizacional (campus)
        :return: queryset de Aluno contendo todos os alunos matriculados e não retidos.
        """

        qs_am = self.get_qs_alunos_matriculados(uo=uo, alias_sql_matricula_periodo='V0')[0]
        vlqs_am = qs_am.values_list('aluno__id', flat=True)

        qs = Aluno.objects.filter(id__in=vlqs_am)
        qs = qs.filter(ano_let_prev_conclusao__gte=PeriodoReferencia.get_ano_referencia())

        return [qs]

    def get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(self, uo=None, modalidades=None, tipo_presenca=None):
        qs = self.get_qs_alunos_matriculados(uo=uo)[0]

        if modalidades:
            qs = qs.filter(aluno__curso_campus__modalidade__in=modalidades)

        if tipo_presenca == 'presencial':
            qs = qs.filter(aluno__curso_campus__diretoria__ead=False)
        elif tipo_presenca == 'ead':
            qs = qs.filter(aluno__curso_campus__diretoria__ead=True)

        return [qs]

    def get_qs_alunos_matriculados_nao_fic(self, uo=None):
        qsam = self.get_qs_alunos_matriculados(uo=uo)[0]
        qs = qsam.exclude(aluno__curso_campus__modalidade__in=[Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL])
        return [qs]

    def get_qs_alunos_matriculados_fic(self, uo=None):
        qsam = self.get_qs_alunos_matriculados(uo=uo)[0]
        qs = qsam.filter(aluno__curso_campus__modalidade__in=[Modalidade.FIC, Modalidade.PROEJA_FIC_FUNDAMENTAL])
        return [qs]

    def get_qs_alunos_assitidos_nao_fic(self, uo=None):
        """
        Retorna uma lista de querysets contendo os alunos que não participam de cursos que possuem o termo
        "FIC" na descrição da modalidade do respectivo curso, com matrícula no ano de referência informado
        e que participaram, ou ainda participam, de pelo menos um programa de permanência durante o período
        de referência informado.

        Obs: Cada aluno será exibido apenas uma vez, mesmo que ele tenha mais de uma participação em programas
        de permanência no período informado.
        """
        qs = Aluno.nao_fic.filter(matriculaperiodo__ano_letivo__ano=PeriodoReferencia.get_ano_referencia())

        qs = qs.filter(
            Q(participacao__data_inicio__range=[PeriodoReferencia.get_data_base(), PeriodoReferencia.get_data_limite()])
            | Q(participacao__data_termino__range=[PeriodoReferencia.get_data_base(), PeriodoReferencia.get_data_limite()])
            | Q(participacao__data_termino__gte=datetime.date.today(), participacao__data_inicio__lt=PeriodoReferencia.get_data_limite())
            | Q(participacao__data_termino__isnull=True, participacao__data_inicio__lt=PeriodoReferencia.get_data_base())
        )

        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)

        # Como um aluno pode ter "n" participações, se faz necessário aplicar o DISTINCT
        # para evitar duplicidade.
        qs = qs.distinct()
        return [qs]

    def get_qs_alunos_jubiliados(self, uo=None):
        qs = Aluno.objects.filter(
            matriculaperiodo__ano_letivo__ano=PeriodoReferencia.get_ano_referencia(), curso_campus__modalidade__id__isnull=False
        ).extra(where=[self.get_extra_sql2() + ' = ' + str(3)])
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    def get_qs_alunos_evadidos(self, uo=None):
        qs = (
            Aluno.objects.filter(matriculaperiodo__ano_letivo__ano=PeriodoReferencia.get_ano_referencia(), curso_campus__modalidade__id__isnull=False)
            .extra(where=[self.get_extra_sql2() + ' = ' + str(9)])
            .distinct()
        )
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    def get_qs_alunos_retidos(self, uo=None):
        qs = (
            Aluno.objects.filter(matriculaperiodo__ano_letivo__ano=PeriodoReferencia.get_ano_referencia(), curso_campus__modalidade__id__isnull=False)
            .extra(where=[self.get_extra_sql() + ' IN ' + str((11, 15, 2, 23, 4))])
            .distinct()
        )
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    # Rotina nova que passa a se basear no atributo "situação" presente no Aluno, e não mais no último registro de
    # HistoricoSituacaoMatricula dele. Esse ajuste foi feito para atender ao chamado 40358.
    def get_qs_alunos_concluintes(self, uo=None):
        situacoes_matricula_aluno_concluinte = (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.EGRESSO, SituacaoMatricula.FORMADO)
        qs = Aluno.objects.filter(
            dt_conclusao_curso__gte=PeriodoReferencia.get_data_base(),
            dt_conclusao_curso__lte=PeriodoReferencia.get_data_limite(),
            curso_campus__modalidade__id__isnull=False,
            situacao__in=situacoes_matricula_aluno_concluinte,
        )

        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    def get_qs_alunos_ingressantes_turmas_concluintes(self, uo=None):
        from comum.models import Ano

        qs = Aluno.objects.filter(
            ano_let_prev_conclusao=PeriodoReferencia.get_ano_referencia(), curso_campus__modalidade__id__isnull=False
        ) | Aluno.objects.filter(
            curso_campus__descricao__unaccent__icontains='PROITEC', ano_letivo=Ano.objects.get(ano=PeriodoReferencia.get_ano_referencia())
        )
        qs = qs.distinct()
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo)
        return [qs]

    def get_qs_alunos_ingressos_correspondentes_mec(self, uo=None):
        """
        Retorna uma lista de querysets contendo as matrículas período correspondentes para cada objeto que estiver
        presente na variável 'AM - Alunos Matriculados'. Essa variável AIMEC, juntamente com a AM, irão compor o
        indicador IEnI do MEC.

        Cenário Exemplo:
        Na variável AM, para o ano de 2015, estão presentes os alunos Alessandro, Misael e Breno. No caso o valor da vari-
        ável AM = 3.

        Alessandro e Misael tem o mesmo curso, ano e período de ingresso, e no caso foi verificado que existiam 40 alunos
        para esses parâmetros(Alessandro e Misael estão inclusos nesses 40). Então computa-se esses 40 alunos.

        Breno estuda no mesmo curso, ano, mas em período de ingresso diferente. No caso para esses parâmetros foram achados
        20 alunos (Breno está incluso nesses 20). Então computa-se mais 20 alunos.

        Ao final, o valor da variável AIMEC = 60.
        Ao final, o indicador IEI (MEC) será AM/AIMEC = 3/60.
        """
        qs_am = self.get_qs_alunos_matriculados(uo=uo)[0]

        # Trazendo todos os cursos, anos e períodos distintos de todos as matrículas período em questão.
        ai_mec_params_dict = qs_am.values('aluno__curso_campus', 'ano_letivo', 'periodo_letivo').distinct()

        # Para cada item de ai_mec_params_dict, será adicionada uma condicional para trazer somente as matrículas período
        # daquele curso, ano e período de ingresso.
        qs = MatriculaPeriodo.objects.none()
        for cont, aip in enumerate(ai_mec_params_dict):
            if cont == 0:
                qs = MatriculaPeriodo.objects.filter(
                    aluno__curso_campus=aip['aluno__curso_campus'], ano_letivo=aip['ano_letivo'], periodo_letivo=aip['periodo_letivo']
                )
            else:
                qs = qs | MatriculaPeriodo.objects.filter(
                    aluno__curso_campus=aip['aluno__curso_campus'], ano_letivo=aip['ano_letivo'], periodo_letivo=aip['periodo_letivo']
                )

        # Acredito que nao precisa disso visto que qs só nao vai existir caso nao tenha nada em ai_mec_params_dict e o qs ja vai estar zerado
        # if not qs:
        #     qs = MatriculaPeriodo.objects.none()
        # Ao final, será retornado uma lista contendo um queryset com várias matrículas período de forma que não há
        # objetos repetidos, ou seja, com mesmo cursos, anos e período de ingresso.
        return [qs]

    def get_qs_alunos_ingressos_correspondentes_nao_retidos_mec(self, uo):
        qs_aicor = self.get_qs_alunos_ingressos_correspondentes_mec(uo=uo)[0]
        vlqs_aicor = qs_aicor.values_list('aluno__id', flat=True)

        qs = Aluno.objects.filter(id__in=vlqs_aicor)
        qs = qs.filter(ano_let_prev_conclusao__gte=PeriodoReferencia.get_ano_referencia())

        return [qs]

    def get_qs_cursos(self, uo=None, tipo_presenca=None, cursos_que_tem_alunos_com_convenio=None):
        qs = CursoCampus.objects.filter(turma__ano_letivo__ano=PeriodoReferencia.get_ano_referencia())

        if tipo_presenca == 'presencial':
            qs = qs.filter(diretoria__ead=False)
        elif tipo_presenca == 'ead':
            qs = qs.filter(diretoria__ead=True)

        if cursos_que_tem_alunos_com_convenio is not None:
            qs = qs.filter(aluno__convenio__isnull=not cursos_que_tem_alunos_com_convenio)

        if uo:
            qs = qs.filter(diretoria__setor__uo=uo)

        qs = qs.distinct()
        return [qs]

    def get_valor_VO(self, uo=None):
        qs_edital = Edital.objects.filter(ano__ano=PeriodoReferencia.get_ano_referencia(), remanescentes=False)

        result = 0
        if uo:
            for edital in qs_edital:
                detalhamento_por_campus = edital.get_detalhamento_por_campus_sgc_agrupado_por_suap_unidade_organizacional_id(uo.id)
                if detalhamento_por_campus:
                    result += detalhamento_por_campus['qtd_vagas'] or 0
        else:
            result = qs_edital.aggregate(Sum('qtd_vagas'))['qtd_vagas__sum'] or 0

        return result

    def _get_valor_com_detalhamento_alunos_segundo_portaria_n25_2015_setec(self, qs_aluno, modalidades=None):
        qs = qs_aluno.select_related('matriz')
        qs = qs.select_related('curso_campus')
        qs = qs.select_related('curso_campus__modalidade')
        qs = qs.select_related('pessoa_fisica')
        qs = qs.order_by('pessoa_fisica__nome')

        if modalidades:
            qs = qs.filter(curso_campus__modalidade__in=modalidades)

        result_valor_AEQ = 0
        result_valor_AEQ_FENC = 0
        result_detalhamento = []

        for aluno in qs:
            curso_campus = aluno.curso_campus
            matriz = aluno.matriz or (aluno.curso_campus.matrizes.all()[0] if aluno.curso_campus.matrizes.all().exists() else None)
            ch_total = 0
            duracao_curso_anos = 0
            fator_equiparacao_carga_horaria = 0
            fator_esforco_curso = round((curso_campus.fator_esforco_curso or 0), 2)

            fenc = 0
            if curso_campus.modalidade.id in (
                Modalidade.FIC,
                Modalidade.PROEJA_FIC_FUNDAMENTAL,
                Modalidade.INTEGRADO,
                Modalidade.INTEGRADO_EJA,
                Modalidade.FIC_INTEGRADO_EJA,
                Modalidade.SUBSEQUENTE,
                Modalidade.CONCOMITANTE,
            ):
                fenc = 1.0
            elif curso_campus.modalidade.id in [
                Modalidade.LICENCIATURA,
                Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
                Modalidade.ENGENHARIA,
                Modalidade.BACHARELADO,
                Modalidade.TECNOLOGIA,
            ]:
                fenc = 1.1
            elif curso_campus.modalidade.id in [Modalidade.ESPECIALIZACAO, Modalidade.APERFEICOAMENTO]:
                fenc = 1.6
            elif curso_campus.modalidade.id in [Modalidade.MESTRADO, Modalidade.DOUTORADO]:
                fenc = 2.5

            if matriz:
                ch_total = matriz.get_carga_horaria_total_prevista()
                if curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                    duracao_curso_anos = Decimal(matriz.qtd_periodos_letivos)
                elif curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
                    duracao_curso_anos = Decimal(matriz.qtd_periodos_letivos) / 2
                # Em conversa com Breno, ele me disse que os cursos de PERIODICIDADE_LIVRE são cursos como FIC.
                elif curso_campus.periodicidade == CursoCampus.PERIODICIDADE_LIVRE:
                    duracao_curso_anos = Decimal(1)
                fator_equiparacao_carga_horaria = ch_total / (duracao_curso_anos * 800)

            duracao_curso_anos = round(duracao_curso_anos, 2)
            fator_equiparacao_carga_horaria = round(fator_equiparacao_carga_horaria, 2)

            valor_aluno_equivalente = fator_equiparacao_carga_horaria * fator_esforco_curso
            valor_aluno_equivalente_com_fenc = float(valor_aluno_equivalente) * fenc
            result_detalhamento.append(
                {
                    'matricula': aluno.matricula,
                    'nome': aluno.pessoa_fisica.nome,
                    'aluno': aluno,
                    'curso': str(curso_campus),
                    'matriz': (str(matriz) if matriz else '(Matriz Não Definida)'),
                    'ch_total': ch_total,
                    'duracao_curso_anos': mask_money(duracao_curso_anos),
                    'fator_equiparacao_carga_horaria': mask_money(fator_equiparacao_carga_horaria),
                    'fator_esforco_curso': mask_money(fator_esforco_curso),
                    'valor_aluno_equivalente': mask_money(valor_aluno_equivalente),
                    'fenc': mask_money(fenc),
                    'valor_aluno_equivalente_com_fenc': mask_money(valor_aluno_equivalente_com_fenc),
                }
            )
            result_valor_AEQ += valor_aluno_equivalente
            result_valor_AEQ_FENC += valor_aluno_equivalente_com_fenc

        return result_valor_AEQ, result_valor_AEQ_FENC, result_detalhamento

    def get_valor_com_detalhamento_AEQ(self, uo=None, modalidades=None, formacao_de_professores=False):
        qs_aluno = self.get_qs_alunos_matriculados_nao_retidos(uo=uo)[0]
        if formacao_de_professores:
            qs_aluno = qs_aluno.filter(curso_campus__formacao_de_professores=True)
        result_valor_AEQ, _result_valor_AEQ_FENC, result_detalhamento = self._get_valor_com_detalhamento_alunos_segundo_portaria_n25_2015_setec(
            qs_aluno=qs_aluno, modalidades=modalidades
        )
        return result_valor_AEQ, result_detalhamento

    def get_valor_com_detalhamento_AEQ_FENC(self, uo=None):
        qs_aluno = self.get_qs_alunos_matriculados_nao_retidos(uo=uo)[0]
        _result_valor_AEQ, result_valor_AEQ_FENC, result_detalhamento = self._get_valor_com_detalhamento_alunos_segundo_portaria_n25_2015_setec(
            qs_aluno=qs_aluno
        )
        return result_valor_AEQ_FENC, result_detalhamento

    def get_valor_com_detalhamento_AEQ_PROEJA(self, uo=None):
        return self.get_valor_com_detalhamento_AEQ(
            uo=uo, modalidades=[Modalidade.PROEJA_FIC_FUNDAMENTAL, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]
        )

    def get_valor_com_detalhamento_AEQ_TECNICO(self, uo=None):
        return self.get_valor_com_detalhamento_AEQ(uo=uo, modalidades=[Modalidade.INTEGRADO, Modalidade.SUBSEQUENTE, Modalidade.CONCOMITANTE])

    def get_valor_com_detalhamento_AEQ_DOCENTE(self, uo=None):
        return self.get_valor_com_detalhamento_AEQ(uo=uo, formacao_de_professores=True)

    def get_valor_com_detalhamento_IAEQ(self, uo=None):
        qs_aluno = self.get_qs_alunos_ingressos_correspondentes_nao_retidos_mec(uo=uo)[0]
        return self._get_valor_com_detalhamento_alunos_segundo_portaria_n25_2015_setec(qs_aluno=qs_aluno)

    def get_valor_I(self, uo=None):
        qs = OfertaVagaCurso.objects.filter(edital__ano__ano=PeriodoReferencia.get_ano_referencia())
        if uo:
            qs = qs.filter(curso_campus__diretoria__setor__uo=uo).filter(edital__remanescentes=False)
        return qs.aggregate(Sum('qtd_inscritos'))['qtd_inscritos__sum']

    # Variáveis de Gestão de Pessoas

    def get_qs_docentes(self, uo=None):
        # REMOVER APÓS HOMOLOGAÇÃO
        # O trecho de código abaixo estava calculando o número de professores com base no grau de instrução e baseado
        # no contra-chueque, o que não estava refletindo a realidade. No caso passamos a usar o manager que traz os
        # todos os docentes ativos.
        # qs = self.get_qs_graduados(uo=uo)[0] | \
        #      self.get_qs_aperfeicoados(uo=uo)[0] | \
        #      self.get_qs_especizalidados(uo=uo)[0] | \
        #      self.get_qs_mestres(uo=uo)[0] | \
        #      self.get_qs_doutores(uo=uo)[0]

        qs = Servidor.objects.docentes()
        if uo:
            qs = qs.filter(setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_docentes_ativos_permanentes(self, uo=None, jornada_trabalho=None):
        qs = Servidor.objects.docentes_permanentes()

        if jornada_trabalho:
            qs = qs.filter(jornada_trabalho__nome=jornada_trabalho)

        if uo:
            qs = qs.filter(setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_docentes_substitutos_ou_temporarios(self, uo=None):
        qs = Servidor.objects.substitutos_ou_temporarios()
        if uo:
            qs = qs.filter(setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_docentes_cedidos(self, uo=None):
        qs = Servidor.objects.docentes_cedidos()
        if uo:
            qs = qs.filter(setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_docentes_por_titulacao(self, titulacoes_ids, uo=None):
        qs = Servidor.objects.docentes()
        qs = qs.filter(situacao__codigo__in=Situacao.SITUACOES_EFETIVOS_E_TEMPORARIOS)

        qs = qs.filter(titulacao_id__in=titulacoes_ids)
        if uo:
            qs = qs.filter(setor_lotacao__uo__equivalente=uo)

        return [qs]

    # REMOVER APÓS HOMOLOGAÇÃO
    def get_qs_graduados(self, uo=None):
        qs = Servidor.objects.filter(
            contracheque__mes=PeriodoReferencia.get_data_limite().month,
            contracheque__ano__ano=PeriodoReferencia.get_data_limite().year,
            contracheque__servidor_eh_docente=True,
            contracheque__servidor_titulacao__isnull=True,
            ativo=True,
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    # REMOVER APÓS HOMOLOGAÇÃO
    def get_qs_aperfeicoados(self, uo=None):
        qs = Servidor.objects.filter(
            contracheque__mes=PeriodoReferencia.get_data_limite().month,
            contracheque__ano__ano=PeriodoReferencia.get_data_limite().year,
            contracheque__servidor_eh_docente=True,
            contracheque__servidor_titulacao__nome__startswith='APERFEICOAMENTO',
            ativo=True,
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    # REMOVER APÓS HOMOLOGAÇÃO
    def get_qs_especizalidados(self, uo=None):
        qs = Servidor.objects.filter(
            contracheque__mes=PeriodoReferencia.get_data_limite().month,
            contracheque__ano__ano=PeriodoReferencia.get_data_limite().year,
            contracheque__servidor_eh_docente=True,
            contracheque__servidor_titulacao__nome__startswith='ESPECIALIZACAO',
            ativo=True,
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    # REMOVER APÓS HOMOLOGAÇÃO
    def get_qs_mestres(self, uo=None):
        qs = Servidor.objects.filter(
            contracheque__mes=PeriodoReferencia.get_data_limite().month,
            contracheque__ano__ano=PeriodoReferencia.get_data_limite().year,
            contracheque__servidor_eh_docente=True,
            contracheque__servidor_titulacao__nome__startswith='MESTRADO',
            ativo=True,
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    # REMOVER APÓS HOMOLOGAÇÃO
    def get_qs_doutores(self, uo=None):
        qs = Servidor.objects.filter(
            contracheque__mes=PeriodoReferencia.get_data_limite().month,
            contracheque__ano__ano=PeriodoReferencia.get_data_limite().year,
            contracheque__servidor_eh_docente=True,
            contracheque__servidor_titulacao__nome__startswith='DOUTORADO',
            ativo=True,
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    def get_qs_docontes_tempo_integral(self, uo=None):
        # DE ou 40h sem função
        qs_de_c40h = Servidor.objects.filter(
            ativo=True, eh_docente=True, funcao__isnull=True, jornada_trabalho__nome__in=['DEDICACAO EXCLUSIVA', '40 HORAS SEMANAIS']
        ).exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        if uo:
            qs_de_c40h = qs_de_c40h.filter(setor__uo=uo)

        # 20h sem função
        qs_c20h = Servidor.objects.filter(ativo=True, eh_docente=True, funcao__isnull=True, jornada_trabalho__nome='20 HORAS SEMANAIS').exclude(
            contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO']
        )
        if uo:
            qs_c20h = qs_c20h.filter(setor__uo=uo)

        # Com função FG
        qs_fg = Servidor.objects.filter(ativo=True, eh_docente=True, funcao__codigo=Funcao.CODIGO_FG).exclude(
            contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO']
        )
        if uo:
            qs_fg = qs_fg.filter(setor__uo=uo)

        # Com função CD4
        qs_cd4 = Servidor.objects.filter(ativo=True, eh_docente=True, funcao__codigo=Funcao.CODIGO_CD, funcao_codigo__in=['4', '0004']).exclude(
            contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO']
        )
        if uo:
            qs_cd4 = qs_cd4.filter(setor__uo=uo)

        # Com função CD1 ou CD2 ou CD3
        qs_cd123 = (
            Servidor.objects.filter(ativo=True, eh_docente=True, funcao__codigo=Funcao.CODIGO_CD)
            .exclude(funcao_codigo__in=['4', '0004'])
            .exclude(contracheque__servidor_situacao__nome_siape__in=['APOSENTADO', 'EXERCICIO PROVISORIO'])
        )
        if uo:
            qs_cd123 = qs_cd123.filter(setor__uo=uo)

        return [qs_de_c40h, qs_c20h, qs_fg, qs_cd4, qs_cd123]

    def __get_qs_docentes_sem_funcao_por_jornada_trabalho(self, jornada_trabalho__nome, uo=None, tem_funcao=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO", que não têm função
        e com a jornada de trabalho de nome "[jornada_trabalho__nome] e com ou sem função".
        """
        qs = Servidor.objects.docentes().filter(
            situacao__codigo__in=self.RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES, jornada_trabalho__nome__in=[jornada_trabalho__nome]
        )
        if uo:
            qs = qs.filter(setor__uo=uo)

        if tem_funcao is not None:
            qs = qs.filter(funcao__isnull=not tem_funcao)

        return [qs]

    def get_qs_docentes_dedicacao_exclusiva(self, uo=None, tem_funcao=None):
        return self.__get_qs_docentes_sem_funcao_por_jornada_trabalho(jornada_trabalho__nome='DEDICACAO EXCLUSIVA', uo=uo, tem_funcao=tem_funcao)

    def get_qs_docentes_40h(self, uo=None, tem_funcao=None):
        return self.__get_qs_docentes_sem_funcao_por_jornada_trabalho(jornada_trabalho__nome='40 HORAS SEMANAIS', uo=uo, tem_funcao=tem_funcao)

    def get_qs_docentes_20h(self, uo=None, tem_funcao=None):
        return self.__get_qs_docentes_sem_funcao_por_jornada_trabalho(jornada_trabalho__nome='20 HORAS SEMANAIS', uo=uo, tem_funcao=tem_funcao)

    def get_qs_docentes_funcao_fg(self, uo=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO" e que têm a função
        de código "FG".
        """
        qs = Servidor.objects.docentes().filter(situacao__codigo__in=self.RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES, funcao__codigo=Funcao.CODIGO_FG)
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    def __get_qs_docentes_funcao_cd(self, funcao_codigo, uo=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO" que têm a função "CD",
        de código [funcao_codigo].
        """
        qs = Servidor.objects.docentes().filter(
            situacao__codigo__in=self.RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES, funcao__codigo=Funcao.CODIGO_CD, funcao_codigo__icontains=funcao_codigo
        )
        if uo:
            qs = qs.filter(setor__uo=uo)
        return [qs]

    def get_qs_docentes_funcao_cd1(self, uo=None):
        return self.__get_qs_docentes_funcao_cd(funcao_codigo__in=['1', '0001'], uo=uo)

    def get_qs_docentes_funcao_cd2(self, uo=None):
        return self.__get_qs_docentes_funcao_cd(funcao_codigo__in=['2', '0002'], uo=uo)

    def get_qs_docentes_funcao_cd3(self, uo=None):
        return self.__get_qs_docentes_funcao_cd(funcao_codigo__in=['3', '0003'], uo=uo)

    def get_qs_docentes_funcao_cd4(self, uo=None):
        return self.__get_qs_docentes_funcao_cd(funcao_codigo__in=['4', '0004'], uo=uo)

    # Fim das Variáveis de Gestão de Pessoas

    # Fim das Variáveis de Gestão de Pessoas

    def get_qs_artigos_publicados(self, uo=None, somente_no_ano_referencia=False):
        qs = Artigo.objects.filter(curriculo__vinculo__user__eh_docente=True, curriculo__vinculo__ativo=True)

        if somente_no_ano_referencia:
            qs = qs.filter(ano=PeriodoReferencia.get_ano_referencia())
        else:
            qs = qs.filter(ano__range=(PeriodoReferencia.get_ano_referencia() - 2, PeriodoReferencia.get_ano_referencia()))

        if uo:
            qs = qs.filter(curriculo__vinculo__pessoa__pessoafisica__servidor_set__setor_lotacao__uo__equivalente=uo)

        # Um artigo pode ter "n" estratos, daí o menor estrato é o de maior qualidade,
        # segundo informações repassadas pelo professor Jerônimo.
        qs = qs.annotate(estrato=Min('periodico__estratos_qualis__estrato'))
        return [qs]

    def get_qs_capitulos_publicados(self, uo=None, somente_no_ano_referencia=False):
        qs = Capitulo.objects.filter(curriculo__vinculo__user__eh_docente=True, curriculo__vinculo__ativo=True)

        if somente_no_ano_referencia:
            qs = qs.filter(ano=PeriodoReferencia.get_ano_referencia())
        else:
            qs = qs.filter(ano__range=(PeriodoReferencia.get_ano_referencia() - 2, PeriodoReferencia.get_ano_referencia()))

        if uo:
            qs = qs.filter(curriculo__vinculo__pessoa__pessoafisica__servidor_set__setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_livros_publicados(self, uo=None, somente_no_ano_referencia=False):
        qs = Livro.objects.filter(curriculo__vinculo__user__eh_docente=True, curriculo__vinculo__ativo=True)

        if somente_no_ano_referencia:
            qs = qs.filter(ano=PeriodoReferencia.get_ano_referencia())
        else:
            qs = qs.filter(ano__range=(PeriodoReferencia.get_ano_referencia() - 2, PeriodoReferencia.get_ano_referencia()))

        if uo:
            qs = qs.filter(curriculo__vinculo__pessoa__pessoafisica__servidor_set__setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_trabalhos_completos_publicados(self, uo=None, somente_no_ano_referencia=False):
        qs = TrabalhoEvento.objects.filter(natureza='COMPLETO').filter(curriculo__vinculo__user__eh_docente=True, curriculo__vinculo__ativo=True)

        if somente_no_ano_referencia:
            qs = qs.filter(ano=PeriodoReferencia.get_ano_referencia())
        else:
            qs = qs.filter(ano__range=(PeriodoReferencia.get_ano_referencia() - 2, PeriodoReferencia.get_ano_referencia()))

        if uo:
            qs = qs.filter(curriculo__vinculo__pessoa__pessoafisica__servidor_set__setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_resumos_publicados(self, uo=None, somente_no_ano_referencia=False):
        qs = TrabalhoEvento.objects.filter(natureza='RESUMO').filter(curriculo__vinculo__user__eh_docente=True, curriculo__vinculo__ativo=True)

        if somente_no_ano_referencia:
            qs = qs.filter(ano=PeriodoReferencia.get_ano_referencia())
        else:
            qs = qs.filter(ano__range=(PeriodoReferencia.get_ano_referencia() - 2, PeriodoReferencia.get_ano_referencia()))

        if uo:
            qs = qs.filter(curriculo__vinculo__pessoa__pessoafisica__servidor_set__setor_lotacao__uo__equivalente=uo)
        return [qs]

    def get_qs_computadores(self, uo=None):
        qs = ConfiguracaoGestao.objects.all()
        if uo:
            qs = qs.filter(uo=uo)
        return [qs]

    def get_querysets(self, uo=None):
        if VARIAVEIS_RH['grupo'] in Variavel.__VARIAVEIS_GRUPO.get(self.sigla, []):
            variaveis_rh = VariavelFactory.get_instance(VARIAVEIS_RH['grupo'])
            uo_sigla = None
            if uo is not None:
                uo_sigla = uo.sigla
            return [variaveis_rh._get_query_uo(self.sigla, uo_sigla)]
        elif self.sigla == 'DEE':
            return self.get_qs_pessoas_envolvidos_extensao(uo=uo, tipo_pessoa='docente')
        elif self.sigla == 'TAEE':
            return self.get_qs_pessoas_envolvidos_extensao(uo=uo, tipo_pessoa='tae')
        elif self.sigla == 'DISCEE':
            return self.get_qs_pessoas_envolvidos_extensao(uo=uo, tipo_pessoa='discente')
        elif self.sigla == 'AI':
            return self.get_qs_alunos_inscritos(uo=uo)
        elif self.sigla == 'AI_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_inscritos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AI_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_inscritos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )
        elif self.sigla == 'AM':
            return self.get_qs_alunos_matriculados(uo=uo)
        elif self.sigla == 'AM_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AM_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )

        elif self.sigla == 'AM_NR':
            return self.get_qs_alunos_matriculados_nao_retidos(uo=uo)

        elif self.sigla == 'AMPRES':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='presencial')

        elif self.sigla == 'AMPRES_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='presencial'),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMPRES_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='presencial'),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla == 'AMPRESF':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, modalidades=[Modalidade.FIC], tipo_presenca='presencial')

        elif self.sigla == 'AMPRESF_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.FIC], tipo_presenca='presencial'
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMPRESF_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.FIC], tipo_presenca='presencial'
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla == 'AMEAD':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='ead')

        elif self.sigla == 'AMEAD_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='ead'),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMEAD_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, tipo_presenca='ead'),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla in [
            'AMGRAD',
            'AMGRAD_EX',
            'AMGRAD_OR',
            'AMGRAD_EAD',
            'AMGRAD_EAD_EX',
            'AMGRAD_EAD_OR',
            'AMGRAD_PRES',
            'AMGRAD_PRES_EX',
            'AMGRAD_PRES_OR',
        ]:
            tipo_presenca = None
            if '_EAD' in self.sigla:
                tipo_presenca = 'ead'
            elif '_PRES' in self.sigla:
                tipo_presenca = 'presencial'

            queryset_list = self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                uo=uo,
                modalidades=[
                    Modalidade.LICENCIATURA,
                    Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
                    Modalidade.ENGENHARIA,
                    Modalidade.BACHARELADO,
                    Modalidade.TECNOLOGIA,
                ],
                tipo_presenca=tipo_presenca,
            )

            variavel_academico_filtro = None
            if self.sigla.endswith('_EX'):
                variavel_academico_filtro = VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            elif self.sigla.endswith('_OR'):
                variavel_academico_filtro = VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO

            if variavel_academico_filtro is not None:
                return self.get_qs_com_filtro_aluno_convenio(queryset_list=queryset_list, variavel_academico_filtro=variavel_academico_filtro)
            else:
                return queryset_list

        elif self.sigla in [
            'AMTEC',
            'AMTEC_EX',
            'AMTEC_OR',
            'AMTEC_EAD',
            'AMTEC_EAD_EX',
            'AMTEC_EAD_OR',
            'AMTEC_PRES',
            'AMTEC_PRES_EX',
            'AMTEC_PRES_OR',
        ]:
            tipo_presenca = None
            if '_EAD' in self.sigla:
                tipo_presenca = 'ead'
            elif '_PRES' in self.sigla:
                tipo_presenca = 'presencial'

            queryset_list = self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                uo=uo,
                modalidades=[
                    Modalidade.INTEGRADO,
                    Modalidade.INTEGRADO_EJA,
                    Modalidade.FIC_INTEGRADO_EJA,
                    Modalidade.SUBSEQUENTE,
                    Modalidade.CONCOMITANTE,
                ],
                tipo_presenca=tipo_presenca,
            )

            variavel_academico_filtro = None
            if self.sigla.endswith('_EX'):
                variavel_academico_filtro = VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            elif self.sigla.endswith('_OR'):
                variavel_academico_filtro = VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO

            if variavel_academico_filtro is not None:
                return self.get_qs_com_filtro_aluno_convenio(queryset_list=queryset_list, variavel_academico_filtro=variavel_academico_filtro)
            else:
                return queryset_list

        elif self.sigla == 'AMLIC':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                uo=uo, modalidades=[Modalidade.LICENCIATURA, Modalidade.LICENCIATURA_DUPLA_HABILITACAO]
            )

        elif self.sigla == 'AMLIC_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.LICENCIATURA, Modalidade.LICENCIATURA_DUPLA_HABILITACAO]
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMLIC_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.LICENCIATURA, Modalidade.LICENCIATURA_DUPLA_HABILITACAO]
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla == 'AMMEST':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, modalidades=[Modalidade.MESTRADO])

        elif self.sigla == 'AMMEST_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, modalidades=[Modalidade.MESTRADO]),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMMEST_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(uo=uo, modalidades=[Modalidade.MESTRADO]),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )
        elif self.sigla == 'AMEJA':
            return self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                uo=uo, modalidades=[Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]
            )

        elif self.sigla == 'AMEJA_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AMEJA_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_matriculados_por_modalidade_eou_tipo_presenca(
                    uo=uo, modalidades=[Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]
                ),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )
        elif self.sigla == 'AMNF':
            return self.get_qs_alunos_matriculados_nao_fic(uo=uo)
        elif self.sigla == 'AMF':
            return self.get_qs_alunos_matriculados_fic(uo=uo)
        elif self.sigla == 'AANF':
            return self.get_qs_alunos_assitidos_nao_fic(uo=uo)
        elif self.sigla == 'AR':
            return self.get_qs_alunos_retidos(uo=uo)
        elif self.sigla == 'AR_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_retidos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AR_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_retidos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )
        elif self.sigla == 'AJ':
            return self.get_qs_alunos_jubiliados(uo=uo)
        elif self.sigla == 'AJ_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_jubiliados(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AJ_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_jubiliados(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )
        elif self.sigla == 'AE':
            return self.get_qs_alunos_evadidos(uo=uo)
        elif self.sigla == 'AE_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_evadidos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AE_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_evadidos(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )
        elif self.sigla == 'AC':
            return self.get_qs_alunos_concluintes(uo=uo)
        elif self.sigla == 'AC_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_concluintes(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO
            )
        elif self.sigla == 'AC_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_concluintes(uo=uo), variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO
            )
        elif self.sigla == 'AIC':
            return self.get_qs_alunos_ingressantes_turmas_concluintes(uo=uo)
        elif self.sigla == 'AIC_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_ingressantes_turmas_concluintes(uo=uo),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AIC_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_ingressantes_turmas_concluintes(uo=uo),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla == 'AICOR':
            return self.get_qs_alunos_ingressos_correspondentes_mec(uo=uo)
        elif self.sigla == 'AICOR_EX':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_ingressos_correspondentes_mec(uo=uo),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO,
            )
        elif self.sigla == 'AICOR_OR':
            return self.get_qs_com_filtro_aluno_convenio(
                queryset_list=self.get_qs_alunos_ingressos_correspondentes_mec(uo=uo),
                variavel_academico_filtro=VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO,
            )

        elif self.sigla == 'AICOR_NR':
            return self.get_qs_alunos_ingressos_correspondentes_nao_retidos_mec(uo=uo)

        elif self.sigla == 'CO':
            return self.get_qs_cursos(uo=uo)
        elif self.sigla == 'COPRES':
            return self.get_qs_cursos(uo=uo, tipo_presenca='presencial')
        elif self.sigla == 'COEAD':
            return self.get_qs_cursos(uo=uo, tipo_presenca='ead')

        elif self.sigla == 'COEAD_EX':
            return self.get_qs_cursos(uo=uo, tipo_presenca='ead', cursos_que_tem_alunos_com_convenio=True)
        elif self.sigla == 'COEAD_OR':
            return self.get_qs_cursos(uo=uo, tipo_presenca='ead', cursos_que_tem_alunos_com_convenio=False)

        # REMOVER a variável DTI após homologação, já que o indicador foi criado.
        elif self.sigla == 'DTI':
            return self.get_qs_docontes_tempo_integral(uo=uo)

        # elif self.sigla == 'VO':
        #     return self.get_qs_vagas_ofertadas(uo=uo)
        # elif self.sigla == 'I':
        #     return self.get_qs_inscricoes(uo=uo)
        elif self.sigla == 'NA':
            return self.get_qs_artigos_publicados(uo)
        elif self.sigla == 'NL':
            return self.get_qs_livros_publicados(uo) + self.get_qs_capitulos_publicados(uo)
        elif self.sigla == 'NT':
            return self.get_qs_trabalhos_completos_publicados(uo)
        elif self.sigla == 'NR':
            return self.get_qs_resumos_publicados(uo)
        elif self.sigla == 'NAA':
            return self.get_qs_artigos_publicados(uo, True)
        elif self.sigla == 'NLA':
            return self.get_qs_livros_publicados(uo, True) + self.get_qs_capitulos_publicados(uo, True)
        elif self.sigla == 'NTA':
            return self.get_qs_trabalhos_completos_publicados(uo, True)
        elif self.sigla == 'NRA':
            return self.get_qs_resumos_publicados(uo, True)
        elif self.sigla == 'C':
            return self.get_qs_computadores(uo)
        else:
            return []

    def __get_querysets_rh(self, uo=None):
        # As variáveis G, A, E, M e D passam a ser calculadas desta forma temporariamente, pois não se tem
        # uma definição mais clara, por parte do demandante.
        if self.sigla == 'A':
            # return self.get_qs_aperfeicoados(uo=uo)
            # 5 - APERFEICOAMENTO NIVEL SUPERIOR
            return self.get_qs_docentes_por_titulacao(titulacoes_ids=[5], uo=uo)
        elif self.sigla == 'E':
            # return self.get_qs_especizalidados(uo=uo)
            # 6 - ESPECIALIZACAO NIVEL SUPERIOR
            # 30 - POS-GRADUAÇÃO+RSC-II LEI 12772/12 ART 18
            return self.get_qs_docentes_por_titulacao(titulacoes_ids=[6, 30], uo=uo)
        elif self.sigla == 'G':
            # return self.get_qs_graduados(uo=uo)
            # 4 - GRADUACAO (NIVEL SUPERIOR COMPLETO)
            # 29 - GRADUAÇÃO+RSC-I (LEI 12772/12 ART. 18)
            # 16 - LICENCIATURA
            return self.get_qs_docentes_por_titulacao(titulacoes_ids=[4, 29, 16], uo=uo)
        elif self.sigla == 'M':
            # return self.get_qs_mestres(uo=uo)
            # 7 - MESTRADO
            # 31 - MESTRE+RSC-III (LEI 12772/12 ART 18)
            return self.get_qs_docentes_por_titulacao(titulacoes_ids=[7, 31], uo=uo)
        elif self.sigla == 'D':
            # return self.get_qs_doutores(uo=uo)
            # 8 - DOUTORADO
            return self.get_qs_docentes_por_titulacao(titulacoes_ids=[8], uo=uo)
        elif self.sigla == 'DO':
            return self.get_qs_docentes(uo)
        elif self.sigla == 'DOAP':
            return self.get_qs_docentes_ativos_permanentes(uo)
        elif self.sigla == 'DOAP_20':
            return self.get_qs_docentes_ativos_permanentes(uo=uo, jornada_trabalho='20 HORAS SEMANAIS')
        elif self.sigla == 'DOAP_40':
            return self.get_qs_docentes_ativos_permanentes(uo=uo, jornada_trabalho='40 HORAS SEMANAIS')
        elif self.sigla == 'DOAP_DDE':
            return self.get_qs_docentes_ativos_permanentes(uo=uo, jornada_trabalho='DEDICACAO EXCLUSIVA')
        elif self.sigla == 'DOST':
            return self.get_qs_docentes_substitutos_ou_temporarios(uo)
        elif self.sigla == 'DOC':
            return self.get_qs_docentes_cedidos(uo)
        # Variáveis que subsidiam o indicador DTI.
        elif self.sigla == 'DDESF':
            return self.get_qs_docentes_dedicacao_exclusiva(uo=uo, tem_funcao=False)
        elif self.sigla == 'DDECF':
            return self.get_qs_docentes_dedicacao_exclusiva(uo=uo, tem_funcao=True)
        elif self.sigla == 'D40SF':
            return self.get_qs_docentes_40h(uo=uo, tem_funcao=False)
        elif self.sigla == 'D40CF':
            return self.get_qs_docentes_40h(uo=uo, tem_funcao=True)
        elif self.sigla == 'D20SF':
            return self.get_qs_docentes_20h(uo=uo, tem_funcao=False)
        elif self.sigla == 'D20CF':
            return self.get_qs_docentes_20h(uo=uo, tem_funcao=True)
        elif self.sigla == 'DFG':
            return self.get_qs_docentes_funcao_fg(uo)
        elif self.sigla == 'DCD1':
            return self.get_qs_docentes_funcao_cd1(uo)
        elif self.sigla == 'DCD2':
            return self.get_qs_docentes_funcao_cd2(uo)
        elif self.sigla == 'DCD3':
            return self.get_qs_docentes_funcao_cd3(uo)
        elif self.sigla == 'DCD4':
            return self.get_qs_docentes_funcao_cd4(uo)

    def get_qs_com_filtro_aluno_convenio(self, queryset_list, variavel_academico_filtro):
        qs_result = []

        filtro_convenio = None
        if variavel_academico_filtro == VariavelAcademicoFiltro.SOMENTE_ALUNOS_COM_CONVENIO:
            filtro_convenio = False
        elif variavel_academico_filtro == VariavelAcademicoFiltro.SOMENTE_ALUNOS_SEM_CONVENIO:
            filtro_convenio = True

        for qs in queryset_list:
            if qs.model == Aluno:
                qs = qs.filter(convenio__isnull=filtro_convenio)
            elif qs.model == MatriculaPeriodo:
                qs = qs.filter(aluno__convenio__isnull=filtro_convenio)
            else:
                raise Exception('Domínio do queryset desconhecido. Impossível definir filtro de aluno e convênio.')

            qs_result.append(qs)

        return qs_result

    def get_filtro_emit_ug(self, uo, incluir_fav=False):
        codigos = ''
        if uo:
            for ug in UnidadeGestora.objects.filter(uo=uo):
                if not codigos:
                    codigos = ug.pk
                else:
                    codigos = f'{codigos}, {ug.pk}'
        if codigos:
            if incluir_fav:  # emit_ug = 4587 and
                return f' and (emit_ug in ({codigos}) or (fav_ug in ({codigos})))'
            return f' and emit_ug in ({codigos})'
        if uo:
            return ' and emit_ug in (-1)'
        return codigos

    def get_qs_despesas_custeios_nes(self, list=None, uo=None, for_diff=False):
        # despesas com custeios presentes nas notas de empenho
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        eventos_emp = ','.join(str(i) for i in Evento.list_empenhos())
        sql = f"""with recursive empenhos (empenho_id, emit_ug, ref_id, ptres, item_id, sb_nat, valor) as
                (select n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n, financeiro_evento e, financeiro_nelistaitens li,
                            financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                            financeiro_notaempenho rf, financeiro_programatrabalhoresumido pt
                        where rf.id = n.referencia_empenho_id
                            and pt.id = rf.ptres_id
                            and e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and n.referencia_empenho_id in (select distinct ne.id
                                                                from financeiro_notaempenho ne, financeiro_naturezadespesa nd,
                                                                    financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                                                where ne.referencia_empenho_id is null
                                                                    and ne.referencia_empenho_original = ''
                                                                    and nd.id = ne.natureza_despesa_id
                                                                    and pt.id = ne.ptres_id
                                                                    --and pt.id = 41
                                                                    and ci.id = pt.classificacao_institucional_id
                                                                    and pt.codigo != '031727' -- beneficio deve ser excluido
                                                                    and ci.codigo = '{gestao}'
                                                                    and nd.codigo like '33%%'
                                                                    and extract(YEAR FROM ne.data_emissao) = {ano_referencia})
                UNION ALL
                select distinct n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, empenhos.ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n
                             INNER JOIN empenhos ON n.referencia_empenho_id = empenhos.empenho_id,
                             financeiro_evento e, financeiro_nelistaitens li, financeiro_neitem it, financeiro_subelementonaturezadespesa nd
                        where e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and extract(YEAR FROM n.data_emissao) = {ano_referencia}
                )
                select * from (
                select codigo, nome, sum(valor)-sum(desconto) as valor , emit_ug
                    from (select sbnat_codigo as codigo, emit_ug,
                                sbnat_nome as nome,
                                case when evento in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento not in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as desconto
                                from (select ne.id as empenho_id, ne.emitente_ug_id as emit_ug, ne.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                                            nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, ev.tipo as evento
                                            from financeiro_notaempenho ne, financeiro_evento ev, financeiro_nelistaitens li,
                                                financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                                                financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                            where ne.referencia_empenho_id is null
                                                and ne.id = li.nota_empenho_id
                                                and li.id = it.lista_itens_id
                                                and nd.id = it.subitem_id
                                                and ev.id = ne.evento_id
                                                and pt.id = ne.ptres_id
                                                --and pt.id = 41
                                                and ci.id = pt.classificacao_institucional_id
                                                and pt.codigo != '031727' -- beneficio deve ser excluido
                                                and ci.codigo = '{gestao}'
                                                and nd.codigo like '33%%'
                                                and extract(YEAR FROM ne.data_emissao) = {ano_referencia}
                                    UNION ALL
                                    select * from empenhos) despesas
                                group by sbnat_codigo, sbnat_nome, evento, emit_ug) desp
                    group by codigo, nome, emit_ug
                ) list where valor != 0.00 {self.get_filtro_emit_ug(uo)}"""
        if for_diff:
            sql = f'SELECT ug.codigo, ug.nome, dados.codigo, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'
            return db.getget_list_list(sql)
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_pessoal_nes(self, list=None, uo=None, for_diff=False):
        # despesas com custeios presentes nas notas de empenho
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        eventos_emp = ','.join(str(i) for i in Evento.list_empenhos())
        sql = f"""with recursive empenhos (empenho_id, emit_ug, ref_id, ptres, item_id, sb_nat, valor) as
                (select n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n, financeiro_evento e, financeiro_nelistaitens li,
                            financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                            financeiro_notaempenho rf, financeiro_programatrabalhoresumido pt
                        where rf.id = n.referencia_empenho_id
                            and pt.id = rf.ptres_id
                            and e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and n.referencia_empenho_id in (select distinct ne.id
                                                                from financeiro_notaempenho ne, financeiro_naturezadespesa nd,
                                                                    financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                                                where ne.referencia_empenho_id is null
                                                                    and ne.referencia_empenho_original = ''
                                                                    and nd.id = ne.natureza_despesa_id
                                                                    and pt.id = ne.ptres_id
                                                                    and ci.id = pt.classificacao_institucional_id
                                                                    and ci.codigo = '{gestao}'
                                                                    and nd.codigo like '31%%'
                                                                    and extract(YEAR FROM ne.data_emissao) = {ano_referencia})
                UNION ALL
                select distinct n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, empenhos.ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n
                             INNER JOIN empenhos ON n.referencia_empenho_id = empenhos.empenho_id,
                             financeiro_evento e, financeiro_nelistaitens li, financeiro_neitem it, financeiro_subelementonaturezadespesa nd
                        where e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and extract(YEAR FROM n.data_emissao) = {ano_referencia}
                )
                select * from (
                select codigo, nome, sum(valor)-sum(desconto) as valor , emit_ug
                    from (select sbnat_codigo as codigo, emit_ug,
                                sbnat_nome as nome,
                                case when evento in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento not in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as desconto
                                from (select ne.id as empenho_id, ne.emitente_ug_id as emit_ug, ne.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                                            nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, ev.tipo as evento
                                            from financeiro_notaempenho ne, financeiro_evento ev, financeiro_nelistaitens li,
                                                financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                                                financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                            where ne.referencia_empenho_id is null
                                                and ne.id = li.nota_empenho_id
                                                and li.id = it.lista_itens_id
                                                and nd.id = it.subitem_id
                                                and ev.id = ne.evento_id
                                                and pt.id = ne.ptres_id
                                                and ci.id = pt.classificacao_institucional_id
                                                and ci.codigo = '{gestao}'
                                                and nd.codigo like '31%%'
                                                and extract(YEAR FROM ne.data_emissao) = {ano_referencia}
                                    UNION ALL
                                    select * from empenhos) despesas
                                group by sbnat_codigo, sbnat_nome, evento, emit_ug) desp
                    group by codigo, nome, emit_ug
                ) list where valor != 0.00 {self.get_filtro_emit_ug(uo)}"""
        if for_diff:
            sql = f'SELECT ug.codigo, ug.nome, dados.codigo, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'
            return db.get_list(sql)
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_custeios_ncs(self, list=None, uo=None, for_diff=False):
        # despesas com custeios presentes nas notas de sistem
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        evts_ncs_if = ','.join(str(i) for i in Evento.list_ncs_if())
        evts_debitos_ncs = ','.join(str(i) for i in Evento.list_debitos_ncs())
        evts_creditos_ncs = ','.join(str(i) for i in Evento.list_creditos_ncs())
        sql = f"""with ncs as
                (select nc.emitente_ug_id as emit_ug, g1.codigo as emit_gestao,
                        nc.favorecido_ug_id as fav_ug, g2.codigo as fav_gestao,
                        nd.codigo, nd.nome,
                        ev.tipo as evento,
                        it.id as it_id,
                        it.ptres_id as ptres_id,
                        it.valor
                    from financeiro_notacredito nc, financeiro_notacreditoitem it,
                        financeiro_evento ev, financeiro_naturezadespesa nd,
                        financeiro_classificacaoinstitucional g1, financeiro_classificacaoinstitucional g2
                    where nc.id = it.nota_credito_id
                        and g1.id = nc.emitente_ci_id
                        and g2.id = nc.favorecido_ci_id
                        and g1.codigo != g2.codigo
                        and ev.id = it.evento_id
                        and nd.id = it.natureza_despesa_id
                        and nd.codigo like '33%%'
                        --and it.ptres_id = 41
                        and extract(YEAR FROM nc.datahora_emissao) = {ano_referencia})
                select codigo || '00' as codigo, nome, sum(valor)-sum(desconto) as valor, emit_ug
                    from (select codigo, nome, evento, emit_ug,
                                case when evento in ({evts_debitos_ncs})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento in ({evts_creditos_ncs})
                                    then sum(valor)
                                    else 0
                                end as desconto
                            from (select distinct it.* -- seleciona as nc's realizadas pelo IF
                                        from ncs it,
                                            financeiro_programatrabalhoresumido pt,
                                            financeiro_classificacaoinstitucional ci
                                        where it.evento in ({evts_ncs_if})
                                            and it.ptres_id = pt.id
                                            --and pt.id = 41
                                            and ci.id = pt.classificacao_institucional_id
                                            and ci.codigo = '{gestao}'
                                    UNION ALL
                                    select distinct i.* -- seleciona as nc's devolvidas em relacao as nc's emitidas pelo IF
                                        from ncs i,
                                            (select emit_ug as favorecido,
                                                    fav_ug as emitente
                                                from ncs it,
                                                    financeiro_programatrabalhoresumido pt,
                                                    financeiro_classificacaoinstitucional ci
                                                where evento in ({evts_ncs_if})
                                                    and it.ptres_id = pt.id
                                                    --and pt.id = 41
                                                    and ci.id = pt.classificacao_institucional_id
                                                    and ci.codigo = '{gestao}') ret
                                        where i.emit_ug = emitente
                                            and i.fav_ug = favorecido) ncs
                            where 1=1 {self.get_filtro_emit_ug(uo, True)}
                            group by codigo, nome, evento, emit_ug) n
                    group by codigo, nome, emit_ug"""
        if for_diff:
            sql = f'SELECT ug.codigo, ug.nome, dados.codigo, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'
            return db.get_list(sql)
        else:
            sql = f'SELECT dados.codigo, dados.nome, dados.valor, dados.emit_ug FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'

        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_custeios_folha(self, list=False, uo=None):
        ano_referencia = PeriodoReferencia.get_ano_referencia()

        sql = """select codigo, descricao,
                        (sum(coalesce(despesa, 0.00)) - sum(coalesce(anulacao, 0.00))) as valor, emit_ug
                        from (select nd.codigo as codigo,
                                    nd.nome as descricao,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as despesa,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as anulacao,
                                    ns.ug_id as emit_ug
                                from financeiro_notasistemaitem it,
                                    financeiro_notasistema ns,
                                    financeiro_subelementonaturezadespesa nd,
                                    financeiro_evento ev
                                where ns.id = it.nota_sistema_id
                                    and nd.id = it.despesa_1_id
                                    and ev.id = it.evento_id
                                    and it.despesa_1_id is not null
                                    and ns.sistema_origem = 'FOLHA'
                                    and extract(YEAR FROM ns.data_emissao) = {}
                                    and nd.codigo in ('33903607','33903628')
                                group by ev.tipo, nd.nome, nd.codigo, ns.ug_id) t
                        where (despesa is not null or anulacao is not null) {}
                        group by codigo, descricao, emit_ug
                        order by codigo;""".format(
            ','.join(str(i) for i in Evento.list_aprop_despesas()),
            ','.join(str(i) for i in Evento.list_anulacao_aprop_despesas()),
            ano_referencia,
            self.get_filtro_emit_ug(uo),
        )
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_beneficios_folha(self, list=False, uo=None):
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        sql = """select codigo, descricao,
                        (sum(coalesce(despesa, 0.00)) - sum(coalesce(anulacao, 0.00))) as valor, emit_ug
                        from (select nd.codigo as codigo,
                                    nd.nome as descricao,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as despesa,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as anulacao,
                                    ns.ug_id as emit_ug
                                from financeiro_notasistemaitem it,
                                    financeiro_notasistema ns,
                                    financeiro_subelementonaturezadespesa nd,
                                    financeiro_evento ev
                                where ns.id = it.nota_sistema_id
                                    and nd.id = it.despesa_1_id
                                    and ev.id = it.evento_id
                                    and it.despesa_1_id is not null
                                    and ns.sistema_origem = 'FOLHA'
                                    and nd.codigo like '33%%'
                                    and extract(YEAR FROM ns.data_emissao) = {}
                                    and nd.codigo not in ('33903607','33903628') -- são considerados custeios
                                group by ev.tipo, nd.nome, nd.codigo, ns.ug_id) t
                        where (despesa is not null or anulacao is not null) {}
                        group by codigo, descricao, emit_ug
                        order by codigo;""".format(
            ','.join(str(i) for i in Evento.list_aprop_despesas()),
            ','.join(str(i) for i in Evento.list_anulacao_aprop_despesas()),
            ano_referencia,
            self.get_filtro_emit_ug(uo),
        )
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_beneficios_nes(self, list=False, uo=None):
        # despesas com custeios presentes nas notas de empenho
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        eventos_emp = ','.join(str(i) for i in Evento.list_empenhos())
        sql = f"""with recursive empenhos (empenho_id, emit_ug, ref_id, ptres, item_id, sb_nat, valor) as
                (select n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n, financeiro_evento e, financeiro_nelistaitens li,
                            financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                            financeiro_notaempenho rf, financeiro_programatrabalhoresumido pt
                        where rf.id = n.referencia_empenho_id
                            and pt.id = rf.ptres_id
                            and e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and n.referencia_empenho_id in (select distinct ne.id
                                                                from financeiro_notaempenho ne, financeiro_naturezadespesa nd,
                                                                    financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                                                where ne.referencia_empenho_id is null
                                                                    and ne.referencia_empenho_original = ''
                                                                    and nd.id = ne.natureza_despesa_id
                                                                    and pt.id = ne.ptres_id
                                                                    and ci.id = pt.classificacao_institucional_id
                                                                    and (pt.codigo = '031727' or pt.codigo = '044957')
                                                                    and ci.codigo = '{gestao}'
                                                                    and nd.codigo like '33%%'
                                                                    and extract(YEAR FROM ne.data_emissao) = {ano_referencia})
                UNION ALL
                select distinct n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, empenhos.ptres, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n
                             INNER JOIN empenhos ON n.referencia_empenho_id = empenhos.empenho_id,
                             financeiro_evento e, financeiro_nelistaitens li, financeiro_neitem it, financeiro_subelementonaturezadespesa nd
                        where e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and extract(YEAR FROM n.data_emissao) = {ano_referencia}
                )
                select * from (
                select codigo, nome, emit_ug, sum(valor)-sum(desconto) as valor
                    from (select sbnat_codigo as codigo,
                                sbnat_nome as nome,
                                emit_ug,
                                case when evento in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento not in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as desconto
                                from (select ne.id as empenho_id, ne.emitente_ug_id as emit_ug, ne.referencia_empenho_id as ref_id, pt.codigo as ptres, it.id as item_id,
                                            nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, ev.tipo as evento
                                            from financeiro_notaempenho ne, financeiro_evento ev, financeiro_nelistaitens li,
                                                financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                                                financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                            where ne.referencia_empenho_id is null
                                                and ne.id = li.nota_empenho_id
                                                and li.id = it.lista_itens_id
                                                and nd.id = it.subitem_id
                                                and ev.id = ne.evento_id
                                                and pt.id = ne.ptres_id
                                                and ci.id = pt.classificacao_institucional_id
                                                and (pt.codigo = '031727' or pt.codigo = '044957')
                                                and ci.codigo = '{gestao}'
                                                and nd.codigo like '33%%'
                                                and extract(YEAR FROM ne.data_emissao) = {ano_referencia}
                                    UNION ALL
                                    select * from empenhos) despesas
                                group by sbnat_codigo, sbnat_nome, evento, emit_ug) desp
                    group by codigo, nome, emit_ug
                ) list where valor != 0.00 {self.get_filtro_emit_ug(uo)};"""
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_pessoalativo(self, list=False, uo=None):
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        sql = """select codigo, descricao,
                           (sum(coalesce(despesa, 0.00)) - sum(coalesce(anulacao, 0.00))) as valor, emit_ug
                        from (select nd.codigo as codigo,
                                    nd.nome as descricao,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as despesa,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as anulacao,
                                    ns.ug_id as emit_ug
                                from financeiro_notasistemaitem it,
                                    financeiro_notasistema ns,
                                    financeiro_subelementonaturezadespesa nd,
                                    financeiro_evento ev
                                where ns.id = it.nota_sistema_id
                                    and nd.id = it.despesa_1_id
                                    and ev.id = it.evento_id
                                    and it.despesa_1_id is not null
                                    and ns.sistema_origem = 'FOLHA'
                                    and nd.codigo like '31%%'
                                    and extract(YEAR FROM ns.data_emissao) = {}
                                    and nd.codigo not like '319001%%' -- aposentados
                                    and nd.codigo not like '319003%%' -- pensionistas
                                    and nd.codigo not in ('31909129', '31909134', '31909141') -- referentes a setencas judiciais de aposentados e pensionistas
                                group by ev.tipo, nd.nome, nd.codigo, ns.ug_id) t
                        where (despesa is not null or anulacao is not null) {}
                        group by codigo, descricao, emit_ug
                        order by codigo;""".format(
            ','.join(str(i) for i in Evento.list_aprop_despesas()),
            ','.join(str(i) for i in Evento.list_anulacao_aprop_despesas()),
            ano_referencia,
            self.get_filtro_emit_ug(uo),
        )

        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_pessoal(self, list=False, uo=None):
        ano_referencia = PeriodoReferencia.get_ano_referencia()

        sql = """select codigo, descricao,
                       (sum(coalesce(despesa, 0.00)) - sum(coalesce(anulacao, 0.00))) as valor, emit_ug
                        from (select nd.codigo as codigo,
                                    nd.nome as descricao,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as despesa,
                                    case when ev.tipo in ({})
                                        then sum(valor)
                                    end as anulacao,
                                    ns.ug_id as emit_ug
                                from financeiro_notasistemaitem it,
                                    financeiro_notasistema ns,
                                    financeiro_subelementonaturezadespesa nd,
                                    financeiro_evento ev
                                where ns.id = it.nota_sistema_id
                                    and nd.id = it.despesa_1_id
                                    and ev.id = it.evento_id
                                    and it.despesa_1_id is not null
                                    and ns.sistema_origem = 'FOLHA'
                                    and nd.codigo like '31%%'
                                    and extract(YEAR FROM ns.data_emissao) = {}
                                group by ev.tipo, nd.nome, nd.codigo, ns.ug_id) t
                        where (despesa is not null or anulacao is not null) {}
                        group by codigo, descricao, emit_ug
                        order by codigo""".format(
            ','.join(str(i) for i in Evento.list_aprop_despesas()),
            ','.join(str(i) for i in Evento.list_anulacao_aprop_despesas()),
            ano_referencia,
            self.get_filtro_emit_ug(uo),
        )

        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_capital_nes(self, list=False, uo=None, for_diff=False):
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        eventos_emp = ','.join(str(i) for i in Evento.list_empenhos())
        sql = f"""with recursive empenhos (empenho_id, emit_ug, ref_id, item_id, sb_nat, valor) as
                (select n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n, financeiro_evento e, financeiro_nelistaitens li,
                            financeiro_neitem it, financeiro_subelementonaturezadespesa nd
                        where e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and n.referencia_empenho_id in (select distinct ne.id
                                                                from financeiro_notaempenho ne, financeiro_naturezadespesa nd,
                                                                    financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                                                where ne.referencia_empenho_id is null
                                                                    and ne.referencia_empenho_original = ''
                                                                    and nd.id = ne.natureza_despesa_id
                                                                    and pt.id = ne.ptres_id
                                                                    and ci.id = pt.classificacao_institucional_id
                                                                    and ci.codigo = '{gestao}'
                                                                    and nd.codigo like '44%%'
                                                                    and extract(YEAR FROM ne.data_emissao) = {ano_referencia})
                UNION ALL
                select n.id as empenho_id, n.emitente_ug_id as emit_ug, n.referencia_empenho_id as ref_id, it.id as item_id,
                        nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, e.tipo as evento
                        from financeiro_notaempenho n
                             INNER JOIN empenhos ON n.referencia_empenho_id = empenhos.empenho_id,
                             financeiro_evento e, financeiro_nelistaitens li, financeiro_neitem it, financeiro_subelementonaturezadespesa nd
                        where e.id = n.evento_id
                            and n.id = li.nota_empenho_id
                            and li.id = it.lista_itens_id
                            and nd.id = it.subitem_id
                            and extract(YEAR FROM n.data_emissao) = {ano_referencia}
                )
                select * from (
                select codigo, nome, sum(valor)-sum(desconto) as valor, emit_ug
                    from (select sbnat_codigo as codigo,
                                sbnat_nome as nome, emit_ug,
                                case when evento in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento not in ({eventos_emp})
                                    then sum(valor)
                                    else 0
                                end as desconto
                                from (select ne.id as empenho_id, ne.emitente_ug_id as emit_ug, ne.referencia_empenho_id as ref_id, it.id as item_id,
                                            nd.codigo as sbnat_codigo, nd.nome as sbnat_nome, it.valor_total as valor, ev.tipo as evento
                                            from financeiro_notaempenho ne, financeiro_evento ev, financeiro_nelistaitens li,
                                                financeiro_neitem it, financeiro_subelementonaturezadespesa nd,
                                                financeiro_programatrabalhoresumido pt, financeiro_classificacaoinstitucional ci
                                            where ne.referencia_empenho_id is null
                                                and ne.id = li.nota_empenho_id
                                                and li.id = it.lista_itens_id
                                                and nd.id = it.subitem_id
                                                and ev.id = ne.evento_id
                                                and pt.id = ne.ptres_id
                                                and ci.id = pt.classificacao_institucional_id
                                                and ci.codigo = '{gestao}'
                                                and nd.codigo like '44%%'
                                                and extract(YEAR FROM ne.data_emissao) = {ano_referencia}
                                    UNION ALL
                                    select * from empenhos) despesas
                                group by sbnat_codigo, sbnat_nome, evento, emit_ug) desp
                            group by codigo, nome, emit_ug
                ) list where valor != 0.00 {self.get_filtro_emit_ug(uo)}"""
        if for_diff:
            sql = f'SELECT ug.codigo, ug.nome, dados.codigo, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'
            return db.get_list(sql)
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_capital_ncs(self, list=None, uo=None, for_diff=False):
        # despesas com custeios presentes nas notas de sistem
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        evts_ncs_if = ','.join(str(i) for i in Evento.list_ncs_if())
        evts_debitos_ncs = ','.join(str(i) for i in Evento.list_debitos_ncs())
        evts_creditos_ncs = ','.join(str(i) for i in Evento.list_creditos_ncs())
        sql = f"""with ncs as
                (select nc.emitente_ug_id as emit_ug, g1.codigo as emit_gestao,
                        nc.favorecido_ug_id as fav_ug, g2.codigo as fav_gestao,
                        nd.codigo, nd.nome,
                        ev.tipo as evento,
                        it.id as it_id,
                        it.ptres_id as ptres_id,
                        it.valor
                    from financeiro_notacredito nc, financeiro_notacreditoitem it,
                        financeiro_evento ev, financeiro_naturezadespesa nd,
                        financeiro_classificacaoinstitucional g1, financeiro_classificacaoinstitucional g2
                    where nc.id = it.nota_credito_id
                        and g1.id = nc.emitente_ci_id
                        and g2.id = nc.favorecido_ci_id
                        and g1.codigo != g2.codigo
                        and ev.id = it.evento_id
                        and nd.id = it.natureza_despesa_id
                        and nd.codigo like '44%%'
                        and extract(YEAR FROM nc.datahora_emissao) = {ano_referencia})
                select emit_ug, codigo || '00' as codigo, nome, sum(valor)-sum(desconto) as valor
                    from (select codigo, nome, emit_ug, evento,
                                case when evento in ({evts_debitos_ncs})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento in ({evts_creditos_ncs})
                                    then sum(valor)
                                    else 0
                                end as desconto
                            from (select distinct it.* -- seleciona as nc's realizadas pelo IF
                                        from ncs it,
                                            financeiro_programatrabalhoresumido pt,
                                            financeiro_classificacaoinstitucional ci
                                        where it.evento in ({evts_ncs_if})
                                            and it.ptres_id = pt.id
                                            and ci.id = pt.classificacao_institucional_id
                                            and ci.codigo = '{gestao}'
                                    UNION ALL
                                    select distinct i.* -- seleciona as nc's devolvidas em relacao as nc's emitidas pelo IF
                                        from ncs i,
                                            (select emit_ug as favorecido,
                                                    fav_ug as emitente
                                                from ncs it,
                                                    financeiro_programatrabalhoresumido pt,
                                                    financeiro_classificacaoinstitucional ci
                                                where evento in ({evts_ncs_if})
                                                    and it.ptres_id = pt.id
                                                    and ci.id = pt.classificacao_institucional_id
                                                    and ci.codigo = '{gestao}') ret
                                        where i.emit_ug = emitente
                                            and i.fav_ug = favorecido) ncs
                            where 1=1 {self.get_filtro_emit_ug(uo)}
                            group by codigo, nome, emit_ug, evento) n
                    group by codigo, nome, emit_ug"""
        if for_diff:
            sql = f'SELECT ug.codigo, ug.nome, dados.codigo, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'
            return db.get_list(sql)
        else:
            sql = f'SELECT dados.codigo, dados.nome, dados.valor FROM ({sql}) AS dados JOIN financeiro_unidadegestora ug ON ug.id = emit_ug ORDER BY ug.codigo, dados.codigo'

        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def get_qs_despesas_precatorios_ncs(self, list=None, uo=None):
        ano_referencia = PeriodoReferencia.get_ano_referencia()
        # despesas com custeios presentes nas notas de sistem
        gestao = Configuracao._get_conf_por_chave('comum', 'instituicao_identificador').valor or ''
        evts_ncs_if = ','.join(str(i) for i in Evento.list_ncs_if())
        evts_debitos_ncs = ','.join(str(i) for i in Evento.list_debitos_ncs())
        evts_creditos_ncs = ','.join(str(i) for i in Evento.list_creditos_ncs())
        sql = f"""with ncs as
                (select nc.emitente_ug_id as emit_ug, g1.codigo as emit_gestao,
                        nc.favorecido_ug_id as fav_ug, g2.codigo as fav_gestao,
                        nd.codigo, nd.nome,
                        ev.tipo as evento,
                        it.id as it_id,
                        it.ptres_id as ptres_id,
                        it.valor
                    from financeiro_notacredito nc, financeiro_notacreditoitem it,
                        financeiro_evento ev, financeiro_naturezadespesa nd,
                        financeiro_classificacaoinstitucional g1, financeiro_classificacaoinstitucional g2
                    where nc.id = it.nota_credito_id
                        and g1.id = nc.emitente_ci_id
                        and g2.id = nc.favorecido_ci_id
                        and g1.codigo != g2.codigo
                        and ev.id = it.evento_id
                        and nd.id = it.natureza_despesa_id
                        and extract(YEAR FROM nc.datahora_emissao) = {ano_referencia}
                        and ev.codigo in ('301019','301023','306019'))
                select codigo || '00' as codigo, nome, sum(valor)-sum(desconto) as valor, emit_ug
                    from (select codigo, nome, emit_ug, evento,
                                case when evento in ({evts_debitos_ncs})
                                    then sum(valor)
                                    else 0
                                end as valor,
                                case when evento in ({evts_creditos_ncs})
                                    then sum(valor)
                                    else 0
                                end as desconto
                            from (select distinct it.* -- seleciona as nc's realizadas pelo IF
                                        from ncs it,
                                            financeiro_programatrabalhoresumido pt,
                                            financeiro_classificacaoinstitucional ci
                                        where it.evento in ({evts_ncs_if})
                                            and it.ptres_id = pt.id
                                            and ci.id = pt.classificacao_institucional_id
                                            and ci.codigo = '{gestao}'
                                    UNION ALL
                                    select distinct i.* -- seleciona as nc's devolvidas em relacao as nc's emitidas pelo IF
                                        from ncs i,
                                            (select emit_ug as favorecido,
                                                    fav_ug as emitente
                                                from ncs it,
                                                    financeiro_programatrabalhoresumido pt,
                                                    financeiro_classificacaoinstitucional ci
                                                where evento in ({evts_ncs_if})
                                                    and it.ptres_id = pt.id
                                                    and ci.id = pt.classificacao_institucional_id
                                                    and ci.codigo = '{gestao}') ret
                                        where i.emit_ug = emitente
                                            and i.fav_ug = favorecido) ncs
                            where 1=1 {self.get_filtro_emit_ug(uo)}
                            group by codigo, nome, emit_ug, evento) n
                    group by codigo, nome, emit_ug;"""
        if list:
            return sorted(self.normalizar_gastos(db.get_list(sql)), key=lambda despesa: despesa[0])
        else:
            return db.get_dict(sql)

    def normalizar_gastos(self, lista):
        if lista:
            index = len(lista[0]) - 1
            for item in lista:
                try:
                    item[index] = UnidadeGestora.objects.get(pk=item[index]).codigo
                except Exception:
                    pass
        return lista

    def get_valor_custeios(self, uo=None):
        valor = 0
        for despesa in self.get_qs_despesas_custeios_nes(uo=uo) + self.get_qs_despesas_custeios_folha(uo=uo):
            valor += despesa['valor']
        return valor

    def get_valor_beneficios(self, uo=None):
        valor = 0
        for despesa in self.get_qs_despesas_beneficios_folha(uo=uo) + self.get_qs_despesas_beneficios_nes(uo=uo):
            valor += despesa['valor']
        return valor

    def get_valor_GPA(self, uo=None):
        valor = 0
        for despesa in self.get_qs_despesas_pessoalativo(uo=uo):
            valor += despesa['valor']
        return valor

    def get_valor_GOC(self, uo=None):
        return self.get_valor_custeios(uo=uo)

    def get_valor_GPE(self, uo=None):
        valor = 0
        for despesa in self.get_qs_despesas_pessoal_nes(uo=uo):
            valor += despesa['valor']
        return valor

    def get_valor_GCA(self, uo=None):
        valor = 0
        for despesa in self.get_qs_despesas_capital_nes(uo=uo) + self.get_qs_despesas_capital_ncs(uo=uo):
            valor += despesa['valor']
        return valor

    def get_valor_GCO(self, uo=None):
        return self.get_valor_custeios(uo=uo) + self.get_valor_beneficios(uo=uo) + self.get_valor_GPA(uo=uo)

    def get_valor_GTO(self, uo=None):
        # gastos totais com custeios + beneficios + capital + pessoal
        return self.get_valor_custeios(uo=uo) + self.get_valor_beneficios(uo=uo) + self.get_valor_GCA(uo=uo) + self.get_valor_GPE(uo=uo)

    # Rotina antiga. Apresentava problemas relatados por Solange no chamado 26944
    # https://suap.ifrn.edu.br/centralservicos/chamado/26944/
    # def get_qs_renda_familiar(self, limite_inferior=0, limite_superior=1000, uo=None):
    #     qsa = Aluno.objects.filter(historicorendafamiliar__numero_salarios__gte=Decimal(str(limite_inferior)), historicorendafamiliar__numero_salarios__lt=Decimal(str(limite_superior))).order_by('pessoa_fisica__nome')
    #     data_limite = '3000-01-01'
    #     qsa = qsa.extra(where=['"ae_historicorendafamiliar"."id" = (SELECT "id" from "ae_historicorendafamiliar" WHERE "aluno_id" = "edu_aluno"."id" AND "data"<=\''+data_limite+'\' ORDER BY "id" DESC LIMIT 1)'])
    #     if uo: qsa = qsa.filter(curso_campus__diretoria__setor__uo=uo)
    #     return qsa

    # Rotina nova, levando em conta a variável AM (Alunos Matriculados). No caso agora o valor da variável RFP será
    # um subconjunto de AM, atendendo assim ao chamado 26944.
    def get_qs_renda_familiar(self, limite_inferior=0, limite_superior=1000, uo=None):
        qs_rfp = self.get_qs_alunos_matriculados(uo=uo)[0]
        qs_rfp = qs_rfp.filter(
            aluno__historicorendafamiliar__numero_salarios__gte=Decimal(str(limite_inferior)),
            aluno__historicorendafamiliar__numero_salarios__lt=Decimal(str(limite_superior)),
        ).order_by('aluno__pessoa_fisica__nome')

        filtro_data_limite_historico_familiar = " AND \"data\" between '{}' and '{}' ".format(
            PeriodoReferencia.get_data_base().strftime('%Y-%m-%d'), PeriodoReferencia.get_data_limite().strftime('%Y-%m-%d')
        )
        qs_rfp = qs_rfp.extra(
            where=[
                f'"ae_historicorendafamiliar"."id" = (SELECT "id" from "ae_historicorendafamiliar" WHERE "aluno_id" = "edu_aluno"."id" {filtro_data_limite_historico_familiar} ORDER BY "id" DESC LIMIT 1)'
            ]
        )
        return qs_rfp

    def get_valor_renda_familiar(self, limite_inferior=0, limite_superior=1000, uo=None):
        qs = self.get_qs_renda_familiar(limite_inferior, limite_superior, uo)
        r = next(iter(qs.aggregate(Avg('aluno__historicorendafamiliar__numero_salarios')).values())) or 0
        return Decimal(str(round(r, 2)))


class Indicador(models.ModelPlus):
    ORGAO_REGULAMENTADOR_TCU = 'TCU'
    ORGAO_REGULAMENTADOR_MEC = 'MEC'
    ORGAO_REGULAMENTADOR_OUTROS = 'OUTROS'
    ORGAO_REGULAMENTADOR_TIPO_CHOICES = [
        [ORGAO_REGULAMENTADOR_TCU, 'TCU'],
        [ORGAO_REGULAMENTADOR_MEC, 'MEC'],
        [ORGAO_REGULAMENTADOR_OUTROS, 'Outros'],
    ]

    sigla = models.CharField(max_length=20, verbose_name='Sigla')
    nome = models.CharField(max_length=100, verbose_name='Nome')
    objetivo = models.TextField(max_length=510, verbose_name='Objetivo')
    responsavel = models.CharField(max_length=50, verbose_name='Área Responsável')
    formula = models.CharField(max_length=100, verbose_name='Fórmula', help_text='Formula utilizada para calcular o valor do indicador em tempo real')
    orgao_regulamentador = models.CharField('Tipo', max_length=10, choices=ORGAO_REGULAMENTADOR_TIPO_CHOICES, default=ORGAO_REGULAMENTADOR_OUTROS)

    class Meta:
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'

        permissions = (('pode_exibir_indicadores', 'Pode exibir indicadores'),)

    @property
    def processado(self):
        return all(variavel.recuperar_valor(pk=variavel.pk, uo_pk=0, processar_valor=False) != '' for variavel in self.get_variaveis())

    def get_variaveis(self):
        variaveis = []
        for token in (
            self.formula.replace(' ', '')
            .replace(')', '')
            .replace('(', '')
            .replace('*', ':')
            .replace('/', ':')
            .replace('+', ':')
            .replace('-', ':')
            .split(':')
        ):
            if not token.isdigit():
                variavel = Variavel.objects.get(sigla=token)
                variaveis.append(variavel)
        return variaveis

    def get_formula_valorada(self, uo=None, user=None):
        index = None
        if uo:
            index = uo.sigla

        if hasattr(self, 'formula_valorada'):
            if index in self.formula_valorada:
                return self.formula_valorada[index]
        else:
            self.formula_valorada = {}
        formula = ' {} '.format(
            self.formula.replace(' ', '')
            .replace(')', ' ) ')
            .replace('(', ' ( ')
            .replace('*', ' * ')
            .replace('/', ' / ')
            .replace('+', ' + ')
            .replace('-', ' - ')
        )
        for variavel in self.get_variaveis():
            # O ajuste '{}.0' garanti que as divisões internas não serão truncadas.
            # Ex: Com o referido ajuste, a fórmula '(  (1053+187)  * 1 )  +  (  (33+39)  / 2 )  +  (23/ 4 )  ) tem
            # como valor final 1281.75, já sem esse ajuste seria exibido 1281.
            if variavel.is_decimal():
                formula = formula.replace(f' {variavel.sigla} ', f' {variavel.get_valor(uo=uo, user=user)} ')
            else:
                formula = formula.replace(f' {variavel.sigla} ', f' {variavel.get_valor(uo=uo, user=user)}.0 ')

        self.formula_valorada[index] = formula
        return self.formula_valorada[index]

    get_formula_valorada.short_description = 'Fórmula Valorada'

    def get_valor(self, uo=None, user=None):
        try:
            return eval_expr(f'1.0*{self.get_formula_valorada(uo=uo, user=user).strip()}')
        except Exception:
            return Decimal('0')

    get_valor.short_description = 'Valor'

    def get_valor_formatado(self, uo=None, user=None):
        return mask_money(self.get_valor(uo=uo, user=user))

    def recuperar_formula_valorada(self, uo=None):
        index = None
        uo_pk = uo and uo.pk or 0
        if uo:
            index = uo.sigla

        if hasattr(self, 'formula_valorada'):
            if index in self.formula_valorada:
                return self.formula_valorada[index]
        else:
            self.formula_valorada = {}
        formula = ' {} '.format(
            self.formula.replace(' ', '')
            .replace(')', ' ) ')
            .replace('(', ' ( ')
            .replace('*', ' * ')
            .replace('/', ' / ')
            .replace('+', ' + ')
            .replace('-', ' - ')
        )
        for variavel in self.get_variaveis():
            # O ajuste '{}.0' garanti que as divisões internas não serão truncadas.
            # Ex: Com o referido ajuste, a fórmula '(  (1053+187)  * 1 )  +  (  (33+39)  / 2 )  +  (23/ 4 )  ) tem
            # como valor final 1281.75, já sem esse ajuste seria exibido 1281.
            if variavel.is_decimal():
                formula = formula.replace(f' {variavel.sigla} ', f' {variavel.recuperar_valor(pk=variavel.pk, uo_pk=uo_pk, processar_valor=False)} ')
            else:
                formula = formula.replace(
                    f' {variavel.sigla} ', f' {variavel.recuperar_valor(pk=variavel.pk, uo_pk=uo_pk, processar_valor=False)}.0 '
                )

        self.formula_valorada[index] = formula
        return self.formula_valorada[index]

    get_formula_valorada.short_description = 'Fórmula Valorada'

    def recuperar_valor(self, uo=None):
        try:
            return eval_expr(f'1.0*{self.recuperar_formula_valorada(uo=uo).strip()}')
        except Exception:
            return Decimal('0')

    recuperar_valor.short_description = 'Valor'

    def recuperar_valor_formatado(self, uo=None):
        return mask_money(self.recuperar_valor(uo=uo))

    def __str__(self):
        return self.nome


class HistoricoVariavel(models.ModelPlus):
    variavel = models.ForeignKeyPlus(Variavel, on_delete=models.CASCADE)
    content_type = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    objeto = GenericForeignKey('content_type', 'object_id')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    data_entrada = models.DateField()
    data_saida = models.DateField(null=True)

    @staticmethod
    def armazenar_dados(variavel):
        hoje = datetime.date.today()
        HistoricoVariavel.objects.filter(data_saida__isnull=True).update(data_saida=hoje)
        for uo in UnidadeOrganizacional.objects.suap().all():
            for qs in variavel.get_querysets(uo):
                for objeto in qs.all():
                    content_type = ContentType.objects.get_for_model(qs.model)
                    registros = HistoricoVariavel.objects.filter(
                        variavel=variavel, content_type=content_type, object_id=objeto.pk, uo_id=uo.pk
                    ).order_by('-id')
                    if registros.exists():
                        registro = registros[0]
                        if registro.data_saida == hoje:
                            HistoricoVariavel.objects.filter(pk=registro.pk).update(data_saida=None)
                        else:
                            HistoricoVariavel.objects.create(
                                variavel_id=variavel.pk, content_type=content_type, object_id=objeto.pk, uo_id=uo.pk, data_entrada=hoje
                            )
                    else:
                        HistoricoVariavel.objects.create(
                            variavel_id=variavel.pk, content_type=content_type, object_id=objeto.pk, uo_id=uo.pk, data_entrada=hoje
                        )
