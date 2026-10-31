import csv
import json
import math
import os
import tempfile
import time
from datetime import date

import openpyxl
from django.conf import settings
from django.db.models import Q
from openpyxl.styles import Font, PatternFill
from tqdm import tqdm

from comum.models import APIExterna
from djtools.utils import requests
from edu.models import (
    Aluno,
    CalendarioAcademico,
    ConfiguracaoPedidoMatricula,
    CursoCampus,
    Deficiencia,
    FrequenciaPeDeMeia,
    MatriculaPeriodo,
    Modalidade,
    ProcedimentoMatricula,
    RequisicaoPeDeMeia,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoNEE,
)

ANO_LETIVO = 2025
PERIODO_LETIVO = 2
FERIAS = True

service = None


CODIGOS_INEP_SGP = {
    '24329312': 66063,
    '24329304': 66062,
    '24328308': 66061,
    '24327328': 66060,
    '24327310': 66059,
    '24327301': 66058,
    '24089656': 65726,
    '24088510': 65626,
    '24086622': 65472,
    '24086479': 65470,
    '24085383': 65386,
    '24085375': 65385,
    '24085367': 65384,
    '24084336': 65297,
    '24084328': 65296,
    '24084310': 65295,
    '24083054': 65207,
    '24083046': 65206,
    '24083011': 65203,
    '24083003': 65202,
    '24069485': 64388,
    '24059110': 63843,
}
DADOS_ALUNOS = (
    'codigoMatriculaSgp',
    'matriculaRede',
    'cpf',
    'nome',
    'anoMatricula',
    'dataInicioMatricula',
    'dataInicioPeriodoLetivo',
    'serieAno',
    'estudanteAnoPeriodo',
    'situacaoMatricula',
    'estudanteSituacaoFinal',
    'dataFimOuAprovacao',
    'dataConclusaoEnsinoMedio',
    'bairro',
    'cep',
    'certidaoNascimento',
    'cnh',
    'codInstituicao',
    'cpfResponsavel',
    'dataAtivacaoMatricula',
    'dataNascimento',
    'deletadaEm',
    'email',
    'estudanteAnoPeriodo',
    'estudanteIntegral',
    'estudantePpl',
    'etapaEnsinoConsolidado',
    'formaOrganizacaoTurma',
    'genero',
    'id',
    'inep',
    'logradouro',
    'municipio',
    'nomeMaeEstudante',
    'nomeSocial',
    'numero',
    'numeroNIS',
    'numeroNISResponsavel',
    'orgaoEmissor',
    'outrasMatriculas',
    'racaCor',
    'rg',
    'situacaoCadastroValidado',
    'telefone',
    'tipoDeficiencia',
    'turmaOrganizacaoQuantidadeTotal',
    'uf',
)
COMPARAR = (
    'matriculaRede',
    'anoMatricula',
    'bairro',
    'cep',
    'codInstituicao',
    'cpf',
    'cpfResponsavel',
    'dataConclusaoEnsinoMedio',
    'dataInicioMatricula',
    'dataInicioPeriodoLetivo',
    'dataNascimento',
    'email',
    'estudanteAnoPeriodo',
    'estudanteIntegral',
    'estudantePpl',
    'estudanteSituacaoFinal',
    'formaOrganizacaoTurma',
    'genero',
    'logradouro',
    'municipio',
    'nome',
    'nomeMaeEstudante',
    'nomeSocial',
    'numero',
    'numeroNIS',
    'numeroNISResponsavel',
    'orgaoEmissor',
    'racaCor',
    'rg',
    'serieAno',
    'estudanteAnoPeriodo',
    'situacaoMatricula',
    'telefone',
    'uf',
    'dataFimOuAprovacao',
    'tipoDeficiencia',
    'turmaOrganizacaoQuantidadeTotal',
)
ATUALIZAR = 'nome', 'dataNascimento', 'logradouro', 'municipio', 'nomeMaeEstudante', 'numero', 'orgaoEmissor', 'racaCor', 'rg', 'uf', 'numeroNIS'
CADASTRAR = (
    'cpf',
    'numeroNIS',
    'nome',
    'email',
    'telefone',
    'dataNascimento',
    'matriculaRede',
    'inep',
    'dataInicioMatricula',
    'dataFimOuAprovacao',
    'serieAno',
    'estudanteAnoPeriodo',
    'racaCor',
    'logradouro',
    'bairro',
    'numero',
    'cep',
    'municipio',
    'uf',
    'genero',
    'cpfResponsavel',
    'nomeMaeEstudante',
    'numeroNISResponsavel',
    'rg',
    'orgaoEmissor',
    'situacaoMatricula',
    'tipoDeficiencia',
    'dataInicioPeriodoLetivo',
    'formaOrganizacaoTurma',
    'turmaOrganizacaoQuantidadeTotal',
)


def get_service():
    global service
    if service is None:
        api = APIExterna.PEDEMEIA
        service = api.get_service() if api.ativo else None
        os.makedirs('pedemeia', exist_ok=True)
    return service


def format(value):
    if value is None:
        return '-'
    if isinstance(value, bool):
        return 'S' if value else 'N'
    if isinstance(value, list):
        return ', '.join([str(v) for v in value])
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value).replace('\t', ' ').strip()


def get_value(dados, key):
    if key not in dados:
        if key == 'codigoMatricula':
            key = 'codigoMatriculaSgp'
        if key == 'codigoMatriculaSgp':
            key = 'codigoMatricula'
        if key == 'matriculaRede':
            return None
    return dados[key]


def listar_alunos_aptos(select_related=False):
    qs = MatriculaPeriodo.objects.filter(
        aluno__matriz__isnull=False, aluno__curso_campus__modalidade__in=[Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA]
    )
    qs = (
        qs.select_related('aluno__curso_campus__diretoria__setor__uo', 'aluno__matriz', 'aluno__pessoa_fisica', 'aluno__curso_campus__modalidade')
        if select_related
        else qs.select_related('aluno')
    )
    qs = qs.exclude(aluno__pessoa_fisica__cpf='').exclude(aluno__pessoa_fisica__cpf__isnull=True)
    qs = qs.filter(Q(aluno__situacao=SituacaoMatricula.MATRICULADO) | Q(codigo_sgp__isnull=False))
    qs = qs.filter(
        Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo__ano=ANO_LETIVO)
        | Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo__ano=ANO_LETIVO, periodo_letivo=PERIODO_LETIVO)
    )
    return qs


def consultar_unidades_sgp():
    unidades = []
    url = get_service().api_externa.url_base.replace('v2', 'v1') + '/unidades-de-ensino'
    params = {'per_page': 100}
    response = requests.get(
        url,
        params=params,
        headers=get_service().get_headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    )
    for item in response.json()['data']:
        unidades.append((item['id'], item['inep'], item['nome']))
    return unidades


def consultar_alunos_sgp(ativos=True, task=None):
    sep = '\t'
    c1 = None
    c2 = None
    file = open('pedemeia/alunos-sgp.csv', 'w' if ativos else 'a')

    url = get_service().api_externa.url_base.replace('v2', 'v1') + '/estudantes/'
    params = {'per_page': 1, 'page': 1, 'situacao_matricula': 'ATIVAS' if ativos else 'INATIVAS', 'ano_matricula': ANO_LETIVO}  # :
    response = requests.get(
        url,
        params=params,
        headers=get_service().get_headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    pages = list(range(1, math.ceil(int(response['pagination']['total']) / 100) + 1))
    iterator = task.iterate if task else tqdm
    for page in iterator(pages):
        time.sleep(1)
        params.update(per_page=100, page=page)
        try:
            response = requests.get(
                url,
                params=params,
                headers=get_service().get_headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            ).json()
        except Exception:
            # print(e)
            # breakpoint()
            pass
        for i, estudante in enumerate(response['data']):
            matriculas = estudante.pop('matriculas', ())
            if c1 is None:
                c1 = list(estudante)
            s1 = sep.join([format(estudante[k]) for k in c1])
            for j, matricula in enumerate(matriculas):
                if c2 is None:
                    c2 = list(matricula)
                s2 = sep.join([format(matricula[k]) for k in c2])
                if page == 1 and i == 0 and j == 0 and ativos:
                    _ = file.write(f'{sep.join(c1)}{sep}{sep.join(c2)}\n')
                _ = file.write(f'{s1}{sep}{s2}\n')

    file.close()


def consultar_aluno(matricula):
    aluno = Aluno.objects.get(matricula=matricula)
    url = get_service().api_externa.url_base.replace('v2', 'v1') + f'/estudantes/{aluno.pessoa_fisica.cpf.replace(".", "").replace("-", "")}'
    response = requests.get(
        url,
        params={},
        headers=get_service().get_headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    )
    return response.json()


def computar_tipo_deficiencia(data):
    """
    0: Não informado
    1: Não possui
    2: Cegueira
    3: Deficiência auditiva
    4: Deficiência física
    5: Deficiência intelectual
    6: Surdez
    7: Surdocegueira
    8: Deficiência múltipla
    9: Transtorno do Espectro autista
    10: Altas habilidades/superdotação
    """
    mapeamento_deficiencia = {
        1: '2',  # Baixa visão => Cegueira
        2: '2',  # Visão monocular => Cegueira
        3: '2',  # Cegueira => Cegueira
        4: '3',  # Deficiência auditiva => Deficiência auditiva
        5: '4',  # Deficiência física => Deficiência física
        6: '5',  # Deficiência intelectual => Deficiência intelectual
        7: '6',  # Surdez => Surdez
        8: '7',  # Surdocegueira => Surdocegueira
        9: '9',  # Transtorno de Espectro Autista (TEA) => Transtorno do Espectro autista
    }

    aluno_id = data['id']
    tipos_deficiencia = set()
    deficiencias = set(Deficiencia.objects.filter(aluno=aluno_id).values_list('classificacao_educacenso', flat=True))
    for d in deficiencias:
        if d in mapeamento_deficiencia:
            tipos_deficiencia.add(mapeamento_deficiencia[d])

    if TipoNEE.objects.filter(aluno=aluno_id, classificacao_educacenso=TipoNEE.ALTAS_HABILIDADES).exists():
        tipos_deficiencia.add('10')

    return tipos_deficiencia or {'1'}


def consultar_alunos_suap(task=None):
    mapa = {
        'aluno__id': 'id',
        'aluno__bairro': 'bairro',
        'aluno__cep': 'cep',
        'aluno__cidade__codigo': 'municipio',
        'aluno__cidade__estado': 'uf',
        'codigo_sgp': 'codigoMatriculaSgp',
        'aluno__cpf_responsavel': 'cpfResponsavel',
        'aluno__curso_campus_id': 'curso_campus_id',
        'aluno__data_matricula': 'data_matricula',
        'aluno__logradouro': 'logradouro',
        'aluno__matricula': 'matriculaRede',
        'aluno__nis': 'numeroNIS',
        'aluno__nome_mae': 'nomeMaeEstudante',
        'aluno__numero': 'numero',
        'aluno__pessoa_fisica__cpf': 'cpf',
        'aluno__vinculos__email_pessoal': 'email',
        'aluno__email_academico': 'email',
        'aluno__pessoa_fisica__nascimento_data': 'dataNascimento',
        'aluno__pessoa_fisica__nome': 'nome',
        'aluno__pessoa_fisica__nome_social': 'nomeSocial',
        'aluno__vinculos__raca': 'racaCor',
        'aluno__numero_rg': 'rg',
        'aluno__orgao_emissao_rg__nome': 'orgaoEmissor',
        'aluno__pessoa_fisica__sexo': 'genero',
        'situacao': 'situacao',
        'aluno__telefone_principal': 'telefone',
        'aluno__curso_campus__diretoria__setor__uo__codigo_inep': 'codInstituicao',
        'aluno__curso_campus__modalidade_id': 'modalidade',
        'aluno__periodo_atual': 'periodo_atual',
        'aluno__matriz__qtd_periodos_letivos': 'turmaOrganizacaoQuantidadeTotal',
        'aluno__dt_conclusao_curso': 'dataConclusaoEnsinoMedio',
        'aluno__percentual_ch_cumprida': 'percentual_ch_cumprida',
    }
    situacoes1 = {
        SituacaoMatriculaPeriodo.JUBILADO: 7,
        SituacaoMatriculaPeriodo.EVASAO: 6,
        SituacaoMatriculaPeriodo.TRANCADA: 7,
        SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE: 7,
        SituacaoMatriculaPeriodo.CANCELADA: 7,
        SituacaoMatriculaPeriodo.TRANSF_CURSO: 2,
        SituacaoMatriculaPeriodo.TRANSF_EXTERNA: 5,
        SituacaoMatriculaPeriodo.CANCELAMENTO_COMPULSORIO: 7,
        SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DESLIGAMENTO: 7,
        SituacaoMatriculaPeriodo.CANCELAMENTO_POR_DUPLICIDADE: 7,
    }
    situacoes2 = {
        SituacaoMatriculaPeriodo.APROVADO: 10,
        SituacaoMatriculaPeriodo.DEPENDENCIA: 10,
        SituacaoMatriculaPeriodo.REPROVADO: 12,
        SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA: 12,
    }
    situacoes = {**situacoes1, **situacoes2}
    file = open('pedemeia/alunos-suap.csv', 'w')
    qs = listar_alunos_aptos(select_related=True)
    dados_inicio_periodo_letivo1 = (
        CalendarioAcademico.objects.filter(turma__curso_campus__modalidade__in=[Modalidade.INTEGRADO])
        .filter(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo__ano=ANO_LETIVO)
        .order_by('turma__curso_campus_id', 'data_inicio')
        .values_list('turma__curso_campus_id', 'data_inicio')
        .distinct('turma__curso_campus_id', 'data_inicio')
    )
    dados_inicio_periodo_letivo2 = (
        CalendarioAcademico.objects.filter(turma__curso_campus__modalidade__in=[Modalidade.INTEGRADO_EJA])
        .filter(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo__ano=ANO_LETIVO, periodo_letivo=PERIODO_LETIVO)
        .order_by('turma__curso_campus_id', 'data_inicio')
        .values_list('turma__curso_campus_id', 'data_inicio')
        .distinct('turma__curso_campus_id', 'data_inicio')
    )
    dados_data_matricula1 = (
        ConfiguracaoPedidoMatricula.objects.filter(cursos__modalidade__in=[Modalidade.INTEGRADO])
        .filter(cursos__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo__ano=ANO_LETIVO)
        .order_by('cursos__id', 'data_inicio')
        .values_list('cursos__id', 'data_inicio')
        .distinct('cursos__id')
    )
    dados_data_matricula2 = (
        ConfiguracaoPedidoMatricula.objects.filter(cursos__modalidade__in=[Modalidade.INTEGRADO_EJA])
        .filter(cursos__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo__ano=ANO_LETIVO, periodo_letivo=PERIODO_LETIVO)
        .order_by('cursos__id', 'data_inicio')
        .values_list('cursos__id', 'data_inicio')
        .distinct('cursos__id')
    )
    dados_fim_periodo_letivo1 = (
        CalendarioAcademico.objects.filter(turma__curso_campus__modalidade__in=[Modalidade.INTEGRADO])
        .filter(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo__ano=ANO_LETIVO)
        .order_by('turma__curso_campus_id', 'data_inicio')
        .values_list('turma__curso_campus_id', 'data_fim')
        .distinct('turma__curso_campus_id', 'data_inicio')
    )
    dados_fim_periodo_letivo2 = (
        CalendarioAcademico.objects.filter(turma__curso_campus__modalidade__in=[Modalidade.INTEGRADO_EJA])
        .filter(turma__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo__ano=ANO_LETIVO, periodo_letivo=PERIODO_LETIVO)
        .order_by('turma__curso_campus_id', 'data_inicio')
        .values_list('turma__curso_campus_id', 'data_fim')
        .distinct('turma__curso_campus_id', 'data_inicio')
    )
    dados_procedimento_matricula = (
        qs.filter(situacao__in=situacoes1)
        .values_list('aluno__matricula', 'procedimentomatricula__data')
        .order_by('aluno__matricula', 'procedimentomatricula__data')
        .distinct('aluno__matricula')
    ).exclude(procedimentomatricula__tipo=ProcedimentoMatricula.MATRICULA_VINCULO)
    dados_situacao_periodo = qs.values_list('aluno__matricula', 'situacao_id').order_by('aluno__matricula', '-id').distinct('aluno__matricula', 'id')
    data_matricula = {
        **dict(dados_data_matricula1),
        **dict(dados_data_matricula2),
    }
    inicio_periodo_letivo = {
        **dict(dados_inicio_periodo_letivo1),
        **dict(dados_inicio_periodo_letivo2),
    }
    fim_periodo_letivo = {
        **dict(dados_fim_periodo_letivo1),
        **dict(dados_fim_periodo_letivo2),
    }
    data_procedimento_matricula = dict(dados_procedimento_matricula)
    situacao_periodo = dict(dados_situacao_periodo)
    qs = qs.values(*mapa.keys())
    iterator = task.iterate if task else tqdm
    for i, values in enumerate(iterator(qs)):
        data = dict(**values)
        email1 = data.pop('aluno__vinculos__email_pessoal')
        email3 = data.pop('aluno__email_academico')
        data['aluno__email_academico'] = email1 or email3
        data['aluno__telefone_principal'] = (
            data['aluno__telefone_principal'].replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
            if data['aluno__telefone_principal']
            else None
        )
        data['aluno__pessoa_fisica__sexo'] = {'M': 1, 'F': 2, None: 0}[data['aluno__pessoa_fisica__sexo']]
        data['aluno__vinculos__raca'] = {7: 0, 3: 1, 2: 2, 1: 3, 4: 4, 5: 5, None: 0}[data['aluno__vinculos__raca']]
        data['aluno__pessoa_fisica__nome_social'] = data['aluno__pessoa_fisica__nome_social'] or None
        data['aluno__pessoa_fisica__cpf'] = (
            data['aluno__pessoa_fisica__cpf'].replace('.', '').replace('-', '') if data['aluno__pessoa_fisica__cpf'] else None
        )
        data['aluno__cpf_responsavel'] = data['aluno__cpf_responsavel'].replace('.', '').replace('-', '') if data['aluno__cpf_responsavel'] else None
        data['aluno__cep'] = data['aluno__cep'].replace('.', '').replace('-', '') if data['aluno__cep'] else None
        data['aluno__nis'] = None if data['aluno__nis'] == '0' else data['aluno__nis']
        data['aluno__orgao_emissao_rg__nome'] = data['aluno__orgao_emissao_rg__nome'][0:10] if data['aluno__orgao_emissao_rg__nome'] else None

        if i == 0:
            _ = file.write('\t'.join(DADOS_ALUNOS))
            _ = file.write('\n')

        for k, v in mapa.items():
            try:
                data[v] = data.pop(k)
            except KeyError:
                pass

        deficiencias = computar_tipo_deficiencia(data)
        data['estudantePpl'] = '1' if deficiencias else ''
        data['tipoDeficiencia'] = ', '.join(deficiencias) if deficiencias else ''
        data['situacaoMatricula'] = (
            'S'
            if data['situacao']
            in (SituacaoMatriculaPeriodo.EM_ABERTO, SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL)
            else 'N'
        )
        data['codInstituicao'] = CODIGOS_INEP_SGP[data['codInstituicao']]
        data['dataInicioPeriodoLetivo'] = format(inicio_periodo_letivo.get(data['curso_campus_id'], '-'))
        data['serieAno'] = 62 if data['modalidade'] == Modalidade.INTEGRADO_EJA else {1: 30, 2: 31, 3: 32, 4: 33}[data['periodo_atual']]
        data['estudanteAnoPeriodo'] = (
            (
                3
                if data['percentual_ch_cumprida'] and data['percentual_ch_cumprida'] > 60
                else (2 if data['percentual_ch_cumprida'] and data['percentual_ch_cumprida'] > 30 else 1)
            )
            if data['serieAno'] == 62
            else None
        )
        data['formaOrganizacaoTurma'] = 2 if data['modalidade'] == Modalidade.INTEGRADO_EJA else 1
        data['anoMatricula'] = ANO_LETIVO
        data['dataFimOuAprovacao'] = (
            None
            if data['situacaoMatricula'] == 'S'
            else format(data_procedimento_matricula.get(data['matriculaRede'], fim_periodo_letivo.get(data['curso_campus_id'])))
        )
        if ANO_LETIVO > 2024:
            data['numeroNIS'] = '-'
        if data['tipoDeficiencia'] == '-':
            data['tipoDeficiencia'] = 1
        if data['dataConclusaoEnsinoMedio']:
            data['estudanteSituacaoFinal'] = '11'
            data['dataFimOuAprovacao'] = min(data['dataFimOuAprovacao'], format(data['dataConclusaoEnsinoMedio']))
        else:
            data['estudanteSituacaoFinal'] = format(situacoes.get(situacao_periodo.get(data['matriculaRede'])))
        # A data de matrícula no período é a data da renovação de matrícula ou a data da matrícula institucional
        data['dataInicioMatricula'] = format(data_matricula.get(data['curso_campus_id']) or data['data_matricula'])
        _ = file.write('\t'.join([format(data.get(key)) for key in DADOS_ALUNOS]))
        _ = file.write('\n')


def definir_codigo_sgp_suap():
    codigos = {}
    reader = csv.DictReader(open('pedemeia/alunos-sgp.csv'), delimiter='\t')
    for row in reader:
        key = '{}:{}'.format(row['matriculaRede'], row['codInstituicao'])
        codigos[key] = row['codigoMatriculaSgp']

    qs = listar_alunos_aptos().filter(codigo_sgp__isnull=True)
    for pk, matricula, codigo_uo_sgp in tqdm(qs.values_list('pk', 'aluno__matricula', 'aluno__curso_campus__diretoria__setor__uo__codigo_sgp')):
        key = f'{matricula}:{codigo_uo_sgp}'
        codigo_sgp = codigos.get(key)
        if codigo_sgp:
            _ = MatriculaPeriodo.objects.filter(pk=pk).update(codigo_sgp=codigo_sgp)


def consultar_frequencia_sgp(ano_letivo, mes):
    sep = '\t'
    file = open(f'pedemeia/frequencias-sgp-{mes}-{ano_letivo.ano}.csv', 'w')
    url = get_service().api_externa.url_base.replace('v2', 'v1') + '/frequencia-mensal/'
    params = {'per_page': 1, 'page': 1, 'mes_referencia': mes, 'ano_referencia': ano_letivo.ano}
    response = requests.get(
        url,
        params=params,
        headers=get_service().get_headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    pages = list(range(1, math.ceil(int(response['pagination']['total']) / 100) + 1))
    for page in tqdm(pages):
        params.update(per_page=100, page=page)
        response = requests.get(
            url,
            params=params,
            headers=get_service().get_headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        ).json()
        for index, frequencia in enumerate(response['data']):
            if page == 1 and index == 0:
                keys = list(frequencia)
                _ = file.write(sep.join(keys))
                _ = file.write('\n')
            _ = file.write(sep.join([format(frequencia[k]) for k in keys]))
            _ = file.write('\n')
    file.close()


def consultar_frequencia_faltante_sgp(ano_letivo, mes):
    frequencias = []
    url = get_service().api_externa.url_base.replace('v2', 'v1') + f'/frequencia-mensal/faltantes/{ano_letivo}/{mes}'
    params = {'per_page': 1, 'page': 1}
    response = requests.get(
        url,
        params=params,
        headers=get_service().get_headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    pages = list(range(1, math.ceil(int(response['pagination']['total']) / 100) + 1))
    for page in tqdm(pages):
        params.update(per_page=100, page=page)
        response = requests.get(
            url,
            params=params,
            headers=get_service().get_headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        ).json()
        frequencias.extend(response['data'])
    return frequencias


def consultar_frequencia_suap(ano_letivo, mes):
    sep = '\t'
    qs = (
        RequisicaoPeDeMeia.objects.filter(
            processada=True,
            tipo__in=(
                RequisicaoPeDeMeia.FREQUENCIA,
                RequisicaoPeDeMeia.ATUALIZACAO_FREQUENCIA,
            ),
            ano=ano_letivo,
            mes=mes,
        )
        .order_by('aluno_id', 'ano_id', 'mes', 'tipo')
        .distinct('aluno_id', 'ano_id', 'mes')
        .values_list('registro_serializado', flat=True)
    )
    file = open(f'pedemeia/frequencias-suap-{mes}-{ano_letivo.ano}.csv', 'w')
    for i, dados in enumerate(qs):
        if i == 0:
            keys = (
                'codigoMatriculaSgp',
                'anoReferencia',
                'mesReferencia',
                'hlOfertadaPeriodo',
                'hlPresentePeriodo',
                'justificativaSuspensaoAulas',
                'matriculaRede',
            )
            _ = file.write(sep.join(keys))
            _ = file.write('\n')

        _ = file.write(sep.join([format(get_value(dados, k)) for k in keys]))
        _ = file.write('\n')

    file.close()


def calcular_frequencia_suap(ano_letivo, mes, task=None):
    file = open(f'pedemeia/frequencias-hoje-{mes}-{ano_letivo.ano}.csv', 'w')
    file.write(
        'codigoMatriculaSgp\tanoReferencia\tmesReferencia\thlOfertadaPeriodo\thlPresentePeriodo\tjustificativaSuspensaoAula\tPercentual\tmatriculaRede\n'
    )
    qs = listar_alunos_aptos()
    iterator = task.iterate if task else tqdm
    for matricula_periodo in iterator(qs):
        (
            qtd_horas_ofertadas,
            qtd_horas_ausentes,
            qtd_horas_presentes,
            qs_qtd_horas_ofertada,
            qs_qtd_horas_ausentes,
            frequencias_pratica_profissional,
        ) = matricula_periodo.aluno.calcular_frequencia_pe_de_meia(ano_letivo.ano, mes)
        frequencia = FrequenciaPeDeMeia.objects.filter(matricula_periodo=matricula_periodo, ano=ano_letivo, mes=mes).first()
        if frequencia is None:
            frequencia = FrequenciaPeDeMeia.objects.create(
                matricula_periodo=matricula_periodo,
                ano=ano_letivo,
                mes=mes,
                qtd_horas_ofertadas=qtd_horas_ofertadas,
                qtd_horas_ausentes=qtd_horas_ausentes,
                qtd_horas_presentes=qtd_horas_presentes,
            )
        FrequenciaPeDeMeia.objects.filter(pk=frequencia.pk).update(
            qtd_horas_ofertadas=qtd_horas_ofertadas, qtd_horas_ausentes=qtd_horas_ausentes, qtd_horas_presentes=qtd_horas_presentes
        )
        frequencia.aulas.set(qs_qtd_horas_ofertada)
        frequencia.faltas.set(qs_qtd_horas_ausentes)
        frequencia.praticas_profissionais.set(frequencias_pratica_profissional)
        file.write(
            '{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
                matricula_periodo.codigo_sgp,
                ano_letivo.ano,
                mes,
                qtd_horas_ofertadas,
                qtd_horas_presentes,
                '-',
                int(qtd_horas_presentes / qtd_horas_ofertadas * 100.0) if qtd_horas_presentes else 0,
                matricula_periodo.aluno.matricula,
            )
        )
    file.close()
    if task:
        qs = FrequenciaPeDeMeia.objects.filter(
            ano=ano_letivo, mes=mes, qtd_horas_ofertadas__gt=0, matricula_periodo__codigo_sgp__isnull=False
        ).values_list('matricula_periodo__codigo_sgp', 'qtd_horas_ofertadas', 'qtd_horas_presentes')
        dados = []
        for codigo_sgp, qtd_horas_ofertadas, qtd_horas_presentes in qs:
            dados.append(
                {
                    'codigoMatriculaSgp': codigo_sgp,
                    'mesReferencia': str(mes).rjust(2, '0'),
                    'anoReferencia': ano_letivo.ano,
                    'hlOfertadaPeriodo': qtd_horas_ofertadas,
                    'hlPresentePeriodo': qtd_horas_presentes,
                    'justificativaSuspensaoAulas': None,
                    'justificativaEdicaoFrequencia': 2,
                }
            )
        fd, file_path = tempfile.mkstemp(suffix='.json', text=True)
        with os.fdopen(fd, 'w') as file:
            file.write(json.dumps(dados))
            task.finalize('Frequência calculada com sucesso.', '/admin/edu/operacaopedemeia/', file_path=file_path)


def indexar_frequencias(ano, mes, prefixo):
    arquivo = f'pedemeia/frequencias-{prefixo}-{mes}-{ano}.csv'
    dados = {}
    reader = csv.DictReader(open(arquivo), delimiter='\t')
    for row in reader:
        dados[row['codigoMatriculaSgp']] = (
            row['hlOfertadaPeriodo'],
            row['hlPresentePeriodo'],
        )
    return dados


def indexar_alunos_sgp():
    dados = {}
    reader = csv.DictReader(open('pedemeia/alunos-sgp.csv'), delimiter='\t')
    for row in reader:
        dados[row['codigoMatriculaSgp']] = row
    return dados


def indexar_alunos_suap():
    dados = {}
    reader = csv.DictReader(open('pedemeia/alunos-suap.csv'), delimiter='\t')
    for row in reader:
        dados[row['codigoMatriculaSgp']] = row
    return dados


def gerar_relatorio_frequencias(periodos):
    """Gera relatório de frequências de alunos a partir dos períodos informados.

    Args:
        periodos: queryset ou lista de períodos letivos.

    Returns:
        XlsResponse: resposta com o arquivo XLS gerado.
    """
    import pandas as pd

    # Styles
    bold_font = Font(bold=True)

    # Style 2: Light green bg, green font
    style2_fill = PatternFill(start_color='90EE90', end_color='90EE90', fill_type='solid')
    style2_font = Font(color='008000')

    # Style 3: Dark green bg, white font
    style3_fill = PatternFill(start_color='006400', end_color='006400', fill_type='solid')
    style3_font = Font(color='FFFFFF')

    # Style 4: Red bg, white font
    style4_fill = PatternFill(start_color='FF0000', end_color='FF0000', fill_type='solid')
    style4_font = Font(color='FFFFFF')

    wb = openpyxl.Workbook()
    # Remove default sheet
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])

    alunos_sgp = indexar_alunos_sgp()

    EMPTY_DICT = {}
    EMPTY_STRING = ''

    sheet = wb.create_sheet('ALUNOS')
    for j, coluna in enumerate(DADOS_ALUNOS):
        cell = sheet.cell(row=1, column=j + 1, value=coluna)
        cell.font = bold_font
    sheet.cell(row=1, column=len(DADOS_ALUNOS) + 1, value='sistema')
    sheet.cell(row=1, column=len(DADOS_ALUNOS) + 2, value='Destacar')

    try:
        df_suap = pd.read_csv('pedemeia/alunos-suap.csv', sep='\t', dtype=str, keep_default_na=False)
    except FileNotFoundError:
        df_suap = pd.DataFrame(columns=DADOS_ALUNOS)

    i = 2
    cadastro = []
    atualizacao = []
    movimentacao = []
    reativacao = []
    frequencias = []
    atualizacao_matriculas = []
    confirmacao_conclusao = []

    for _, linha in df_suap.iterrows():
        linha = linha.to_dict()
        reativado = False
        destacar = False
        codigo_sgp = linha.get('codigoMatriculaSgp')

        linha2 = alunos_sgp.get(codigo_sgp, {})
        atualizar = {}
        for j, coluna in enumerate(DADOS_ALUNOS):
            v1 = linha.get(coluna, EMPTY_STRING)

            # Default style
            current_font = None
            current_fill = None

            if linha2:
                v2 = linha2.get(coluna, EMPTY_STRING)
                if coluna in COMPARAR:
                    igual = str(v1).lower() == str(v2).lower()
                    if coluna == 'estudanteSituacaoFinal' and str(v2) == '13':
                        igual = True

                    if igual:
                        current_fill = style3_fill
                        current_font = style3_font
                    else:
                        current_fill = style4_fill
                        current_font = style4_font

                    if coluna == 'estudanteSituacaoFinal' and not igual:
                        destacar = True
                else:
                    if str(v1).lower() == str(v2).lower():
                        current_fill = style2_fill
                        current_font = style2_font
                    else:
                        pass  # Default style

                if coluna in ATUALIZAR and str(v1).lower() != str(v2).lower():
                    atualizar[coluna] = linha[coluna]

                cell1 = sheet.cell(row=i, column=j + 1, value=v1)
                if current_font:
                    cell1.font = current_font
                if current_fill:
                    cell1.fill = current_fill

                cell2 = sheet.cell(row=i + 1, column=j + 1, value=v2)
                if current_font:
                    cell2.font = current_font
                if current_fill:
                    cell2.fill = current_fill
            else:
                cell1 = sheet.cell(row=i, column=j + 1, value=v1)
                # Default style

        if atualizar:
            atualizar['cpfNis'] = linha['cpf']
            atualizacao.append(atualizar)

        # Devem ser cadastrados os alunos sem códigos SGP no período letivo
        if linha.get('codigoMatriculaSgp') == '-':
            registro = {k: None if linha.get(k) == '-' else linha.get(k) for k in CADASTRAR}
            registro['instituicao'] = linha.get('codInstituicao')
            registro['tipoDeficiencia'] = linha.get('tipoDeficiencia', '').split(', ')
            registro['anoMatricula'] = ANO_LETIVO
            cadastro.append(registro)

        if linha2:
            # Devem ser atualizadas as matrículas com codigoMatriculaSgp e dataInicioPeriodoLetivo no SUAP e sem matriculaRede no SGP
            if linha.get('codigoMatriculaSgp') and linha.get('dataInicioPeriodoLetivo') != '-' and linha2.get('matriculaRede') == '-':
                registro = {
                    'codigoMatriculaSgp': codigo_sgp,
                    'matriculaRede': linha.get('matriculaRede'),
                    'dataInicioPeriodoLetivo': linha.get('dataInicioPeriodoLetivo'),
                    'formaOrganizacaoTurma': linha.get('formaOrganizacaoTurma'),
                    'turmaOrganizacaoQuantidadeTotal': linha.get('turmaOrganizacaoQuantidadeTotal'),
                }
                if linha2.get('dataInicioMatricula') and linha.get('matriculaRede', '').startswith('2024'):
                    registro.update(dataInicioMatricula=linha.get('dataInicioMatricula'), anoMatricula=int(linha.get('anoMatricula')))
                atualizacao_matriculas.append(registro)

            # Devem ser reativados os alunos com estudanteSituacaoFinal divergente e que estejam inativos no SGP por motivo diferente da conclusão
            if (
                linha.get('estudanteSituacaoFinal') != linha2.get('estudanteSituacaoFinal')
                and linha2.get('situacaoMatricula') == 'N'
                and linha2.get('estudanteSituacaoFinal') != '13'
            ):
                registro = {k: None if linha.get(k) == '-' else linha.get(k) for k in CADASTRAR}
                registro['codigoMatriculaSgp'] = linha2.get('codigoMatriculaSgp')
                registro['instituicao'] = linha.get('codInstituicao')
                registro['tipoDeficiencia'] = linha.get('tipoDeficiencia', '').split(', ')
                registro['anoMatricula'] = ANO_LETIVO
                reativacao.append(registro)
                reativado = True

            # Devem ser movimentados alunos com estudanteSituacaoFinal no SUAP e sem estudanteSituacaoFinal no SGP; ou que foram reativdos
            if (linha.get('estudanteSituacaoFinal') != '-' and linha2.get('estudanteSituacaoFinal') == '-') or reativado:
                registro = {
                    'codigoMatriculaSgp': codigo_sgp,
                    'estudanteSituacaoFinal': linha.get('estudanteSituacaoFinal'),
                    'dataFimOuAprovacao': linha.get('dataFimOuAprovacao'),
                }
                if linha.get('dataConclusaoEnsinoMedio') != '-':
                    registro['dataConclusaoEnsinoMedio'] = linha.get('dataConclusaoEnsinoMedio')
                movimentacao.append(registro)

            # Devem ter a conclusão confirmada os alunos que estão com a situação 11 no SUAP e SGP
            if (linha.get('estudanteSituacaoFinal') == '11' and linha2.get('estudanteSituacaoFinal') == '11') and not reativado:
                confirmacao_conclusao.append({'codigoMatriculaSgp': codigo_sgp})

        if FERIAS:
            frequencias.append(
                {
                    'codigoMatriculaSgp': codigo_sgp,
                    'mesReferencia': 2,
                    'anoReferencia': ANO_LETIVO,
                    'hlOfertadaPeriodo': 0,
                    'hlPresentePeriodo': 0,
                    'justificativaSuspensaoAulas': 7,
                }
            )

        sheet.cell(row=i, column=len(DADOS_ALUNOS) + 1, value='SUAP')
        if linha2:
            sheet.cell(row=i + 1, column=len(DADOS_ALUNOS) + 1, value='SGP')
        if destacar:
            sheet.cell(row=i, column=len(DADOS_ALUNOS) + 2, value='X')
            if linha2:
                sheet.cell(row=i + 1, column=len(DADOS_ALUNOS) + 2, value='X')
        i += 2 if linha2 else 1

    for ano, mes in periodos:
        atualizacao_frequencia = []
        sheet = wb.create_sheet(f'{mes}-{ano}')

        # Merge cells
        sheet.merge_cells(start_row=1, start_column=1, end_row=2, end_column=1)
        sheet.cell(row=1, column=1, value='CODIGO').font = bold_font

        sheet.merge_cells(start_row=1, start_column=2, end_row=2, end_column=2)
        sheet.cell(row=1, column=2, value='MATRICULA').font = bold_font

        sheet.merge_cells(start_row=1, start_column=3, end_row=2, end_column=3)
        sheet.cell(row=1, column=3, value='ANO').font = bold_font

        sheet.merge_cells(start_row=1, start_column=4, end_row=2, end_column=4)
        sheet.cell(row=1, column=4, value='MES').font = bold_font

        sheet.merge_cells(start_row=1, start_column=5, end_row=2, end_column=5)
        sheet.cell(row=1, column=5, value='GREVE').font = bold_font

        sheet.merge_cells(start_row=1, start_column=6, end_row=1, end_column=8)
        sheet.cell(row=1, column=6, value='SGP').font = bold_font

        for n in [6, 9, 12]:
            sheet.cell(row=2, column=n, value='OFERTADO').font = bold_font
            sheet.cell(row=2, column=n + 1, value='PRESENTE').font = bold_font
            sheet.cell(row=2, column=n + 2, value='PERCENTUAL').font = bold_font

        sheet.merge_cells(start_row=1, start_column=9, end_row=1, end_column=11)
        sheet.cell(row=1, column=9, value='SUAP').font = bold_font

        sheet.merge_cells(start_row=1, start_column=12, end_row=1, end_column=14)
        sheet.cell(row=1, column=12, value='HOJE').font = bold_font

        sheet.merge_cells(start_row=1, start_column=15, end_row=2, end_column=15)
        sheet.cell(row=1, column=15, value='CONSISTENTE').font = bold_font

        sheet.merge_cells(start_row=1, start_column=16, end_row=2, end_column=16)
        sheet.cell(row=1, column=16, value='ATUALIZADO').font = bold_font

        i = 3
        sgp = indexar_frequencias(ano=ano, mes=mes, prefixo='sgp')
        suap = indexar_frequencias(ano=ano, mes=mes, prefixo='suap')
        hoje = indexar_frequencias(ano=ano, mes=mes, prefixo='hoje')

        for k in sgp:
            ofertada_sgp, presente_sgp = sgp[k]
            ofertada_sgp = float(ofertada_sgp)
            presente_sgp = float(presente_sgp)
            percentual_sgp = int(presente_sgp / ofertada_sgp * 100 if ofertada_sgp else 0)
            ofertada_suap, presente_suap = suap.get(k, (None, None))
            ofertada_suap = float(ofertada_suap) if ofertada_suap else None
            presente_suap = float(presente_suap) if presente_suap else None
            percentual_suap = int(presente_suap / ofertada_suap * 100 if ofertada_suap else 0)
            ofertada_hoje, presente_hoje = hoje.get(k, (None, None))
            ofertada_hoje = float(ofertada_hoje) if ofertada_hoje else None
            presente_hoje = float(presente_hoje) if presente_hoje else None
            percentual_hoje = int(presente_hoje / ofertada_hoje * 100 if ofertada_hoje and presente_hoje else 0)
            consistente = ofertada_sgp == ofertada_suap and presente_sgp == presente_suap and 'S' or 'N'
            atualizado = ofertada_sgp == ofertada_hoje and presente_sgp == presente_hoje and 'S' or 'N'
            if ofertada_hoje:
                atualizacao_frequencia.append(
                    {
                        'codigoMatriculaSgp': k,
                        'anoReferencia': ano,
                        'mesReferencia': mes,
                        'hlOfertadaPeriodo': int(ofertada_hoje),
                        'hlPresentePeriodo': int(presente_hoje),
                        'justificativaEdicaoFrequencia': 2,
                    }
                )
            line = (
                k,
                alunos_sgp.get(k, EMPTY_DICT).get('matriculaRede'),
                ano,
                mes,
                'N',
                ofertada_sgp,
                presente_sgp,
                percentual_sgp,
                ofertada_suap,
                presente_suap,
                percentual_suap,
                ofertada_hoje,
                presente_hoje,
                percentual_hoje,
                consistente,
                atualizado,
            )
            for j, label in enumerate(line):
                cell = sheet.cell(row=i, column=j + 1, value=label)
                if atualizado == 'S':
                    cell.fill = style3_fill
                    cell.font = style3_font
                elif consistente == 'S':
                    cell.fill = style2_fill
                    cell.font = style2_font
                else:
                    pass
            i += 1
        with open(f'pedemeia/frequencias-hoje-{mes}-{ano}.json', 'w') as file:
            file.write(json.dumps(atualizacao_frequencia, indent=4, ensure_ascii=False))

    wb.save('pedemeia/pedemeia.xlsx')

    if atualizacao:
        with open('pedemeia/atualizacao_alunos.json', 'w') as file:
            file.write(json.dumps(atualizacao, indent=4, ensure_ascii=False))
    if cadastro:
        with open('pedemeia/cadastro_alunos.json', 'w') as file:
            file.write(json.dumps(cadastro, indent=4, ensure_ascii=False))
    if reativacao:
        with open('pedemeia/reativacao_alunos.json', 'w') as file:
            file.write(json.dumps(reativacao, indent=4, ensure_ascii=False))
    if movimentacao:
        with open('pedemeia/movimentacao.json', 'w') as file:
            file.write(json.dumps(movimentacao, indent=4, ensure_ascii=False))
    if atualizacao_matriculas:
        with open('pedemeia/atualizacao_matriculas.json', 'w') as file:
            file.write(json.dumps(atualizacao_matriculas, indent=4, ensure_ascii=False))
    if confirmacao_conclusao:
        with open('pedemeia/confirmacao_conclusao.json', 'w') as file:
            file.write(json.dumps(confirmacao_conclusao, indent=4, ensure_ascii=False))
    if frequencias:
        with open('pedemeia/frequencias.json', 'w') as file:
            file.write(json.dumps(frequencias, indent=4, ensure_ascii=False))
