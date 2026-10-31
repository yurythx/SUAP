import collections
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from comum.utils import get_setor
from djtools.utils import XlsResponse, eval_attr, httprr, permission_required, rtr
from edu.utils import TabelaCampusPorModalidade
from gestao import tasks
from gestao.forms import CompararaVariavelForm, PeriodoReferenciaForm
from gestao.models import INDICADORES_DESATIVADOS, VARIAVEIS_GRUPOS, Indicador, PeriodoReferencia, Variavel
from gestao.util import VariavelDiff
from rh.models import UnidadeOrganizacional


@rtr()
@permission_required('gestao.view_periodoreferencia')
def periodo_referencia(request):
    title = 'Período de Referência'
    ano_referencia = PeriodoReferencia.get_ano_referencia()
    data_limite = PeriodoReferencia.get_data_limite()
    data_base = PeriodoReferencia.get_data_base()
    return locals()


@rtr()
@permission_required('gestao.pode_editar_meu_periodo_referencia')
def definir_periodo_referencia(request):
    title = 'Definir Período de Referência'
    if request.method == 'POST':
        form = PeriodoReferenciaForm(data=request.POST, instance=PeriodoReferencia.get_referencia(request.user))
        if form.is_valid():
            periodo_referencia = form.save(False)
            periodo_referencia.user = request.user
            periodo_referencia.save()
            return httprr('..', 'Período de referência alterado com sucesso')
    else:
        form = PeriodoReferenciaForm(instance=PeriodoReferencia.get_referencia(request.user))
    return locals()


@rtr()
@permission_required('gestao.pode_editar_periodo_referencia_global')
def definir_periodo_referencia_global(request):
    title = 'Definir Período de Referência Global'
    if request.method == 'POST':
        form = PeriodoReferenciaForm(data=request.POST, instance=PeriodoReferencia.get_referencia(request.user))
        if form.is_valid():
            periodo_referencia = form.save(False)
            PeriodoReferencia.objects.update(
                ano=periodo_referencia.ano, data_base=periodo_referencia.data_base, data_limite=periodo_referencia.data_limite
            )
            return httprr('..', 'Período de referência global alterado com sucesso')
    else:
        form = PeriodoReferenciaForm(instance=PeriodoReferencia.get_referencia(request.user))
    return locals()


@rtr()
@login_required()
def recuperar_valor(request):
    pk = int(request.GET.get('pk', 0))
    uo_pk = int(request.GET.get('uo_pk', 0) or 0)
    data = {'valor': Variavel.recuperar_valor(pk, uo_pk)}
    return JsonResponse(data)


@rtr()
@permission_required('gestao.pode_exibir_variaveis')
def exibir_variaveis(request, tipo, vinculo_aluno_convenio='AlunosTodos'):
    setor_usuario_logado = get_setor(request.user)

    title = 'Variáveis'
    periodo = PeriodoReferencia.get_referencia(request.user)
    ano_referencia = periodo.ano
    data_base = periodo.data_base
    data_limite = periodo.data_limite
    periodo_referencia = f'{ano_referencia}_{data_base}_{data_limite}'

    variaveis = Variavel.objects.all().order_by('sigla')
    tipo_titulo = ''

    if tipo != 'Todas':
        for vg in VARIAVEIS_GRUPOS:
            if vg.get('grupo') == tipo:
                subgrupo = vg.get('subgrupo')
                if not subgrupo or subgrupo == vinculo_aluno_convenio:
                    variaveis = variaveis.filter(sigla__in=vg.get('variaveis'))
                    tipo_titulo = vg.get('titulo')
                    break

        title = f'Variáveis de {tipo_titulo}'

    if 'por_campus' in request.GET or 'por_campus_xls' in request.GET or 'pelo_meu_campus' in request.GET or 'pelo_meu_campus_xls' in request.GET:
        if 'por_campus' in request.GET or 'por_campus_xls' in request.GET:
            uos = UnidadeOrganizacional.objects.suap().all()
        elif 'pelo_meu_campus' in request.GET or 'pelo_meu_campus_xls' in request.GET:
            uos = [setor_usuario_logado.uo]

        linhas = []

        for variavel in variaveis:
            linha = [variavel]
            for uo in uos:
                if 'por_campus_xls' in request.GET or 'pelo_meu_campus_xls' in request.GET:
                    linha.append(variavel.get_valor_formatado(uo))
                else:
                    valor = Variavel.recuperar_valor(variavel.pk, uo.pk, False)
                    linha.append({'valor': valor, 'uo': uo})
            linhas.append(linha)

        if 'por_campus_xls' in request.GET or 'pelo_meu_campus_xls' in request.GET:
            linha = ['']
            for uo in uos:
                linha.append(uo.sigla)
            linhas.insert(0, linha)
            return XlsResponse(linhas)

    tasks = []
    variaveis_cache = {}
    for variavel in variaveis:
        var_cache = {}
        var_cache['pk'] = variavel.pk
        var_cache['nome'] = variavel.nome
        var_cache['sigla'] = variavel.sigla
        var_cache['descricao'] = variavel.descricao
        var_cache['fonte'] = variavel.fonte
        var_cache['valor'] = Variavel.recuperar_valor(variavel.pk, 0, False)
        var_cache['has_detalhamento_variavel'] = variavel.has_detalhamento_variavel()
        variaveis_cache[var_cache['sigla']] = var_cache

    return locals()


@rtr()
@permission_required('gestao.pode_exibir_indicadores')
def exibir_indicadores(request, orgao_regulamentador='TCU'):
    title = 'Indicadores'
    ano_referencia = PeriodoReferencia.get_ano_referencia()
    data_base = PeriodoReferencia.get_data_base()
    data_limite = PeriodoReferencia.get_data_limite()
    setor_usuario_logado = get_setor(request.user)

    if orgao_regulamentador == 'TCU':
        indicadores = Indicador.objects.filter(orgao_regulamentador=Indicador.ORGAO_REGULAMENTADOR_TCU)
    elif orgao_regulamentador == 'MEC':
        indicadores = Indicador.objects.filter(orgao_regulamentador=Indicador.ORGAO_REGULAMENTADOR_MEC)
    else:
        indicadores = Indicador.objects.filter(orgao_regulamentador=Indicador.ORGAO_REGULAMENTADOR_OUTROS)

    # Indicadores desativados.
    indicadores = indicadores.all().exclude(sigla__in=INDICADORES_DESATIVADOS)

    if 'processar' in request.GET:
        return tasks.processar_indicadores(indicadores, request.user)

    if 'por_campus' in request.GET or 'por_campus_xls' in request.GET or 'pelo_meu_campus' in request.GET or 'pelo_meu_campus_xls' in request.GET:
        if 'por_campus' in request.GET or 'por_campus_xls' in request.GET:
            uos = UnidadeOrganizacional.objects.suap().all()
        else:
            uos = [setor_usuario_logado.uo]
        linhas = []

        for indicador in indicadores:
            linha = [indicador.sigla]
            for uo in uos:
                linha.append(indicador.recuperar_valor_formatado(uo=uo))
            linhas.append(linha)

        if 'por_campus_xls' in request.GET or 'pelo_meu_campus_xls' in request.GET:
            linha = ['']
            for uo in uos:
                linha.append(uo.sigla)
            linhas.insert(0, linha)
            return XlsResponse(linhas)

    return locals()


@rtr()
@permission_required('gestao.pode_detalhar_variavel')
def detalhar_variavel(request, sigla, uo_ativa):
    variavel = get_object_or_404(Variavel, sigla=sigla)
    title = f'Detalhar Variável: {variavel.nome} ({variavel.sigla})'
    ano_referencia = PeriodoReferencia.get_ano_referencia()
    data_base = PeriodoReferencia.get_data_base()
    data_limite = PeriodoReferencia.get_data_limite()
    uos = [None]
    uos.extend(list(UnidadeOrganizacional.objects.suap().all()))
    uo = None

    q = ''
    if 'q' in request.GET:
        q = request.GET['q']

    if uo_ativa != 'Todas':
        uo = UnidadeOrganizacional.objects.suap().get(pk=uo_ativa)

    campus = uo.sigla if uo else 'Todas'

    # gerar dados em csv
    url_base = request.path + '?' + request.GET.urlencode()
    url_csv = url_base + '&format=csv'

    valor = variavel.get_valor(uo)

    qs_pessoas_descricao = ''
    if variavel.sigla == 'DEE':
        qs_pessoas_descricao = 'Docentes'
        qs_pessoas = variavel.get_querysets(uo)[0].order_by('nome')
        if q:
            qs_pessoas = qs_pessoas.filter(servidor__matricula=q)

    elif variavel.sigla == 'TAEE':
        qs_pessoas_descricao = 'Técnicos Administrativos'
        qs_pessoas = variavel.get_querysets(uo)[0].order_by('nome')
        if q:
            qs_pessoas = qs_pessoas.filter(servidor__matricula=q)

    elif variavel.sigla == 'DISCEE':
        qs_pessoas_descricao = 'Discentes'
        qs_pessoas = variavel.get_querysets(uo)[0].order_by('nome')
        if q:
            qs_pessoas = qs_pessoas.filter(aluno_set__matricula=q)

    elif variavel.sigla == 'AEQ':
        detalhamento_variavel_AEQ = variavel.get_valor_com_detalhamento_AEQ(uo=uo)[1]

    elif variavel.sigla == 'AEQ_PROEJA':
        detalhamento_variavel_AEQ = variavel.get_valor_com_detalhamento_AEQ_PROEJA(uo=uo)[1]

    elif variavel.sigla == 'AEQ_TECNICO':
        detalhamento_variavel_AEQ = variavel.get_valor_com_detalhamento_AEQ_TECNICO(uo=uo)[1]

    elif variavel.sigla == 'AEQ_DOCENTE':
        detalhamento_variavel_AEQ = variavel.get_valor_com_detalhamento_AEQ_DOCENTE(uo=uo)[1]

    elif variavel.sigla == 'AEQ_FENC':
        detalhamento_variavel_AEQ_FENC = variavel.get_valor_com_detalhamento_AEQ_FENC(uo=uo)[1]

    elif variavel.sigla == 'IAEQ':
        detalhamento_variavel_IAEQ = variavel.get_valor_com_detalhamento_IAEQ(uo=uo)[1]

    elif variavel.sigla in ['AC', 'AC_EX', 'AC_OR'] or variavel.sigla in ['AI', 'AI_EX', 'AI_OR']:
        qs_alunos = variavel.get_querysets(uo)[0].order_by('pessoa_fisica__nome')
        if q:
            qs_alunos = qs_alunos.filter(matricula=q)
        tabela = TabelaCampusPorModalidade(qs_matriculas1=None, qs_alunos=qs_alunos, uo=uo)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            return tasks.detalhar_variavel_ac_xls(qs_alunos)

    elif variavel.sigla in ['AIC', 'AIC_EX', 'AIC_OR']:
        qs_alunos = variavel.get_querysets(uo)[0]
        for qs in variavel.get_querysets(uo)[1:]:
            qs_alunos = qs_alunos | qs
        qs_alunos = qs_alunos.order_by('curso_campus__id')
        if q:
            qs_alunos = qs_alunos.filter(aluno__matricula=q)
        tabela = TabelaCampusPorModalidade(qs_matriculas1=None, qs_alunos=qs_alunos, uo=uo)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            return tasks.detalhar_variavel_ac_xls(qs_alunos)

    elif variavel.sigla in ['AR', 'AR_EX', 'AR_OR', 'AJ', 'AJ_EX', 'AJ_OR', 'AE', 'AE_EX', 'AE_OR', 'AANF']:
        qs_alunos = variavel.get_querysets(uo)[0].order_by('pessoa_fisica__nome')
        if q:
            qs_alunos = qs_alunos.filter(matricula=q)
        tabela = TabelaCampusPorModalidade(qs_matriculas1=None, qs_alunos=qs_alunos, uo=uo)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            return tasks.detalhar_variavel_ac_xls(qs_alunos)

    elif variavel.sigla in ['CO', 'COPRES', 'COEAD', 'COEAD_EX', 'COEAD_OR']:
        qss = variavel.get_querysets(uo)
        qs_curso = qss[0].order_by('descricao')
        if q:
            qs_curso = qs_curso.filter(descricao__unaccent__icontains=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = get_exportacao(
                qs_curso, ['descricao', 'ano_letivo', 'data_inicio', 'data_fim'], ['Descrição', 'Ano Letivo', 'Data Início', 'Data Fim']
            )
            return XlsResponse(rows)

    elif variavel.sigla in [
        'AM',
        'AM_EX',
        'AM_OR',
        'AM_NR',
        'AICOR_NR',
        'AMPRES',
        'AMPRES_EX',
        'AMPRES_OR',
        'AMPRESF',
        'AMPRESF_EX',
        'AMPRESF_OR',
        'AMEAD',
        'AMEAD_EX',
        'AMEAD_OR',
        'AMF',
        'AMNF',
        'AMTEC',
        'AMTEC_EX',
        'AMTEC_OR',
        'AMTEC_EAD',
        'AMTEC_EAD_EX',
        'AMTEC_EAD_OR',
        'AMTEC_PRES',
        'AMTEC_PRES_EX',
        'AMTEC_PRES_OR',
        'AMGRAD',
        'AMGRAD_EX',
        'AMGRAD_OR',
        'AMGRAD_EAD',
        'AMGRAD_EAD_EX',
        'AMGRAD_EAD_OR',
        'AMGRAD_PRES',
        'AMGRAD_PRES_EX',
        'AMGRAD_PRES_OR',
        'AMLIC',
        'AMLIC_EX',
        'AMLIC_OR',
        'AMMEST',
        'AMMEST_EX',
        'AMMEST_OR',
        'AMEJA',
        'AMEJA_EX',
        'AMEJA_OR',
        'AICOR',
        'AICOR_EX',
        'AICOR_OR',
    ]:
        qss = variavel.get_querysets(uo)
        modelo = qss[0].model
        qs_matriculas = qss[0]
        tem_aluno = 'aluno' in [f.name for f in modelo._meta.get_fields()]
        if tem_aluno:
            qs_matriculas = qs_matriculas.order_by('aluno__pessoa_fisica__nome')
            if q:
                qs_matriculas = qs_matriculas.filter(aluno__matricula=q).select_related(
                    'aluno__pessoa_fisica', 'aluno__curso_campus', 'aluno__curso_campus__diretoria'
                )

        tabela = TabelaCampusPorModalidade(qs_matriculas1=qs_matriculas, qs_alunos=None, uo=uo)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            return tasks.detalhar_variavel_am_xls(qs_matriculas)

    elif variavel.sigla in ['A', 'G', 'E', 'M', 'D', 'DO', 'DOAP', 'DOAP_20', 'DOAP_40', 'DOAP_DDE', 'DOST', 'DOC']:
        qs_servidores = variavel.get_querysets(uo)[0].order_by('pessoa_fisica__nome')
        if q:
            qs_servidores = qs_servidores.filter(matricula=q)

    elif variavel.sigla in ['DDESF', 'DDECF', 'D40SF', 'D40CF', 'D20SF', 'D20CF', 'DFG', 'DCD1', 'DCD2', 'DCD3', 'DCD4']:
        qs_servidores = variavel.get_querysets(uo)[0].order_by('pessoa_fisica__nome')
        if q:
            qs_servidores = qs_servidores.filter(matricula=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = get_exportacao(qs_servidores, ['matricula', 'nome', 'cargo_emprego'], ['Matrícula', 'Nome', 'Cargo'])
            return XlsResponse(rows)

    # REMOVER a variável DTI após homologação, já que o indicador foi criado.
    elif variavel.sigla == 'DTI':
        qs_de_c40h, qs_c20h, qs_fg, qs_cd4, qs_cd123 = variavel.get_querysets(uo)
        qs_servidores = (qs_de_c40h | qs_c20h | qs_fg | qs_cd4).order_by('nome')
        if q:
            qs_servidores = qs_servidores.filter(matricula=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = get_exportacao(qs_servidores, ['matricula', 'nome', 'cargo_emprego'], ['Matrícula', 'Nome', 'Cargo'])
            return XlsResponse(rows)

    elif variavel.sigla == 'GPE':
        # para cada coluna um conjunto de propriedades referentes ao estilo ou ao tipo de dado
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '100px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        tabelas = []
        registros = []
        #         for lin in sorted(variavel.get_qs_despesas_pessoal(list=True, uo=uo), key=lambda despesa: despesa[0]):
        for lin in sorted(variavel.get_qs_despesas_pessoal_nes(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros.append(linha)

        # precatorios = []
        #         for lin in sorted(variavel.get_qs_despesas_precatorios_ncs(list=True, uo=uo), key=lambda despesa: despesa[0]):
        #             linha = []
        #             for c, col in enumerate(lin):
        #                 coluna = estilos[c].copy()
        #                 coluna['info'] = col
        #                 linha.append(coluna)
        #             precatorios.append(linha)

        tabelas.append({'titulo': 'Folha', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros})
    # tabelas.append({'titulo':'Precatorios', 'colunas':['Despesa', 'Descrição', 'Valor', 'UG'], 'dados':precatorios})

    elif variavel.sigla == 'GPA':
        # para cada coluna um conjunto de propriedades referentes ao estilo
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '100px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        tabelas = []
        registros = []
        for lin in sorted(variavel.get_qs_despesas_pessoalativo(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros.append(linha)

        tabelas.append({'titulo': '', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros})

    elif variavel.sigla == 'GCO':
        tabelas = []

        # para cada coluna um conjunto de propriedades referentes ao estilo
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '100px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        registros = []
        for lin in sorted(variavel.get_qs_despesas_custeios_nes(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros.append(linha)

        registros_folha = []
        for lin in sorted(variavel.get_qs_despesas_beneficios_folha(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros_folha.append(linha)

        registros_ativos = []
        for lin in sorted(variavel.get_qs_despesas_pessoalativo(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros_ativos.append(linha)

        tabelas.append({'titulo': 'Gasto com Pessoal Ativo', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros_ativos})
        tabelas.append({'titulo': 'Beneficios', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros_folha})
        tabelas.append({'titulo': 'Outros Custeios', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros})

    elif variavel.sigla == 'GOC':
        tabelas = []

        # para cada coluna um conjunto de propriedades referentes ao estilo
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '120px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        ncs = []
        for lin in sorted(variavel.get_qs_despesas_custeios_ncs(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            ncs.append(linha)

        nes = []
        for lin in sorted(variavel.get_qs_despesas_custeios_nes(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            nes.append(linha)

        folha = []
        for lin in sorted(variavel.get_qs_despesas_custeios_folha(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            folha.append(linha)

        tabelas.append({'titulo': 'Descentralizacoes', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': ncs})
        tabelas.append({'titulo': 'Notas de Empenho', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': nes})
        tabelas.append({'titulo': 'Folha', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': folha})

    elif variavel.sigla == 'GCA':
        tabelas = []

        # para cada coluna um conjunto de propriedades referentes ao estilo
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '100px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        registros = []
        for lin in sorted(
            (variavel.get_qs_despesas_capital_nes(list=True, uo=uo) + variavel.get_qs_despesas_capital_ncs(list=True, uo=uo)),
            key=lambda despesa: despesa[0],
        ):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros.append(linha)

        tabelas.append({'titulo': '', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros})

    elif variavel.sigla == 'GTO':
        tabelas = []

        # para cada coluna um conjunto de propriedades referentes ao estilo
        estilos = [
            {'align': 'center', 'type': 'text', 'width': '80px'},
            {'align': 'left', 'type': 'text'},
            {'align': 'right', 'type': 'money', 'width': '100px'},
            {'align': 'right', 'type': 'text', 'width': '50px'},
        ]

        registros = []
        for lin in sorted(
            (variavel.get_qs_despesas_custeios_nes(list=True, uo=uo) + variavel.get_qs_despesas_custeios_ncs(list=True, uo=uo)),
            key=lambda despesa: despesa[0],
        ):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros.append(linha)

        registros_folha = []
        for lin in sorted(variavel.get_qs_despesas_beneficios_folha(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros_folha.append(linha)

        registros_ativos = []
        for lin in sorted(variavel.get_qs_despesas_pessoalativo(list=True, uo=uo), key=lambda despesa: despesa[0]):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros_ativos.append(linha)

        registros_capital = []
        for lin in sorted(
            (variavel.get_qs_despesas_capital_nes(list=True, uo=uo) + variavel.get_qs_despesas_capital_ncs(list=True, uo=uo)),
            key=lambda despesa: despesa[0],
        ):
            linha = []
            for c, col in enumerate(lin):
                coluna = estilos[c].copy()
                coluna['info'] = col
                linha.append(coluna)
            registros_capital.append(linha)

        tabelas.append({'titulo': 'Gasto com Pessoal Ativo', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros_ativos})
        tabelas.append({'titulo': 'Beneficios', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros_folha})
        tabelas.append({'titulo': 'Gastos com Capital', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros_capital})
        tabelas.append({'titulo': 'Outros Custeios', 'colunas': ['Despesa', 'Descrição', 'Valor', 'UG'], 'dados': registros})

    elif sigla == 'RFP':
        total = Decimal(0)
        tabelas = []
        linhas = []
        tabela_faixas = []
        qs_faixa_1 = variavel.get_qs_renda_familiar(0, 0.5, uo)
        valor_faixa_1 = qs_faixa_1.count()

        if q:
            qs_faixa_1 = qs_faixa_1.filter(aluno__matricula=q)
        total += valor_faixa_1
        linhas.append([{'info': 'Até 0.5 (exclusivo)'}, {'info': valor_faixa_1, 'align': 'right'}])

        qs_faixa_2 = variavel.get_qs_renda_familiar(0.5, 1.0, uo)
        valor_faixa_2 = qs_faixa_2.count()
        if q:
            qs_faixa_2 = qs_faixa_2.filter(aluno__matricula=q)
        total += valor_faixa_2
        linhas.append([{'info': 'Entre 0.5 e 1 (exclusivo)'}, {'info': valor_faixa_2, 'align': 'right'}])

        qs_faixa_3 = variavel.get_qs_renda_familiar(1.0, 1.5, uo)
        valor_faixa_3 = qs_faixa_3.count()
        if q:
            qs_faixa_3 = qs_faixa_3.filter(aluno__matricula=q)
        total += valor_faixa_3
        linhas.append([{'info': 'Entre 1 e 1.5 (exclusivo)'}, {'info': valor_faixa_3, 'align': 'right'}])

        qs_faixa_4 = variavel.get_qs_renda_familiar(1.5, 2.0, uo)
        valor_faixa_4 = qs_faixa_4.count()
        if q:
            qs_faixa_4 = qs_faixa_4.filter(aluno__matricula=q)
        total += valor_faixa_4
        linhas.append([{'info': 'Entre 1.5 e 2 (exclusivo)'}, {'info': valor_faixa_4, 'align': 'right'}])

        qs_faixa_5 = variavel.get_qs_renda_familiar(2.0, 2.5, uo)
        valor_faixa_5 = qs_faixa_5.count()
        if q:
            qs_faixa_5 = qs_faixa_5.filter(aluno__matricula=q)
        total += valor_faixa_5
        linhas.append([{'info': 'Entre 2 e 2.5 (exclusivo)'}, {'info': valor_faixa_5, 'align': 'right'}])

        qs_faixa_6 = variavel.get_qs_renda_familiar(2.5, 3.0, uo)
        valor_faixa_6 = qs_faixa_6.count()
        if q:
            qs_faixa_6 = qs_faixa_6.filter(aluno__matricula=q)
        total += valor_faixa_6
        linhas.append([{'info': 'Entre 2.5 e 3 (exclusivo)'}, {'info': valor_faixa_6, 'align': 'right'}])

        qs_faixa_7 = variavel.get_qs_renda_familiar(3.0, 10000, uo)
        valor_faixa_7 = qs_faixa_7.count()
        if q:
            qs_faixa_7 = qs_faixa_7.filter(aluno__matricula=q)
        total += valor_faixa_7
        linhas.append([{'info': 'Maior ou igual que 3'}, {'info': valor_faixa_7, 'align': 'right'}])

        if total == Decimal(0):
            total = Decimal(1)  # evitar divisao por zero
        valor_faixa_1 = ('%.2f' % ((valor_faixa_1 * 100) / total)) + ' %'
        linhas[0].append({'info': valor_faixa_1, 'align': 'right'})
        valor_faixa_2 = ('%.2f' % ((valor_faixa_2 * 100) / total)) + ' %'
        linhas[1].append({'info': valor_faixa_2, 'align': 'right'})
        valor_faixa_3 = ('%.2f' % ((valor_faixa_3 * 100) / total)) + ' %'
        linhas[2].append({'info': valor_faixa_3, 'align': 'right'})
        valor_faixa_4 = ('%.2f' % ((valor_faixa_4 * 100) / total)) + ' %'
        linhas[3].append({'info': valor_faixa_4, 'align': 'right'})
        valor_faixa_5 = ('%.2f' % ((valor_faixa_5 * 100) / total)) + ' %'
        linhas[4].append({'info': valor_faixa_5, 'align': 'right'})
        valor_faixa_6 = ('%.2f' % ((valor_faixa_6 * 100) / total)) + ' %'
        linhas[5].append({'info': valor_faixa_6, 'align': 'right'})
        valor_faixa_7 = ('%.2f' % ((valor_faixa_7 * 100) / total)) + ' %'
        linhas[6].append({'info': valor_faixa_7, 'align': 'right'})
        tabelas.append(
            {
                'titulo': 'Renda Familiar Per Capta (Relativo)',
                'colunas': ['Faixa (salários mínimos)', 'Quantidade (alunos)', 'Percentual (%)'],
                'dados': linhas,
            }
        )

    elif variavel.sigla in ('NA', 'NAA'):
        """
        A variável 'artigos_resumo_quantitativo_estrato_dict' conterá um dicionário
        contendo a um resumo da quantidade de artigos por estrato. A rotina abaixo
        foi necessária porque não foi possível fazer via queryset, devido ao fato
        de "estrato" não ser um atributo da entidade em questão, e sim um "annotate".

        Obs: Tentei usar o componente 'defaultdict' do pacote 'collections' mas por
        algum motivo a engine do template do django não reconhece com um dicionário.
        """
        estratos_list = variavel.get_querysets(uo)[0].order_by('estrato').values_list('estrato', flat=True)
        artigos_resumo_quantitativo_estrato_dict = collections.OrderedDict()
        for estrato in estratos_list:
            if estrato is None:
                estrato = 'Sem estrato'
            artigos_resumo_quantitativo_estrato_dict[estrato] = artigos_resumo_quantitativo_estrato_dict.get(estrato, 0) + 1

        qs_artigos = variavel.get_querysets(uo)[0].order_by('curriculo__vinculo__pessoa__nome')
        if q:
            qs_artigos = qs_artigos.filter(curriculo__vinculo__user__username=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = artigos_exportacao(qs_artigos, variavel, ano_referencia, campus, valor)
            return XlsResponse(rows)

    elif variavel.sigla in ('NL', 'NLA'):
        qs_livros = variavel.get_querysets(uo)[0].order_by('curriculo__vinculo__pessoa__nome')
        qs_capitulos = variavel.get_querysets(uo)[1].order_by('curriculo__vinculo__pessoa__nome')

        if q:
            qs_livros = qs_livros.filter(curriculo__vinculo__user__username=q)
            qs_capitulos = qs_capitulos.filter(curriculo__vinculo__user__username=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = livros_capitulos_exportacao(qs_livros, qs_capitulos, variavel, ano_referencia, campus, valor)
            return XlsResponse(rows)

    elif variavel.sigla in ('NT', 'NTA') or variavel.sigla in ('NR', 'NRA'):
        qs_trabalho_evento = variavel.get_querysets(uo)[0].order_by('curriculo__vinculo__pessoa__nome')

        if q:
            qs_trabalho_evento = qs_trabalho_evento.filter(curriculo__vinculo__user__username=q)

        if request.method == 'GET' and request.GET.get('format') == 'csv':
            rows = trabalhos_exportacao(qs_trabalho_evento, variavel, ano_referencia, campus, valor)
            return XlsResponse(rows)

    return locals()


@rtr()
@permission_required('gestao.pode_comparar_variavel')
def comparar_variavel(request, sigla):
    title = f'Comparar Variável [{sigla}]'
    form = CompararaVariavelForm()
    uo = None
    variavel = Variavel.objects.get(sigla=sigla)

    only_diff = bool(request.GET.get('only_diff', False))

    if request.method == 'POST':
        form = CompararaVariavelForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo_siafi = form.cleaned_data['arquivo']
            if variavel.sigla == 'GCO':
                #                 dados_suap = (variavel.get_qs_despesas_custeios_ncs(list=True, uo=uo, for_diff=True) + variavel.get_qs_despesas_custeios_nes(list=True, uo=uo, for_diff=True))
                dados_suap = variavel.get_qs_despesas_custeios_nes(list=True, uo=uo, for_diff=True)
            elif variavel.sigla == 'GCA':
                dados_suap = variavel.get_qs_despesas_capital_nes(list=True, uo=uo, for_diff=True) + variavel.get_qs_despesas_capital_ncs(
                    list=True, uo=uo, for_diff=True
                )
            if variavel.sigla == 'GPE':
                dados_suap = variavel.get_qs_despesas_pessoal_nes(list=True, uo=uo, for_diff=True)
            rows = VariavelDiff.calcular(arquivo_siafi, dados_suap, only_diff=only_diff)
            return XlsResponse(rows, name=f'diferenca_{sigla}')

    return locals()


def inscricoes_exportacao(inscricoes):
    """
    Apresenta a tabela com os dados de inscrições para exportação.
    """
    rows = []
    header = ['', 'Nome', 'CPF', 'Nº de inscrição', 'Oferta de vaga', 'Campus']
    rows.append(header)
    count = 0
    for candidato_vaga in inscricoes:
        count += 1
        row = [
            count,
            candidato_vaga.candidato.nome or '-',
            candidato_vaga.candidato.cpf or '-',
            candidato_vaga.candidato.inscricao,
            candidato_vaga.oferta_vaga,
            candidato_vaga.oferta_vaga.curso_campus.diretoria.setor.uo.sigla,
        ]
        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)

    return rows


def __adicionar_cabecalho_publicacao_bibliografica_exportacao_excel(rows, variavel, ano_referencia, campus, total_publicacoes):
    pesquisa_ano_referencia = ['Ano de Referência', ano_referencia]
    pesquisa_sigla = ['Sigla', variavel.sigla]
    pesquisa_descricao = ['Descrição', variavel.descricao]
    pesquisa_total_publicacoes = ['Total de Publicações', total_publicacoes]
    pesquisa_campus = ['Campus', campus]

    rows.append(pesquisa_ano_referencia)
    rows.append(pesquisa_sigla)
    rows.append(pesquisa_descricao)
    rows.append(pesquisa_total_publicacoes)
    rows.append(pesquisa_campus)
    rows.append([''])


def trabalhos_exportacao(trabalhos, variavel, ano_referencia, campus, total_publicacoes):
    """
    Apresenta a tabela com os dados de trabalhos publicados em eventos.
    """
    rows = []

    __adicionar_cabecalho_publicacao_bibliografica_exportacao_excel(rows, variavel, ano_referencia, campus, total_publicacoes)

    header = ['', 'Matrícula', 'Nome', 'Evento', 'Título', 'Ano']
    rows.append(header)
    count = 0
    for trabalho in trabalhos:
        count += 1
        row = [
            count,
            trabalho.curriculo.vinculo.relacionamento.matricula,
            trabalho.curriculo.vinculo.pessoa.nome,
            trabalho.nome_evento,
            trabalho.titulo,
            trabalho.ano,
        ]
        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)

    return rows


def artigos_exportacao(trabalhos, variavel, ano_referencia, campus, total_publicacoes):
    """
    Apresenta a tabela com os dados de artigos publicados em eventos.
    """
    rows = []

    __adicionar_cabecalho_publicacao_bibliografica_exportacao_excel(rows, variavel, ano_referencia, campus, total_publicacoes)

    header = ['', 'Matrícula', 'Nome', 'Periódico/Revista', 'ISSN', 'Estrato', 'Título', 'Ano']
    rows.append(header)
    count = 0
    for trabalho in trabalhos:
        count += 1
        row = [
            count,
            trabalho.curriculo.vinculo.relacionamento.matricula,
            trabalho.curriculo.vinculo.pessoa.nome,
            trabalho.titulo_periodico_revista,
            trabalho.issn,
            trabalho.estrato,
            trabalho.titulo,
            trabalho.ano,
        ]
        # O código abaixo em tese é desnecessário!
        # Após alggum tempo, caso não apresente problemas, irei removê-lo.
        # for index,column in enumerate(row):
        #    row[index] = column
        rows.append(row)

    return rows


def livros_capitulos_exportacao(livros, capitulos, variavel, ano_referencia, campus, total_publicacoes):
    """
    Apresenta a tabela com os dados de livros e capitulos publicados por docentes.
    """
    rows = []

    __adicionar_cabecalho_publicacao_bibliografica_exportacao_excel(rows, variavel, ano_referencia, campus, total_publicacoes)

    header = ['', 'Matrícula', 'Nome', 'Editora', 'ISBN', 'Título', 'Ano']
    rows.append(header)
    count = 0
    for trabalho in livros:
        count += 1
        row = [
            count,
            trabalho.curriculo.vinculo.relacionamento.matricula,
            trabalho.curriculo.vinculo.pessoa.nome,
            trabalho.nome_editora,
            trabalho.isbn,
            trabalho.titulo,
            trabalho.ano,
        ]
        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)
    for trabalho in capitulos:
        count += 1
        row = [
            count,
            trabalho.curriculo.vinculo.relacionamento.matricula,
            trabalho.curriculo.vinculo.pessoa.nome,
            trabalho.nome_editora,
            trabalho.isbn,
            trabalho.titulo,
            trabalho.ano,
        ]
        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)

    return rows


def vagas_exportacao(vagas):
    """
    Apresenta a tabela com os dados de inscrições para exportação.
    """
    rows = []
    header = ['', 'Processo Seletivo', 'Curso', 'Campus', 'Quantidade']
    rows.append(header)
    count = 0
    for vaga in vagas:
        count += 1
        row = [count, f'{vaga.edital}', vaga.curso_campus, vaga.curso_campus.diretoria.setor.uo.sigla, vaga.qtd]
        for index, column in enumerate(row):
            row[index] = column
        rows.append(row)

    return rows


def get_exportacao(queryset, attributes, headers, task=None):
    try:
        if len(attributes) != len(headers):
            raise NameError('O número de atributos e cabeçalhos deve ser o mesmo')

        rows = []
        # insere a coluna com os números das linhas
        headers.insert(0, '#')
        # adiciona cabeçalhos
        rows.append(headers)

        count = 0
        if task:
            queryset = task.iterate(queryset)
        for registro in queryset:
            count += 1

            row = [count]

            for att in attributes:
                row.append(eval_attr(registro, att) or '-')

            for index, column in enumerate(row):
                row[index] = column
            rows.append(row)
        return rows
    except Exception:
        raise


# estrai os dados que serão utilizados na exportação mas não acrescenta os cabeçalhos
def get_exportacao_apenas_dados(queryset, attributes, cont_inicial, task=None):
    try:
        rows = []
        count = cont_inicial
        if task:
            queryset = task.iterate(queryset)
        for registro in queryset:
            count += 1

            row = [count]

            for att in attributes:
                try:
                    row.append(eval_attr(registro, att) or '-')
                except Exception:
                    row.append('-')

            for index, column in enumerate(row):
                row[index] = column
            rows.append(row)
        return rows
    except Exception:
        raise
