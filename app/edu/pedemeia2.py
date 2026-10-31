from tqdm import tqdm
from djtools.utils import requests
from datetime import timedelta, datetime
from django.db.models import Q, F, Value, IntegerField, CharField, OuterRef, Subquery
from comum.models import Configuracao
from edu.models import (
    MatriculaPeriodo,
    Modalidade,
    CursoCampus,
    FrequenciaPeDeMeia,
    Turma,
    MatriculaDiario,
    HistoricoSituacaoMatriculaPeriodo,
    SituacaoMatriculaPeriodo,
    Professor,
)
from django.conf import settings
from django.core.cache import cache


raca_cor_pessoa_fisica = {1: 3, 2: 2, 3: 1, 4: 4, 5: 5, 7: 0, None: 0}
sexo_pessoa_fisica = {'M': 1, 'F': 2}
modalidade_ensino_estudante = {Modalidade.INTEGRADO: 4, Modalidade.INTEGRADO_EJA: 3, Modalidade.FIC_INTEGRADO_EJA: 3}
estudante_vinculo_responsavel_1 = {'Pai/Mãe': 1, 'Avô/Avó': 1, 'Tio/Tia': 1, 'Sobrinho/Sobrinha': 1, 'Outro': 5, '': 5, None: 5}
mapa_situacoes = {
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
    SituacaoMatriculaPeriodo.APROVADO: 10,
    SituacaoMatriculaPeriodo.DEPENDENCIA: 10,
    SituacaoMatriculaPeriodo.REPROVADO: 12,
    SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA: 12,
}

escolaridade = {
    'Graduado': 7,
    'Graduada': 7,
    'Especialista': 8,
    'Mestre': 9,
    'Mestra': 9,
    'Doutor': 10,
    'Doutora': 10,
    'Pós-Doutor': 10,
    'Pós-Doutora': 10,
}

estados_ibge = {
    None: None,
    'RO': 11,
    'AC': 12,
    'AM': 13,
    'RR': 14,
    'AP': 15,
    'PA': 16,
    'TO': 17,
    'MA': 21,
    'PI': 22,
    'CE': 23,
    'RN': 24,
    'PB': 25,
    'PE': 26,
    'AL': 27,
    'SE': 28,
    'BA': 29,
    'MG': 31,
    'ES': 32,
    'RJ': 33,
    'SP': 35,
    'PR': 41,
    'SC': 42,
    'RS': 43,
    'MS': 50,
    'MT': 51,
    'GO': 52,
    'DF': 53,
}


def get_url(endpoint):
    url = Configuracao.get_valor_por_chave('edu', 'url_pedemeia')
    return f'{url}{endpoint}'


def get_headers():
    token = cache.get('token_pedemeia', None)
    if token:
        headers = {'Authorization': f'Bearer {token}'}
    else:
        username = Configuracao.get_valor_por_chave('edu', 'usuario_pedemeia')
        password = Configuracao.get_valor_por_chave('edu', 'senha_pedemeia')
        url = get_url('/api/v2/auth/login')
        data = {'password': password, 'username': username}
        response = requests.post(url, json=data, timeout=settings.REQUESTS_TIMEOUT)
        output = response.json()
        token = output['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        cache.set('token_pedemeia', token, timeout=60)
    return headers


def listar_alunos_aptos(ano_letivo, periodo_letivo, modalidades=(), matriculas=()):
    qs = MatriculaPeriodo.objects
    if matriculas:
        qs = qs.filter(aluno__matricula__in=matriculas)
    qs = qs.filter(aluno__matriz__isnull=False, aluno__curso_campus__modalidade__in=modalidades)
    qs = qs.exclude(aluno__pessoa_fisica__cpf='').exclude(aluno__pessoa_fisica__cpf__isnull=True)
    qs = qs.filter(
        Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo=ano_letivo)
        | Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
    )
    return qs


def dados_alunos(ano_letivo, periodo_letivo, atualizacao=False, modalidades=(), amostra=False, matriculas=()):
    qs = listar_alunos_aptos(ano_letivo, periodo_letivo, modalidades=modalidades, matriculas=matriculas)
    definir_dados_matriculas_periodo(qs)
    if atualizacao:
        qs = qs.filter(codigo_sgp__isnull=False, aluno__codigo_sgp__isnull=False)
    else:
        qs = qs.filter(codigo_sgp__isnull=True, data_matricula_periodo__isnull=False, calendario_academico__isnull=False)
    if amostra:
        qs = qs[0:2]

    dados = qs.values(
        id_sgp_estudante=F('aluno__codigo_sgp'),
        estudante_cpf=F('aluno__pessoa_fisica__cpf'),
        estudante_nome=F('aluno__pessoa_fisica__nome'),
        estudante_dt_nascimento=F('aluno__pessoa_fisica__nascimento_data'),
        estudante_sexo=F('aluno__pessoa_fisica__sexo'),
        estudante_raca_cor=F('aluno__vinculos__raca'),  # raca migrou de PessoaFisica p/ Vinculo
        estudante_quilombola=Value(0, output_field=IntegerField()),  # Não informado,
        estudante_nacionalidade=F('aluno__pais_origem__codigo'),
        estudante_responsavel_1_nome=F('aluno__responsavel'),
        estudante_vinculo_responsavel_1=F('aluno__parentesco_responsavel'),
        estudante_co_uf_res=F('aluno__cidade__estado'),
        estudante_co_municipio_res=F('aluno__cidade__codigo'),
        estudante_apoio_pedagogico=Value(0, output_field=IntegerField()),  # Não informado
        estudante_deficiencia=Value('0', output_field=CharField()),  # Não informado
        co_entidade=F('aluno__curso_campus__diretoria__setor__uo__codigo_inep'),
        no_entidade=F('aluno__curso_campus__diretoria__setor__uo__nome'),
        co_matricula_rede=F('aluno__matricula'),
        nu_ano_matricula=F('ano_letivo__ano'),
        data_inicio_matricula=F('data_matricula_periodo'),
        estudante_matricula_integral=Value(0, output_field=IntegerField()),  # Não informado
        modalidade_ensino_estudante=F('aluno__curso_campus__modalidade'),
        data_inicio_periodo_letivo=F('calendario_academico__data_inicio'),
        turma_localizacao=Value(1, output_field=IntegerField()),  #  A turma não está em local de funcionamento diferenciado
        estudante_etapa_de_ensino=F('aluno__periodo_atual'),
        estudante_ano_periodo=F('aluno__periodo_atual'),
    )
    # dados = dados.filter(aluno__matricula=20231031160061)

    for item in dados:
        item['estudante_nacionalidade'] = int(item['estudante_nacionalidade'] or 76)
        item['estudante_dt_nascimento'] = item['estudante_dt_nascimento'].strftime('%d/%m/%Y')
        item['estudante_raca_cor'] = raca_cor_pessoa_fisica[item['estudante_raca_cor']]
        estudante_ano_periodo = item.pop('estudante_ano_periodo')
        if item['modalidade_ensino_estudante'] == Modalidade.INTEGRADO_EJA:
            item['estudante_etapa_de_ensino'] = 62
            if estudante_ano_periodo in (1, 2):
                item['estudante_ano_periodo'] = 1
            elif estudante_ano_periodo in (3, 4):
                item['estudante_ano_periodo'] = 2
            else:
                item['estudante_ano_periodo'] = 3
        elif item['modalidade_ensino_estudante'] == Modalidade.FIC_INTEGRADO_EJA:
            item['estudante_etapa_de_ensino'] = 67
            if estudante_ano_periodo < 3:
                item['estudante_ano_periodo'] = estudante_ano_periodo
            else:
                item['estudante_ano_periodo'] = 3
        elif item['modalidade_ensino_estudante'] == Modalidade.INTEGRADO:
            item['estudante_etapa_de_ensino'] = {1: 30, 2: 31, 3: 32, 4: 33}[item['estudante_etapa_de_ensino']]
        item['estudante_sexo'] = sexo_pessoa_fisica[item['estudante_sexo']]
        item['modalidade_ensino_estudante'] = modalidade_ensino_estudante[item['modalidade_ensino_estudante']]
        item['data_inicio_matricula'] = item['data_inicio_matricula'].strftime('%d/%m/%Y') if item['data_inicio_matricula'] else None
        item['data_inicio_periodo_letivo'] = item['data_inicio_periodo_letivo'].strftime('%d/%m/%Y') if item['data_inicio_periodo_letivo'] else None
        item['estudante_responsavel_1_nome'] = item['estudante_responsavel_1_nome'] or 'Não cadastrado'
        item['estudante_vinculo_responsavel_1'] = estudante_vinculo_responsavel_1[item['estudante_vinculo_responsavel_1']]

        if atualizacao:
            item['editar_dados'] = 1
            del item['co_entidade']
            del item['no_entidade']
            del item['nu_ano_matricula']
            del item['turma_localizacao']
            del item['data_inicio_matricula']
            del item['estudante_etapa_de_ensino']
            del item['data_inicio_periodo_letivo']
            del item['estudante_apoio_pedagogico']
            del item['modalidade_ensino_estudante']
            del item['estudante_matricula_integral']
            del item['co_matricula_rede']
            del item['estudante_ano_periodo']
        else:
            del item['id_sgp_estudante']

    return [dict(**item) for item in dados]


def dados_profissionais(ano_letivo, modalidades, atualizacao=False, amostra=False):
    pks = (
        Professor.objects.filter(
            professordiario__diario__ano_letivo=ano_letivo, professordiario__diario__turma__curso_campus__modalidade__in=modalidades
        )
        .order_by('pk')
        .values_list('pk', flat=True)
        .distinct()
    )
    qs = Professor.objects.filter(  # .filter(pk=2058)
        vinculo__pessoa__pessoafisica__servidor_set__data_inicio_exercicio_na_instituicao__isnull=False,
        vinculo__setor__uo__codigo_inep__isnull=False,
        titulacao__isnull=False,
        vinculo__pessoa__pessoafisica__pessoaendereco__municipio__codigo_ibge__isnull=False,
    ).filter(pk__in=pks)
    if atualizacao:
        qs = qs.filter(codigo_sgp__isnull=False)
    else:
        qs = qs.filter(codigo_sgp__isnull=True)
    if amostra:
        qs = qs[0:2]
    dados = qs.values(
        profissional_cpf=F('vinculo__pessoa__pessoafisica__cpf'),
        profissional_nome=F('vinculo__pessoa__pessoafisica__nome'),
        profissional_dt_nascimento=F('vinculo__pessoa__pessoafisica__nascimento_data'),
        profissional_sexo=F('vinculo__pessoa__pessoafisica__sexo'),
        profissional_raca_cor=F('vinculo__raca'),
        profissional_quilombola=Value(0, output_field=IntegerField()),  # Não informado
        profissional_nacionalidade=Value(76, output_field=IntegerField()),  # Brasil
        co_nivel_escolaridade=(F('titulacao')),
        profissional_co_uf_res=F('vinculo__pessoa__pessoafisica__pessoaendereco__municipio__uf'),
        profissional_co_municipio_res=F('vinculo__pessoa__pessoafisica__pessoaendereco__municipio__codigo_ibge'),
        co_tipo_formacao_academica=Value(0, output_field=IntegerField()),  # Não informado
        co_area_conhecimento_formacao_academica=Value(0, output_field=IntegerField()),  # Não informado
        profissional_deficiencia=Value('0', output_field=CharField()),  # Não informado
        co_entidade=F('vinculo__setor__uo__codigo_inep'),
        co_tipo_vinculo=Value(0, output_field=IntegerField()),  # Não informado
        situacao_vinculo_profissional_rede=Value(1, output_field=IntegerField()),  # Ativo
        data_inicio_vinculo_profissional_rede=F('vinculo__pessoa__pessoafisica__servidor_set__data_inicio_exercicio_na_instituicao'),
        co_funcao=Value(1, output_field=IntegerField()),  # Docente
        data_ingresso=F('vinculo__pessoa__pessoafisica__servidor_set__data_inicio_exercicio_na_instituicao'),
        id_sgp_profissional=F('codigo_sgp'),
    )
    for item in dados:
        id_sgp_profissional = item.pop('id_sgp_profissional')
        item['profissional_co_uf_res'] = estados_ibge[item.get('profissional_co_uf_res')]
        item['profissional_sexo'] = sexo_pessoa_fisica[item['profissional_sexo']]
        item['profissional_raca_cor'] = raca_cor_pessoa_fisica[item['profissional_raca_cor']]
        item['profissional_dt_nascimento'] = item['profissional_dt_nascimento'].strftime('%d/%m/%Y')
        item['data_inicio_vinculo_profissional_rede'] = item['data_inicio_vinculo_profissional_rede'].strftime('%d/%m/%Y')
        item['data_ingresso'] = item['data_ingresso'].strftime('%d/%m/%Y')
        item['co_nivel_escolaridade'] = escolaridade.get(item['co_nivel_escolaridade'])

        if atualizacao:
            item['editar_dados'] = 1
            item['id_sgp_profissional'] = id_sgp_profissional
            del item['co_entidade']
            del item['data_ingresso']
            del item['co_tipo_vinculo']
            del item['co_nivel_escolaridade']
            del item['co_tipo_formacao_academica']
            del item['situacao_vinculo_profissional_rede']
            del item['data_inicio_vinculo_profissional_rede']
            del item['co_area_conhecimento_formacao_academica']
            del item['co_funcao']
    return [dict(**item) for item in dados]


def calcular_frequencia_suap(ano_letivo, periodo_letivo, mes, modalidades=None, atualizar_existente=True, task=None):
    qs = MatriculaPeriodo.objects.filter(codigo_sgp__isnull=False).filter(
        Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL, ano_letivo=ano_letivo)
        | Q(aluno__curso_campus__periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
    )
    if modalidades:
        qs = qs.filter(aluno__curso_campus__modalidade__in=modalidades)
    if not atualizar_existente:
        qs = qs.exclude(frequenciapedemeia__ano=ano_letivo, frequenciapedemeia__mes=mes)
    for matricula_periodo in task.iterate(qs.select_related('aluno')) if task else tqdm(qs.select_related('aluno')):
        (
            qtd_horas_ofertadas,
            _,
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
                qtd_horas_presentes=qtd_horas_presentes,
            )
        FrequenciaPeDeMeia.objects.filter(pk=frequencia.pk).update(
            qtd_horas_ofertadas=qtd_horas_ofertadas,
            qtd_horas_presentes=qtd_horas_presentes,
            data_ultima_atualizacao=datetime.now(),
        )
        frequencia.aulas.set(qs_qtd_horas_ofertada)
        frequencia.faltas.set(qs_qtd_horas_ausentes)
        frequencia.praticas_profissionais.set(frequencias_pratica_profissional)
    if task:
        task.finalize('Frequência calculada com sucesso.', '/admin/edu/operacaopedemeia/')


def frequencia_mensal(ano_letivo, mes, ferias=False, atualizacao=False, modalidades=(), amostra=False, matriculas=()):
    qs = FrequenciaPeDeMeia.objects.filter(ano=ano_letivo, mes=mes, matricula_periodo__codigo_sgp__isnull=False)
    if matriculas:
        qs = qs.filter(matricula_periodo__aluno__matricula__in=matriculas)
    if not ferias:
        qs = qs.filter(qtd_horas_ofertadas__gt=0)
    if modalidades:
        qs = qs.filter(matricula_periodo__aluno__curso_campus__modalidade__in=modalidades)
    # qs = qs.filter(matricula_periodo__aluno__matricula=20231031160061)
    if atualizacao:
        qs = qs.exclude(qtd_horas_ofertadas=F('qtd_horas_ofertadas_sgp'), qtd_horas_presentes=F('qtd_horas_presentes_sgp'))
    else:
        qs = qs.filter(qtd_horas_ofertadas_sgp__isnull=True)
    if amostra:
        qs = qs[0:2]
    dados = [
        {
            'ano_referencia': ano_frequencia,
            'mes_referencia': mes_frequencia,
            'id_sgp_matricula': codigo_sgp,
            'hl_ofertada_periodo': 0 if ferias else qtd_horas_ofertadas,
            'hl_presente_estudante_periodo': 0 if ferias else qtd_horas_presentes,
            'justificativa_suspensao_aulas': 7
            if ferias
            else None,  # 1 - Greve 2 - Situação de calamidade pública que exigiu o uso de seu espaço ou impediu o acesso à mesma 3 - A ausência de professor na escola resultou na falta de atividades letivas 4 - Situação de emergência em saúde ou pandemia, como um surto de doenças coletivas na escola 5 - Situação de reforma/reparos da infraestrutura da escola que impede o acesso à unidade escolar por conta de interdição impactando a realização das atividades letivas 6 - Situação de violência urbana ou grave ameaça que coloque em risco a segurança do(s) estudante(s) causando a interrupção imediata das atividades letivas, pois impede a frequência regular e segura dos alunos à escola 7 - Recesso/férias [período não contabilizado como período letivo ou ano letivo não iniciado] 99 - Outro "
        }
        for ano_frequencia, mes_frequencia, codigo_sgp, qtd_horas_ofertadas, qtd_horas_presentes in qs.values_list(
            'ano__ano', 'mes', 'matricula_periodo__codigo_sgp', 'qtd_horas_ofertadas', 'qtd_horas_presentes'
        )
    ]
    if atualizacao:
        for dado in dados:
            dado['editar_frequencia'] = 1
            dado['no_entidade'] = '-'
            dado['nu_ano_matricula'] = ano_letivo.ano
            dado['justificativa_edicao_frequencia'] = (
                2  # Complementação de informação: a frequência informada anteriormente estava incompleta e a edição se deve à atualização da informação
            )
    return dados


def frequencias_pendentes(ano_letivo, mes, ferias=False, modalidades=(), amostra=False):
    url = get_url(f'/api/v2/frequencia-mensal-matricula/{ano_letivo.ano}/{mes}/faltantes?page=1&page_size=5000')
    response = requests.get(url, headers=get_headers(), timeout=settings.REQUESTS_TIMEOUT)
    codigos_sgp = [item['id_sgp_matricula'] for item in response.json().get('items')]
    qs = FrequenciaPeDeMeia.objects.filter(ano=ano_letivo, mes=mes, matricula_periodo__codigo_sgp__in=codigos_sgp)

    if modalidades:
        qs = qs.filter(matricula_periodo__aluno__curso_campus__modalidade__in=modalidades)
    if amostra:
        qs = qs[0:2]
    dados = [
        {
            'ano_referencia': ano_frequencia,
            'mes_referencia': mes_frequencia,
            'id_sgp_matricula': codigo_sgp,
            'hl_ofertada_periodo': 0 if ferias else qtd_horas_ofertadas,
            'hl_presente_estudante_periodo': 0 if ferias else qtd_horas_presentes,
            'justificativa_suspensao_aulas': 7
            if ferias
            else None,  # 1 - Greve 2 - Situação de calamidade pública que exigiu o uso de seu espaço ou impediu o acesso à mesma 3 - A ausência de professor na escola resultou na falta de atividades letivas 4 - Situação de emergência em saúde ou pandemia, como um surto de doenças coletivas na escola 5 - Situação de reforma/reparos da infraestrutura da escola que impede o acesso à unidade escolar por conta de interdição impactando a realização das atividades letivas 6 - Situação de violência urbana ou grave ameaça que coloque em risco a segurança do(s) estudante(s) causando a interrupção imediata das atividades letivas, pois impede a frequência regular e segura dos alunos à escola 7 - Recesso/férias [período não contabilizado como período letivo ou ano letivo não iniciado] 99 - Outro "
        }
        for ano_frequencia, mes_frequencia, codigo_sgp, qtd_horas_ofertadas, qtd_horas_presentes in qs.values_list(
            'ano__ano', 'mes', 'matricula_periodo__codigo_sgp', 'qtd_horas_ofertadas', 'qtd_horas_presentes'
        )
    ]
    return dados


def definir_dados_matriculas_periodo(matriculas_periodo):
    # Definindo o calendário acadêmico baseado na turma
    qs = matriculas_periodo.filter(turma__isnull=False, calendario_academico__isnull=True)
    qs.update(calendario_academico_id=Subquery(Turma.objects.filter(id=OuterRef('turma_id')).values_list('calendario_academico_id')[:1]))
    # Definindo o calendário acadêmico baseado no diário quando não vinculado a uma turma
    qs = matriculas_periodo.filter(turma__isnull=True, calendario_academico__isnull=True, matriculadiario__isnull=False)
    qs.update(
        calendario_academico_id=Subquery(
            MatriculaDiario.objects.filter(matricula_periodo_id=OuterRef('id')).values_list('diario__calendario_academico_id')[:1]
        )
    )

    # Definindo a data de matrícula baseada no histórico da situação
    qs = matriculas_periodo.filter(data_matricula_periodo__isnull=True)
    qs.update(
        data_matricula_periodo=Subquery(
            HistoricoSituacaoMatriculaPeriodo.objects.filter(matricula_periodo_id=OuterRef('id'))
            .filter(situacao_id=2)
            .order_by('data')
            .values_list('data')[:1]
        )
    )

    # Definindo a data da situação no período baseada no histórico da situação
    qs = matriculas_periodo.filter(data_situacao_periodo__isnull=True)
    pks = list(qs.values_list('pk', flat=True))
    qs.update(
        data_situacao_periodo=Subquery(
            HistoricoSituacaoMatriculaPeriodo.objects.filter(matricula_periodo_id=OuterRef('id'))
            .filter(situacao_id=OuterRef('situacao_id'))
            .order_by('-data')
            .values_list('data')[:1]
        )
    )
    MatriculaPeriodo.objects.filter(pk__in=pks).update(data_situacao_periodo=F('data_situacao_periodo') - timedelta(days=1))


def movimentacoes(modalidades=(), amostra=False, matriculas=()):
    dados = []
    em_andamento = 0
    qs = MatriculaPeriodo.objects.filter(codigo_sgp__isnull=False)
    if matriculas:
        qs = qs.filter(aluno__matricula__in=matriculas)
    if modalidades:
        qs = qs.filter(aluno__curso_campus__modalidade__in=modalidades)
    for situacao_id, situacao_pedemeia in mapa_situacoes.items():
        if amostra and len(dados) == 2:
            break
        for id_sgp_matricula, data_fim, co_matricula_rede in (
            qs.filter(situacao_id=situacao_id, aluno__dt_conclusao_curso__isnull=True)
            .filter(situacao_pedemeia=em_andamento)
            .values_list('codigo_sgp', 'data_situacao_periodo', 'aluno__matricula')
        ):
            dados.append(
                {
                    'id_sgp_matricula': id_sgp_matricula,
                    'data_fim': data_fim,
                    'estudante_matricula_situacao': situacao_pedemeia,
                    'co_matricula_rede': co_matricula_rede,
                }
            )

    for dado in dados:
        dado['data_fim'] = dado['data_fim'].strftime('%d/%m/%Y')
    return dados
