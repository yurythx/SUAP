import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Exists, OuterRef
from django.db.models.aggregates import Count
from django.shortcuts import get_object_or_404

from comum.models import Ano, Configuracao
from djtools.html.graficos import ColumnChart, GroupedColumnChart, PieChart
from djtools.templatetags.filters import format_
from djtools.utils import (
    XlsResponse,
    group_required,
    httprr,
    permission_required,
    rtr,
    running_tests,
)
from edu import tasks
from edu.forms import (
    EstatisticaForm,
    ExportarAlunosCaracterizacaoForm,
    FiltroAlunosForm,
    IndicadoresForm,
    RelatorioCoordenacaoCursoForm,
    RelatorioDependenteForm,
    RelatorioDiarioForm,
    RelatorioFaltasForm,
    RelatorioForm,
    RelatorioMigracaoForm,
    RelatorioPeriodosAbertosForm,
    SalvarRelatorioForm,
)
from edu.models import (
    Aluno,
    CursoCampus,
    Diretoria,
    HistoricoRelatorio,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
    Modalidade,
    RegistroEmissaoDiploma,
    SituacaoMatricula,
    Turma,
)
from edu.utils import TabelaAlunoCursoCampusPolo, TabelaMPPoloNivelEnsino, TabelaResumoAluno, TabelaResumoMPCurso
from rh.models import UnidadeOrganizacional

from ..importador import DAO
from .pdfs import assinaturas_alunos_pdf, etiquetas_alunos_pdf


@rtr()
@login_required()
@permission_required('edu.gerar_relatorio')
def relatorio(request):
    title = 'Listagem de Alunos'
    quantidade_itens = 25

    form = RelatorioForm(request, data=request.GET or None)
    if 'editar' in request.GET:
        formatacao = None
    else:
        if form.is_valid():
            exibicao_choices = (
                form.EXIBICAO_CHOICES + RelatorioForm.PENDENCIAS_EXIBICAO_CHOICES + form.EXIBICAO_COMUNICACAO + form.EXIBICAO_DADOS_PESSOAIS
            )
            ano_letivo = form.cleaned_data.get('ano_letivo')
            periodo_letivo = int(form.cleaned_data.get('periodo_letivo', 0) or 0)
            query_string = request.META.get('QUERY_STRING', '').encode('utf-8').hex()
            alunos, filtros = form.processar()
            quantidade_itens = form.cleaned_data['quantidade_itens']
            alunos_list = request.POST.getlist('select_aluno')
            if alunos_list:
                alunos = Aluno.objects.filter(id__in=alunos_list)
            formatacao = form.cleaned_data['formatacao']
            if formatacao == 'educacenso' or formatacao == 'censup':
                for aluno in alunos:
                    qs = MatriculaPeriodo.objects.filter(aluno=aluno).order_by('-ano_letivo__ano', '-periodo_letivo')
                    if periodo_letivo not in [None, '', '0', 0]:
                        qs = qs.filter(periodo_letivo=periodo_letivo)
                    if ano_letivo:
                        qs = qs.filter(ano_letivo=ano_letivo)
                    if qs:
                        aluno.matricula_periodo = qs[0]
            elif formatacao == 'pordisciplinacursando' or formatacao == 'pordisciplinapendente':
                alunos = alunos.filter(matriz__isnull=False)
            elif formatacao == 'tcc':
                alunos = alunos.filter(matriculaperiodo__projetofinal__isnull=False)
            elif formatacao == 'pe_de_meia':
                # filtrar situação matriculado
                alunos = alunos.filter(
                    situacao__in=[
                        SituacaoMatricula.MATRICULADO,
                        SituacaoMatricula.CONCLUDENTE,
                        SituacaoMatricula.AGUARDANDO_ENADE,
                        SituacaoMatricula.AGUARDANDO_COLACAO_DE_GRAU,
                    ]
                )
                alunos = alunos.filter(curso_campus__modalidade__in=[Modalidade.INTEGRADO, Modalidade.CONCOMITANTE])

            ordenacao = ['curso_campus__diretoria__setor__uo', 'curso_campus_id']
            if form.cleaned_data['ordenacao'] == 'Matrícula':
                ordenacao.append('matricula')
            else:
                ordenacao.append('pessoa_fisica__nome')

            alunos = alunos.order_by(*ordenacao)

            agrupamento = form.cleaned_data['agrupamento']
            if agrupamento == 'Turma':
                for aluno in alunos:
                    aluno.turma = aluno.get_ultima_matricula_periodo(excluir_em_aberto=True).turma

            campos_exibicao = form.cleaned_data['exibicao']
            if (ano_letivo and not periodo_letivo) or (periodo_letivo and not ano_letivo):
                if 'get_situacao_periodo_referencia' in campos_exibicao:
                    campos_exibicao.remove('get_situacao_periodo_referencia')
                    messages.warning(request, 'Selecione o "Ano Letivo" e o "Período Letivo" para exibir a "Situação no Período"')
                if 'get_frequencia_periodo_referencia' in campos_exibicao:
                    campos_exibicao.remove('get_frequencia_periodo_referencia')
                    messages.warning(request, 'Selecione o "Ano Letivo" e o "Período Letivo" para exibir a "Frequência no Período"')
            if 'pendencias' in campos_exibicao:
                campos_exibicao.remove('pendencias')
                for chave, _valor in RelatorioForm.PENDENCIAS_EXIBICAO_CHOICES:
                    campos_exibicao.append(chave)

            if 'imprimir' in request.POST:
                if alunos.count() > 500:
                    messages.error(request, 'Limite de 500 alunos atingido! Selecione mais filtros para poder "Expotar para PDF"')
                    return locals()
                return tasks.relatorio_pdf(request, alunos, filtros, formatacao, campos_exibicao)

            if 'assinaturas' in request.POST:
                return assinaturas_alunos_pdf(request, alunos, filtros, agrupamento)

            if 'carometros' in request.POST:
                return tasks.carometros_alunos_pdf(request, alunos, filtros)

            if 'etiquetas' in request.POST:
                etiquetas = request.POST['etiquetas']
                return etiquetas_alunos_pdf(request, alunos, etiquetas)

            if 'cracha' in request.POST:
                return tasks.imprime_cracha(request, alunos)

            if 'xls' in request.POST or 'xls_anonimo' in request.POST:
                if formatacao == 'educacenso':
                    return tasks.relatorio_educacenso_xls(alunos, ano_letivo, periodo_letivo)
                elif formatacao == 'censup':
                    return tasks.relatorio_censup_xls(alunos, ano_letivo, periodo_letivo)
                elif formatacao == 'pordisciplinapendente':
                    return tasks.relatorio_pordisciplinapendente_xls(alunos)
                elif formatacao == 'pordisciplinacursando':
                    return tasks.relatorio_pordisciplinacursando_xls(alunos)
                elif formatacao == 'tcc':
                    return tasks.relatorio_tcc_xls(alunos)
                elif formatacao == 'pe_de_meia':
                    is_administrador = request.user.groups.filter(name='Administrador Acadêmico').exists()
                    return tasks.relatorio_pe_de_meia_csv(is_administrador, alunos)
                elif formatacao == 'relatorio_conselho_classe':
                    return tasks.relatorio_conselho_classe_csv(alunos, ano_letivo, periodo_letivo)
                # Se for qualquer outra formatação
                else:
                    cabecalhos = exibicao_choices
                    return tasks.exportar_listagem_alunos_xls(request, alunos, campos_exibicao, cabecalhos, filtros, ano_letivo, periodo_letivo)

    return locals()


@login_required()
@rtr()
def salvar_relatorio(request, tipo, query_string):
    title = 'Salvar Consulta'
    form = SalvarRelatorioForm(request.POST or None, tipo=tipo)
    if form.is_valid():
        form.processar(query_string)
        return httprr(f'/edu/meus_relatorios/{tipo}/', 'Consulta salva com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def meus_relatorios(request, tipo):
    del_historicorelatorio = request.GET.get('del_historicorelatorio')
    if del_historicorelatorio:
        historicorelatorio = get_object_or_404(HistoricoRelatorio, id=del_historicorelatorio, user=request.user)
        url_sem_parametro = historicorelatorio.get_url_sem_parametro()
        historicorelatorio.delete()
        return httprr(url_sem_parametro, 'Consulta excluída com sucesso.')
    title = 'Consultas salvas anteriormente'
    relatorios = request.user.historicorelatorio_set.filter(tipo=tipo)
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def alunos_dados_incompletos(request, diretoria_id=None, cursos_id=None):
    title = 'Relatório de alunos concluídos com dados incompletos'
    cursos_id = cursos_id.split('_') if cursos_id else None

    subquery_diploma = RegistroEmissaoDiploma.objects.filter(aluno_id=OuterRef('id'), cancelado=False)
    alunos_dados_incompletos_para_diploma = (
        Aluno.get_alunos_concluidos_dados_incompletos(diretoria_id, cursos_id)
        .select_related('curso_campus', 'pessoa_fisica', 'naturalidade')
        .annotate(tem_diploma=Exists(subquery_diploma))
    )

    return locals()


@rtr()
@group_required('Coordenador de Curso')
def alunos_sem_turma(request, ano, periodo):
    title = f'Alunos sem Turma em {ano}.{periodo}'
    alunos = Aluno.get_alunos_sem_turma(request.user, ano, periodo)
    return locals()


@rtr('alunos_sem_turma.html')
@group_required('Coordenador de Curso')
def alunos_sem_turma_curso(request, ano, periodo, curso_id):
    title = f'Alunos sem Turma em {ano}.{periodo}'
    alunos = Aluno.get_alunos_sem_turma(request.user, ano, periodo, curso_id)
    return locals()


@rtr()
@login_required()
@permission_required('ponto.pode_ver_frequencia_propria')
def relatorio_disciplinas_aluno(request, pk, tipo):
    obj = get_object_or_404(Aluno.locals, pk=pk)
    if tipo == 'pendente':
        componentes = obj.get_componentes_obrigatorios_pendentes(True)
        title = f'Relatório de Disciplinas Pendentes {obj}'
    else:
        if request.GET.get('ano_letivo'):
            obj.ano_letivo_referencia = request.GET.get('ano_letivo')
        if request.GET.get('periodo_letivo'):
            obj.periodo_letivo_referencia = request.GET.get('periodo_letivo', None)
        matriculas_diario = obj.get_matriculas_diario_cursando()
        title = f'Relatório de Disciplinas Cursando {obj}'
    return locals()


def _grafico_raca(alunos_caracterizados, caracterizacao_dos_alunos):
    """Gráfico de distribuição por raça/cor dos alunos caracterizados."""
    dados_raca = []
    alunos_por_raca = caracterizacao_dos_alunos.values('raca__descricao').annotate(qtd=Count('raca__descricao')).order_by('raca__descricao')
    total_raca = 0
    for registro in alunos_por_raca:
        dados_raca.append([registro['raca__descricao'], registro['qtd']])
        total_raca += registro['qtd']
    if dados_raca and dados_raca[-1][1] == 0:
        dados_raca.pop()
    if alunos_caracterizados.count() - total_raca > 0:
        dados_raca.append(['Não Informado', alunos_caracterizados.count() - total_raca])
    grafico_raca = ColumnChart('grafico_raca', title='Raça/Cor', subtitle='Total de Alunos por Raça/Cor', minPointLength=0, data=dados_raca)
    grafico_raca.id = 'grafico_raca'
    return grafico_raca


def _grafico_idade(alunos_caracterizados):
    """Gráfico de distribuição por faixa etária dos alunos caracterizados."""
    dados_idade = []
    hoje = datetime.datetime.now()
    date_ate_14 = hoje - relativedelta(years=14)
    date_ate_17 = hoje - relativedelta(years=17)
    date_ate_29 = hoje - relativedelta(years=29)
    date_ate_49 = hoje - relativedelta(years=49)
    ATE_14 = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__gte=date_ate_14)
    ENTRE_15_17 = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__lt=date_ate_14, pessoa_fisica__nascimento_data__gte=date_ate_17)
    ENTRE_18_29 = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__lt=date_ate_17, pessoa_fisica__nascimento_data__gte=date_ate_29)
    ENTRE_30_49 = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__lt=date_ate_29, pessoa_fisica__nascimento_data__gte=date_ate_49)
    ACIMA_50 = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__lt=date_ate_49)
    NAO_INFORMADO = alunos_caracterizados.filter(pessoa_fisica__nascimento_data__isnull=True)
    dados_idade.append(['Até 14 anos', ATE_14.count()])
    dados_idade.append(['Entre 15 e 17 anos', ENTRE_15_17.count()])
    dados_idade.append(['Entre 18 e 29 anos', ENTRE_18_29.count()])
    dados_idade.append(['Entre 30 e 49 anos', ENTRE_30_49.count()])
    dados_idade.append(['Acima de 50 anos', ACIMA_50.count()])
    dados_idade.append(['Não informado', NAO_INFORMADO.count()])
    grafico_idade = ColumnChart(
        'grafico_idade', title='Faixa Etária', subtitle='Total de Alunos por Faixa Etária', minPointLength=0, data=dados_idade
    )
    grafico_idade.id = 'grafico_idade'
    return grafico_idade


def _grafico_renda(caracterizacao_dos_alunos):
    """Gráfico de distribuição por renda per capita (em salários mínimos)."""
    dados_renda = []
    sm = Decimal(Configuracao.get_valor_por_chave('comum', 'salario_minimo'))
    dados_renda.append(
        [
            'Maior que 5 SM',
            caracterizacao_dos_alunos.filter(~Q(qtd_pessoas_domicilio=0))
            .extra(where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > ({sm} * 5)'])
            .count(),
        ]
    )
    dados_renda.append(['Não informado', caracterizacao_dos_alunos.filter(qtd_pessoas_domicilio=0).count()])
    dados_renda.append(
        [
            'Até ½ SM',
            caracterizacao_dos_alunos.filter(~Q(qtd_pessoas_domicilio=0))
            .extra(where=[f'renda_bruta_familiar/qtd_pessoas_domicilio <= {sm}/2'])
            .count(),
        ]
    )
    for qtd_inicial in [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5]:
        if qtd_inicial % 1 == 0:
            label = f'Entre {qtd_inicial} SM e {qtd_inicial} ½ SM'
        else:
            label = 'Entre {} ½ SM e {} SM'.format(int(qtd_inicial - 0.5) or '', int(qtd_inicial + 0.5))
        # convertendo qtd_inicial para string por causa do erro que estava dando no gunicorn e nginx
        inicial = Decimal(str(qtd_inicial)) * sm
        final = (Decimal(str(qtd_inicial)) + Decimal('0.5')) * sm
        dados_renda.append(
            [
                label,
                caracterizacao_dos_alunos.filter(~Q(qtd_pessoas_domicilio=0))
                .extra(
                    where=[f'renda_bruta_familiar/qtd_pessoas_domicilio > ({inicial}) AND renda_bruta_familiar/qtd_pessoas_domicilio <= ({final})']
                )
                .count(),
            ]
        )
    grafico_renda = ColumnChart(
        'grafico_renda',
        title='Renda Per Capita',
        subtitle='Total de Alunos por Per Capita com base no salário mínimo (SM)',
        minPointLength=0,
        data=dados_renda,
    )
    grafico_renda.id = 'grafico_renda'
    return grafico_renda


def _distribuicoes_caracterizacao(alunos):
    """Gráficos de distribuição (raça, faixa etária, renda) dos alunos caracterizados.

    Devolve dict vazio quando não há caracterizados, para o template apenas omitir
    os gráficos.
    """
    alunos_caracterizados = alunos.filter(caracterizacao__isnull=False)
    if not alunos_caracterizados:
        return {}
    caracterizacao_dos_alunos = apps.get_model('ae.Caracterizacao').objects.filter(aluno__in=alunos_caracterizados.values_list('id'))
    return {
        'grafico_raca': _grafico_raca(alunos_caracterizados, caracterizacao_dos_alunos),
        'grafico_idade': _grafico_idade(alunos_caracterizados),
        'grafico_renda': _grafico_renda(caracterizacao_dos_alunos),
    }


def _exportar_estatistica_xls(request, form, alunos, mps):
    """Exportação XLS da estatística.

    `tab=total_curso` gera o total por curso (monta o crosstab UMA vez); as demais
    abas delegam à task de listagem. Chamada antes de montar gráficos/tabelas de
    tela, que não são usados no export.
    """
    if request.GET.get('tab') != 'total_curso':
        return tasks.exportar_listagem_alunos_xls(
            request, mps, form.cleaned_data['exibicao'], form.fields['exibicao'].choices, is_matricula_periodo=True
        )
    rows = [['Código', 'Descrição', 'Campus', 'Modalidade', 'Quantidade']]
    for registro in TabelaResumoMPCurso(alunos).registros:
        rows.append(list(registro.values()))
    return XlsResponse(rows)


@permission_required('ponto.pode_ver_frequencia_propria')
@rtr()
def estatistica(request):
    title = 'Quantitativo de Alunos'
    form = EstatisticaForm(request.GET or None, request=request)
    collapse_filters = ''

    if not form.is_valid():
        return locals()

    collapse_filters = 'collapsed'
    uos, anos, periodos, uo_selecionada, ano_selecionado, periodo_selecionado, grafico_ano, alunos, mps = form.processar()
    agrupar = form.cleaned_data.get('agrupar')

    # Exportação XLS: short-circuit antes de montar gráficos/distribuições/tabelas
    # de tela (descartados no export) — evita trabalho e queries desnecessárias.
    if 'xls' in request.GET:
        return _exportar_estatistica_xls(request, form, alunos, mps)

    tabela = TabelaResumoAluno(alunos)
    series = []
    for i, modalidade in enumerate(tabela.colunas):
        series.append([modalidade, tabela.registros[len(tabela.registros) - 1][i]])
    series = series[1:-1]

    id_grafico = 'id_grafico_x'
    grafico = PieChart(id_grafico, title='Total de Alunos por Modalidade', data=series)
    grafico.id = id_grafico

    # Distribuições (raça/cor, faixa etária, renda per capita) dos caracterizados.
    distribuicoes = _distribuicoes_caracterizacao(alunos)
    grafico_raca = distribuicoes.get('grafico_raca')
    grafico_idade = distribuicoes.get('grafico_idade')
    grafico_renda = distribuicoes.get('grafico_renda')

    if uo_selecionada:
        tabela_por_curso = TabelaResumoMPCurso(alunos)
        if uo_selecionada.pk == 14:
            tabela_aluno_polo_nivel_ensino = TabelaMPPoloNivelEnsino(alunos)
            tabela_aluno_curso_polo = TabelaAlunoCursoCampusPolo(alunos)

    alunos = alunos[0:25]
    mps = mps[0:25]
    return locals()


@permission_required('edu.gerar_relatorio')
@rtr()
def variaveis(request, indicador, ano, uo, modalidades, curso):
    title = f'{IndicadoresForm.INDICADORES[indicador][0]} - {ano}'
    ano = int(ano)
    uos = uo.split('_')
    modalidades = modalidades.split('_')
    curso = int(curso)
    deficiencias = request.GET.get('deficiencias', '')
    outras_nees = request.GET.get('outras_nees', '')
    variaveis = IndicadoresForm.processar_variaveis(
        ano,
        ano,
        modalidades,
        uos,
        curso_id=curso,
        deficiencias=deficiencias.split('_') if deficiencias else [],
        outras_nees=outras_nees.split('_') if outras_nees else [],
    )
    taxa_conclusao = float(variaveis['CONCLUIDOS'][ano].count()) / float(variaveis['ATENDIDOS'][ano].count() or 1) * 100
    taxa_ativos_regulares = float(variaveis['CONTINUADOS_REGULARES'][ano].count()) / float(variaveis['ATENDIDOS'][ano].count() or 1) * 100
    if 'variavel' in request.GET:
        alunos = Aluno.objects.filter(id__in=variaveis[request.GET.get('variavel')][ano])[0:100]
    return locals()


@login_required()
@rtr()
def indicadores(request):
    if (
        not request.user.has_perm('edu.efetuar_matricula')
        and not request.user.has_perm('edu.gerar_relatorio')
        and not request.user.has_perm('edu.view_aluno')
    ):
        return httprr('/', 'Você não tem permissão para acessar essa página', 'error')

    form = IndicadoresForm(request.GET or None, request=request)
    if form.is_valid():
        if 'xls' in request.GET and ('uo_selecionada' in request.GET or request.user.has_group_cached('Administrador Acadêmico')):
            return tasks.exportar_indicadores_xls(request)
        else:
            return tasks.processar_indicadores(request)

    return locals()


@rtr()
@permission_required('edu.view_dados_caracterizacao_e_academicos')
def exportar_dados_aluno_caracterizacao(request):
    title = 'Exportar Dados de Aluno e Caracterização Social'
    form = ExportarAlunosCaracterizacaoForm(data=request.POST or None)
    if form.is_valid():
        return form.processar()
    return locals()


@permission_required('edu.view_turma')
def exportar_xls_aluno(request):
    escopo = request.GET.get('escopo', None)

    turma_pk = request.GET.get('turma', None)
    turma_manager = request.user.has_group_cached('Diretor Acadêmico') and Turma.objects or Turma.locals
    turma_obj = get_object_or_404(turma_manager, pk=turma_pk)

    xls = request.GET.get('xls', None)

    rows = []
    name_xls = 'report_xls'

    if escopo == 'turma':
        if xls in ['alunos_na_turma', 'alunos_apenas_em_diarios', 'alunos_todos']:
            rows.append(['#', 'Código da Turma', 'Aluno', 'Matrícula', 'Situação no Período'])
            name_xls = f'{turma_obj.codigo}_{xls}'

        matriculas_periodo = MatriculaPeriodo.objects.none()

        if xls == 'alunos_na_turma':
            matriculas_periodo = turma_obj.get_alunos_matriculados()

        elif xls == 'alunos_apenas_em_diarios':
            matriculas_periodo = turma_obj.get_alunos_matriculados_diarios()

        elif xls == 'alunos_todos':
            matriculas_periodo = turma_obj.get_alunos_matriculados() | MatriculaPeriodo.objects.filter(
                pk__in=[matricula.id for matricula in turma_obj.get_alunos_matriculados_diarios()]
            )

        count = 0
        for matricula_periodo in matriculas_periodo:
            count += 1
            rows.append([count, turma_obj.codigo, matricula_periodo.aluno.get_nome(), matricula_periodo.aluno.matricula, matricula_periodo.situacao])

    if not rows:
        rows.append(['?'])

    return XlsResponse(rows, name=name_xls)


@permission_required('edu.efetuar_matricula')
@rtr()
def relatorio_dados_responsavel_incompletos(request):
    title = 'Relatório de Alunos Menores de Idade sem CPF do Responsável'
    hoje = datetime.datetime.now()
    nascimento_data = hoje - relativedelta(years=18)
    diretorias = Diretoria.locals.all()
    alunos = Aluno.locals.filter(
        curso_campus__diretoria__in=diretorias,
        situacao__ativo=True,
        cpf_responsavel__isnull=True,
        pessoa_fisica__nascimento_data__gte=nascimento_data,
    )
    form = FiltroAlunosForm(data=request.GET or None)
    if form.is_valid():
        alunos = form.filtrar(alunos)
    if 'export' in request.GET:
        rows = [['MATRÍCULA', 'NOME', 'CURSO', 'TURMA', 'DIRETORIA']]
        for aluno in alunos:
            ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
            row = [
                aluno.matricula,
                aluno.get_nome(),
                str(aluno.curso_campus),
                ultima_matricula_periodo and str(ultima_matricula_periodo.turma) or '-',
                str(aluno.curso_campus.diretoria),
            ]
            rows.append(row)
        return XlsResponse(rows)
    return locals()


@rtr()
@login_required()
@permission_required('edu.report_dependentes_reprovados')
def relatorio_dependentes(request):
    title = 'Listagem de Dependentes'
    form = RelatorioDependenteForm(data=request.GET or None)
    exibir_botao_executar = HistoricoRelatorio.objects.filter(user=request.user, tipo=HistoricoRelatorio.TIPO_PROFESSOR).exists()
    if form.is_valid():
        query_string = request.META.get('QUERY_STRING', '').encode('utf-8').hex()
        matriculas_diarios, filtros = form.processar()
        matricula_diario_list = request.POST.getlist('select_matricula_diario')
        matricula_diario_resumida_list = request.POST.getlist('select_matricula_diario_resumida')
        if matricula_diario_list or matricula_diario_resumida_list:
            matriculas_diarios = list(MatriculaDiario.objects.filter(id__in=matricula_diario_list)) + list(
                MatriculaDiarioResumida.objects.filter(id__in=matricula_diario_resumida_list)
            )

        if 'xls' in request.POST:
            return tasks.exportar_relatorio_dependencia_xls(matriculas_diarios)
    return locals()


@rtr()
@group_required('Diretor de Avaliação e Regulação do Ensino')
def relatorio_coordenacao_curso(request):
    title = 'Relatório de Coordenação de Cursos'
    form = RelatorioCoordenacaoCursoForm(data=request.POST or None)
    if form.is_valid():
        cursos = form.processar()
        cursos_id = '_'.join(str(curso.id) for curso in cursos)

    if 'xls' in request.POST:
        return tasks.exportar_relatorio_coordenacao_curso(request, request.POST.get('xls'))
    return locals()


@rtr()
@login_required()
@permission_required(['edu.gerar_relatorio', 'rh.eh_servidor'])
def relatorio_diario(request):
    exibir_botao_executar = HistoricoRelatorio.objects.filter(user=request.user, tipo=HistoricoRelatorio.TIPO_DIARIO).exists()
    title = 'Listagem de Diários'
    form = RelatorioDiarioForm(data=request.GET or None, initial={'etapa': 1})
    if form.is_valid():
        query_string = request.META.get('QUERY_STRING', '').encode('utf-8').hex()
        diarios = form.processar()
        filtros = diarios.filtros
        agrupamento = form.cleaned_data['agrupamento']
        if agrupamento == 'Componente':
            diarios = diarios.order_by('componente_curricular__componente__sigla')
        elif agrupamento == 'Campus':
            diarios = diarios.order_by('turma__curso_campus__diretoria__setor__uo__nome')
        else:
            diarios = diarios.order_by('turma__curso_campus')

        impede_exportar = diarios.count() > 5000
        campos_exibicao = form.cleaned_data['exibicao']

        if 'alunos_pendentes' in request.GET:
            return tasks.relatorio_diario_alunos_pendentes(request, diarios, filtros, exibir_botao_executar, agrupamento, campos_exibicao)

        if 'imprimir' in request.GET and request.user.has_perm('edu.emitir_boletins'):
            return tasks.relatorio_diario_pdf(request, diarios)
        if 'xls' in request.GET:
            return tasks.exportar_relatorio_diario_xls(diarios, campos_exibicao, form.EXIBICAO_CHOICES)

    return locals()


@rtr()
@permission_required('edu.gerar_relatorio')
def relatorio_faltas(request):
    title = 'Relatório de Faltas'
    form = RelatorioFaltasForm(request.GET or None, request=request)
    if form.is_valid():
        if 'exportar' in request.GET:
            return tasks.relatorio_faltas_exportar(request)
        if 'notificar' in request.GET:
            return tasks.relatorio_faltas_notificar(request)
        if not running_tests():
            return tasks.relatorio_faltas(request)
        else:
            ctx = tasks.get_matriculas_periodos_relatorio_faltas(request, None)
            ctx['form'] = form
            return ctx
    return locals()


def _anos_periodos_abertos(request, situacoes):
    """Últimos 15 anos com período em aberto e o ano em foco no relatório."""
    anos = (
        Ano.objects.filter(matriculaperiodo__ano_letivo__ano__lt=datetime.datetime.now().year, matriculaperiodo__situacao__id__in=situacoes)
        .order_by('-matriculaperiodo__ano_letivo__ano')
        .values_list('ano', flat=True)
        .distinct()[0:15]
    )
    if 'ano_selecionado' in request.GET:
        return anos, int(request.GET['ano_selecionado'])
    # `anos` é vazio quando não há matrícula-período em ano anterior ao corrente; o
    # relatório então sai vazio (o laço sobre `anos` não roda) em vez de estourar.
    return anos, (anos[0] if anos else None)


def _uos_periodos_abertos(request, qs, is_administador):
    """Câmpus visíveis ao usuário e o selecionado; ``(None, None)`` quando não há nenhum."""
    if is_administador:
        ids_uos = (
            qs.filter(aluno__curso_campus__diretoria__setor__uo__isnull=False)
            .order_by('aluno__curso_campus__diretoria__setor__uo')
            .values_list('aluno__curso_campus__diretoria__setor__uo', flat=True)
            .distinct()
        )
    else:
        ids_uos = Diretoria.locals.all().values_list('setor__uo', flat=True).order_by('setor__uo').distinct()
    if not ids_uos:
        return None, None
    uos = UnidadeOrganizacional.objects.suap().filter(id__in=ids_uos)
    uo_selecionada = None
    if request.GET.get('uo_selecionada'):
        uo_selecionada = UnidadeOrganizacional.objects.suap().get(pk=request.GET['uo_selecionada'])
    if not is_administador and not uo_selecionada:
        uo_selecionada = uos and uos[0] or None
    return uos, uo_selecionada


def _series_periodos_abertos(qs, anos, ano_selecionado, uo_selecionada, is_administador):
    """Uma série por ano para o gráfico e os ids de aluno do ano em foco."""
    series = []
    ids = []
    for ano in anos:
        serie = [ano]
        if is_administador:
            serie.append(len(set(qs.filter(ano_letivo__ano=ano).values_list('aluno__id', flat=True))))
        qs_ano = qs.filter(ano_letivo__ano=ano)
        if uo_selecionada:
            qs_ano = qs_ano.filter(aluno__curso_campus__diretoria__setor__uo=uo_selecionada)
        ids_ano = qs_ano.values_list('aluno__id', flat=True)
        if ano == ano_selecionado:
            ids = ids_ano
        serie.append(len(set(ids_ano)))
        series.append(serie)
    return series, ids


def _xls_periodos_abertos(alunos, ano_selecionado):
    """Planilha do relatório, uma linha por aluno."""
    rows = [['#', 'Ano', 'Matrícula', 'Aluno', 'CursoSituação no Curso', 'Diretoria', 'Câmpus']]
    for count, aluno in enumerate(alunos, start=1):
        rows.append(
            [
                count,
                format_(ano_selecionado),
                format_(aluno.matricula),
                format_(aluno.get_nome_social_composto()),
                format_(aluno.curso_campus),
                format_(aluno.curso_campus.diretoria),
                format_(aluno.curso_campus.diretoria.setor.uo),
                format_(aluno.situacao),
            ]
        )
    return XlsResponse(rows)


@permission_required('edu.gerar_relatorio')
@rtr()
def relatorio_periodos_abertos(request):
    title = 'Relatório de Alunos com Períodos Não-Fechados'

    form = RelatorioPeriodosAbertosForm(request.GET or None, request=request)

    is_administador = request.user.has_group_cached('Administrador Acadêmico')

    situacoes = [2]
    anos, ano_selecionado = _anos_periodos_abertos(request, situacoes)

    qs = MatriculaPeriodo.objects.filter(situacao__id__in=situacoes)

    if form.is_valid():
        if form.cleaned_data['modalidades']:
            qs = qs.filter(aluno__curso_campus__modalidade__in=form.cleaned_data['modalidades'])
        if form.cleaned_data['cursos']:
            qs = qs.filter(aluno__curso_campus__in=form.cleaned_data['cursos'])

    uos, uo_selecionada = _uos_periodos_abertos(request, qs, is_administador)
    if uos is None:
        return httprr('/', 'Você não tem permissão para realizar isso.', 'error')

    ano_corrente = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or datetime.date.today().year)
    periodo_corrente = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)

    if periodo_corrente == 1:
        qs = qs.exclude(ano_letivo__ano=ano_corrente)
    else:
        qs = qs.exclude(ano_letivo__ano=ano_corrente, periodo_letivo=2).exclude(
            ano_letivo__ano=ano_corrente, aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL
        )

    series, ids = _series_periodos_abertos(qs, anos, ano_selecionado, uo_selecionada, is_administador)
    alunos = Aluno.objects.filter(id__in=ids).order_by('curso_campus')

    disabled_groups = []
    if not is_administador:
        groups = [uo_selecionada.nome]
    elif uo_selecionada:
        groups = ['Instituto', uo_selecionada.nome]
        disabled_groups = ['Instituto']
    else:
        groups = ['Instituto']

    id_grafico = '1'
    grafico = GroupedColumnChart(id_grafico, title='Alunos com Período Letivo Aberto', data=series, groups=groups, disabled_groups=disabled_groups)

    grafico.id = id_grafico

    if 'xls' in request.GET:
        return _xls_periodos_abertos(alunos, ano_selecionado)

    return locals()


@rtr()
@permission_required('edu.add_matriz')
def relatorio_migracao(request, acao=None, curso_campus_id=None):
    ano = int(Configuracao.get_valor_por_chave('edu', 'ano_letivo_atual') or datetime.date.today().year)
    periodo_letivo = int(Configuracao.get_valor_por_chave('edu', 'periodo_letivo_atual') or 1)
    ano_letivo = Ano.objects.get(ano=ano)

    qs = MatriculaPeriodo.objects.filter(
        aluno__situacao__in=[
            SituacaoMatricula.MATRICULADO,
            SituacaoMatricula.TRANCADO,
            SituacaoMatricula.INTERCAMBIO,
            SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
        ]
    )
    qs = qs.filter(aluno__codigo_academico__isnull=False)
    qs = qs.filter(aluno__matriz__estrutura__isnull=True) | qs.filter(aluno__matriz__estrutura__proitec=False)

    if acao in ['migrados', 'pendentes', 'pendencias', 'pendencias_excel']:
        qs = qs.filter(aluno__curso_campus=curso_campus_id)
        form = RelatorioMigracaoForm(data=request.GET)
        if form.is_valid():
            qs = form.filtrar(qs)
        form = None

    if acao == 'migrados':
        title = 'Alunos Migrados'
        qs_matriculas_periodo = qs.filter(aluno__curso_campus=curso_campus_id, aluno__matriz__isnull=False)
        return locals()
    elif acao == 'pendentes':
        title = 'Alunos Não-Migrados'
        qs_matriculas_periodo = qs.filter(aluno__curso_campus=curso_campus_id, aluno__matriz__isnull=True)
        return locals()
    elif acao == 'pendencias' or acao == 'pendencias_excel':
        title = 'Pendências do Q-Acadêmico'
        curso_campus = CursoCampus.objects.filter(pk=curso_campus_id)
        qs = qs.filter(aluno__curso_campus=curso_campus_id, aluno__matriz__isnull=True)
        dao = DAO()
        matriculas = []
        matriculas_aptos = []
        for matricula in qs.values_list('aluno__matricula', flat=True):
            matriculas_aptos.append(matricula)
            matriculas.append(matricula)

        ano_letivo = Ano.objects.get(pk=request.GET['ano_letivo'])
        periodo_letivo = int(request.GET['periodo_letivo'])
        ignorar_ultimo_periodo = 'ignorar_ultimo_periodo' in request.GET
        erros = dao.importar_historico_resumo(
            matriculas, 199, ano_letivo, periodo_letivo, validacao=True, ignorar_ultimo_periodo=ignorar_ultimo_periodo
        )

        for aluno, _mensagens in erros:
            matriculas_aptos.remove(aluno.matricula)

        alunos_aptos = Aluno.objects.filter(matriz__isnull=True, matricula__in=matriculas_aptos)

        if acao == 'pendencias_excel':
            rows = [['#', 'Matrícula', 'Nome', 'Pendência']]
            count = 0
            for aluno, mensagens in erros:
                for mensagem in mensagens:
                    count += 1
                    row = [count, aluno.matricula, aluno.get_nome_social_composto(), mensagem.replace('<i>', '').replace('</i>', '')]
                    rows.append(row)
            rows.append(['', '', '', ''])
            for aluno in alunos_aptos:
                count += 1
                row = [count, aluno.matricula, aluno.get_nome_social_composto(), 'NENHUMA']
                rows.append(row)
            return XlsResponse(rows, name=f'{aluno.curso_campus.diretoria.setor.uo.sigla}-{aluno.curso_campus.codigo}')

        return locals()

    title = 'Relatório de Migração'
    form = RelatorioMigracaoForm(data=request.GET or None, initial={'ano_letivo': ano_letivo.pk, 'periodo_letivo': periodo_letivo})
    if form.is_valid():
        qs = form.filtrar(qs)
        resumo = []
        for curso_campus_id, codigo_curso_campus, descricao_curso_campus in (
            qs.order_by('aluno__curso_campus')
            .values_list('aluno__curso_campus__id', 'aluno__curso_campus__codigo', 'aluno__curso_campus__descricao')
            .distinct()
        ):
            qs_curso_campus = qs.filter(aluno__curso_campus=curso_campus_id)
            total = qs_curso_campus.count()
            migrados = qs_curso_campus.filter(aluno__matriz__isnull=False).count()
            pendentes = total - migrados
            percentual = total and int(migrados * 100 / total) or 0
            item = {
                'id': curso_campus_id,
                'codigo': codigo_curso_campus,
                'descricao': descricao_curso_campus,
                'total': total,
                'migrados': migrados,
                'pendentes': pendentes,
                'percentual': percentual,
            }
            resumo.append(item)
    return locals()
