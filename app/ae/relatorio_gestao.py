from collections import OrderedDict

from ae.models import (
    DadosRelatorioGrafico,
    RelatorioGestaoAtendimentos,
    RelatorioGestaoAuxilios,
    RelatorioGestaoBolsas,
    RelatorioGestaoProgramas,
    RelatorioGestaoResumo,
    RelatorioGestaoSaude,
    RelatorioGrafico,
)


def preencher_relatorio_total(relatorio, dados):
    relatorio.qtd_janeiro = dados['meses'][1]['qtd']
    relatorio.qtd_fevereiro = dados['meses'][2]['qtd']
    relatorio.qtd_marco = dados['meses'][3]['qtd']
    relatorio.qtd_abril = dados['meses'][4]['qtd']
    relatorio.qtd_maio = dados['meses'][5]['qtd']
    relatorio.qtd_junho = dados['meses'][6]['qtd']
    relatorio.qtd_julho = dados['meses'][7]['qtd']
    relatorio.qtd_agosto = dados['meses'][8]['qtd']
    relatorio.qtd_setembro = dados['meses'][9]['qtd']
    relatorio.qtd_outubro = dados['meses'][10]['qtd']
    relatorio.qtd_novembro = dados['meses'][11]['qtd']
    relatorio.qtd_dezembro = dados['meses'][12]['qtd']
    relatorio.total_1_semestre = dados['total_1_sem']
    relatorio.total_2_semestre = dados['total_2_sem']
    relatorio.total_anual = dados['total']


def preencher_relatorio_alunos(relatorio, dados):
    relatorio.qtd_janeiro = len(dados['meses'][1]['qtd_aluno'])
    relatorio.qtd_fevereiro = len(dados['meses'][2]['qtd_aluno'])
    relatorio.qtd_marco = len(dados['meses'][3]['qtd_aluno'])
    relatorio.qtd_abril = len(dados['meses'][4]['qtd_aluno'])
    relatorio.qtd_maio = len(dados['meses'][5]['qtd_aluno'])
    relatorio.qtd_junho = len(dados['meses'][6]['qtd_aluno'])
    relatorio.qtd_julho = len(dados['meses'][7]['qtd_aluno'])
    relatorio.qtd_agosto = len(dados['meses'][8]['qtd_aluno'])
    relatorio.qtd_setembro = len(dados['meses'][9]['qtd_aluno'])
    relatorio.qtd_outubro = len(dados['meses'][10]['qtd_aluno'])
    relatorio.qtd_novembro = len(dados['meses'][11]['qtd_aluno'])
    relatorio.qtd_dezembro = len(dados['meses'][12]['qtd_aluno'])
    relatorio.total_1_semestre = len(dados['total_alunos_1_sem'])
    relatorio.total_2_semestre = len(dados['total_alunos_2_sem'])
    relatorio.total_anual = len(dados['total_alunos'])


def preencher_relatorio_valores(relatorio, dados):
    relatorio.qtd_janeiro = dados['meses'][1]['valor']
    relatorio.qtd_fevereiro = dados['meses'][2]['valor']
    relatorio.qtd_marco = dados['meses'][3]['valor']
    relatorio.qtd_abril = dados['meses'][4]['valor']
    relatorio.qtd_maio = dados['meses'][5]['valor']
    relatorio.qtd_junho = dados['meses'][6]['valor']
    relatorio.qtd_julho = dados['meses'][7]['valor']
    relatorio.qtd_agosto = dados['meses'][8]['valor']
    relatorio.qtd_setembro = dados['meses'][9]['valor']
    relatorio.qtd_outubro = dados['meses'][10]['valor']
    relatorio.qtd_novembro = dados['meses'][11]['valor']
    relatorio.qtd_dezembro = dados['meses'][12]['valor']
    relatorio.total_1_semestre = dados['valor_total_1_sem']
    relatorio.total_2_semestre = dados['valor_total_2_sem']
    relatorio.total_anual = dados['valor_total']


def obter_dict_meses():
    meses = {}
    for i in range(1, 13):
        meses[i] = {}
    return meses


def preencher_valores_meses(relatorio, meses, chave):
    meses[1][chave] = relatorio.qtd_janeiro
    meses[2][chave] = relatorio.qtd_fevereiro
    meses[3][chave] = relatorio.qtd_marco
    meses[4][chave] = relatorio.qtd_abril
    meses[5][chave] = relatorio.qtd_maio
    meses[6][chave] = relatorio.qtd_junho
    meses[7][chave] = relatorio.qtd_julho
    meses[8][chave] = relatorio.qtd_agosto
    meses[9][chave] = relatorio.qtd_setembro
    meses[10][chave] = relatorio.qtd_outubro
    meses[11][chave] = relatorio.qtd_novembro
    meses[12][chave] = relatorio.qtd_dezembro


def preencher_relatorio_atendimentos(rel, atendimentos, atendimentos_valor):
    relatorios = []
    agrupador = RelatorioGestaoAtendimentos.TOTAL_ATENDIMENTOS
    for tipo_atendimento, dados in list(atendimentos.items()):
        relatorio = RelatorioGestaoAtendimentos()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        relatorio.custeio = dados['custeio']
        preencher_relatorio_total(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoAtendimentos.ALUNOS_ASSISTIDOS
    for tipo_atendimento, dados in list(atendimentos.items()):
        relatorio = RelatorioGestaoAtendimentos()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        relatorio.custeio = dados['custeio']
        preencher_relatorio_alunos(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoAtendimentos.VALORES_GASTOS
    for tipo_atendimento, dados in list(atendimentos_valor.items()):
        relatorio = RelatorioGestaoAtendimentos()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        relatorio.custeio = dados['custeio']
        preencher_relatorio_valores(relatorio, dados)
        relatorios.append(relatorio)

    RelatorioGestaoAtendimentos.objects.bulk_create(relatorios)


def obter_relatorio_atendimentos(rel):
    relatorios_atendimentos = rel.relatoriogestaoatendimentos_set.all()

    atendimentos = OrderedDict()
    for relatorio_atendimentos in relatorios_atendimentos.exclude(agrupador=RelatorioGestaoAtendimentos.VALORES_GASTOS):
        if relatorio_atendimentos.tipo in atendimentos:
            dados = atendimentos[relatorio_atendimentos.tipo]
        else:
            dados = {}
            atendimentos[relatorio_atendimentos.tipo] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses

        dados['custeio'] = relatorio_atendimentos.custeio
        if relatorio_atendimentos.agrupador == RelatorioGestaoAtendimentos.TOTAL_ATENDIMENTOS:
            dados['total_1_sem'] = relatorio_atendimentos.total_1_semestre
            dados['total_2_sem'] = relatorio_atendimentos.total_2_semestre
            dados['total'] = relatorio_atendimentos.total_anual
            preencher_valores_meses(relatorio_atendimentos, meses, 'qtd')
        if relatorio_atendimentos.agrupador == RelatorioGestaoAtendimentos.ALUNOS_ASSISTIDOS:
            dados['total_alunos_1_sem'] = relatorio_atendimentos.total_1_semestre
            dados['total_alunos_2_sem'] = relatorio_atendimentos.total_2_semestre
            dados['total_alunos'] = relatorio_atendimentos.total_anual
            preencher_valores_meses(relatorio_atendimentos, meses, 'qtd_aluno')

    atendimentos_valor = OrderedDict()
    for relatorio_atendimentos in relatorios_atendimentos.filter(agrupador=RelatorioGestaoAtendimentos.VALORES_GASTOS):
        if relatorio_atendimentos.tipo in atendimentos_valor:
            dados = atendimentos_valor[relatorio_atendimentos.tipo]
        else:
            dados = {}
            atendimentos_valor[relatorio_atendimentos.tipo] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses

        if relatorio_atendimentos.agrupador == RelatorioGestaoAtendimentos.VALORES_GASTOS:
            dados['valor_total_1_sem'] = relatorio_atendimentos.total_1_semestre
            dados['valor_total_2_sem'] = relatorio_atendimentos.total_2_semestre
            dados['valor_total'] = relatorio_atendimentos.total_anual
            preencher_valores_meses(relatorio_atendimentos, meses, 'valor')

    return atendimentos, atendimentos_valor


def preencher_relatorio_auxilios(rel, auxilios):
    relatorios = []
    agrupador = RelatorioGestaoAuxilios.TOTAL_AUXILIOS
    for tipo_atendimento, dados in list(auxilios.items()):
        relatorio = RelatorioGestaoAuxilios()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        preencher_relatorio_total(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoAuxilios.ALUNOS_ASSISTIDOS
    for tipo_atendimento, dados in list(auxilios.items()):
        relatorio = RelatorioGestaoAuxilios()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        preencher_relatorio_alunos(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoAuxilios.VALORES_GASTOS
    for tipo_atendimento, dados in list(auxilios.items()):
        relatorio = RelatorioGestaoAuxilios()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo = tipo_atendimento
        preencher_relatorio_valores(relatorio, dados)
        relatorios.append(relatorio)

    RelatorioGestaoAuxilios.objects.bulk_create(relatorios)


def obter_relatorio_auxilios(rel):
    relatorios_auxilios = rel.relatoriogestaoauxilios_set.all()

    auxilios = OrderedDict()
    for relatorio_auxilios in relatorios_auxilios:
        if relatorio_auxilios.tipo in auxilios:
            dados = auxilios[relatorio_auxilios.tipo]
        else:
            dados = {}
            auxilios[relatorio_auxilios.tipo] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses

        if relatorio_auxilios.agrupador == RelatorioGestaoAuxilios.TOTAL_AUXILIOS:
            dados['total_1_sem'] = relatorio_auxilios.total_1_semestre
            dados['total_2_sem'] = relatorio_auxilios.total_2_semestre
            dados['total'] = relatorio_auxilios.total_anual
            preencher_valores_meses(relatorio_auxilios, meses, 'qtd')
        if relatorio_auxilios.agrupador == RelatorioGestaoAuxilios.ALUNOS_ASSISTIDOS:
            dados['total_alunos_1_sem'] = relatorio_auxilios.total_1_semestre
            dados['total_alunos_2_sem'] = relatorio_auxilios.total_2_semestre
            dados['total_alunos'] = relatorio_auxilios.total_anual
            preencher_valores_meses(relatorio_auxilios, meses, 'qtd_aluno')
        if relatorio_auxilios.agrupador == RelatorioGestaoAuxilios.VALORES_GASTOS:
            dados['valor_total_1_sem'] = relatorio_auxilios.total_1_semestre
            dados['valor_total_2_sem'] = relatorio_auxilios.total_2_semestre
            dados['valor_total'] = relatorio_auxilios.total_anual
            preencher_valores_meses(relatorio_auxilios, meses, 'valor')

    return auxilios


def preencher_relatorio_bolsas(rel, bolsas):
    relatorios = []
    agrupador = RelatorioGestaoBolsas.TOTAL_BOLSAS
    for categoria, dados in list(bolsas.items()):
        relatorio = RelatorioGestaoBolsas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.categoria = categoria
        preencher_relatorio_total(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoBolsas.ALUNOS_ASSISTIDOS
    for categoria, dados in list(bolsas.items()):
        relatorio = RelatorioGestaoBolsas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.categoria = categoria
        preencher_relatorio_alunos(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoBolsas.VALORES_GASTOS
    for categoria, dados in list(bolsas.items()):
        relatorio = RelatorioGestaoBolsas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.categoria = categoria
        preencher_relatorio_valores(relatorio, dados)
        relatorios.append(relatorio)

    RelatorioGestaoBolsas.objects.bulk_create(relatorios)


def obter_relatorio_bolsas(rel):
    relatorios_bolsas = rel.relatoriogestaobolsas_set.all()
    bolsas = OrderedDict()
    for relatorio_bolsas in relatorios_bolsas:
        if relatorio_bolsas.categoria in bolsas:
            dados = bolsas[relatorio_bolsas.categoria]
        else:
            dados = {}
            bolsas[relatorio_bolsas.categoria] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses
        if relatorio_bolsas.agrupador == RelatorioGestaoBolsas.TOTAL_BOLSAS:
            dados['total_1_sem'] = relatorio_bolsas.total_1_semestre
            dados['total_2_sem'] = relatorio_bolsas.total_2_semestre
            dados['total'] = relatorio_bolsas.total_anual
            preencher_valores_meses(relatorio_bolsas, meses, 'qtd')
        if relatorio_bolsas.agrupador == RelatorioGestaoBolsas.ALUNOS_ASSISTIDOS:
            dados['total_alunos_1_sem'] = relatorio_bolsas.total_1_semestre
            dados['total_alunos_2_sem'] = relatorio_bolsas.total_2_semestre
            dados['total_alunos'] = relatorio_bolsas.total_anual
            preencher_valores_meses(relatorio_bolsas, meses, 'qtd_aluno')
        if relatorio_bolsas.agrupador == RelatorioGestaoBolsas.VALORES_GASTOS:
            dados['valor_total_1_sem'] = relatorio_bolsas.total_1_semestre
            dados['valor_total_2_sem'] = relatorio_bolsas.total_2_semestre
            dados['valor_total'] = relatorio_bolsas.total_anual
            preencher_valores_meses(relatorio_bolsas, meses, 'valor')

    return bolsas


def preencher_relatorio_programas(rel, programas):
    relatorios = []
    agrupador = RelatorioGestaoProgramas.TOTAL_PARTICIPACOES
    for programa, dados in list(programas.items()):
        relatorio = RelatorioGestaoProgramas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.programa = programa
        preencher_relatorio_total(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoProgramas.ALUNOS_ASSISTIDOS
    for programa, dados in list(programas.items()):
        relatorio = RelatorioGestaoProgramas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.programa = programa
        preencher_relatorio_alunos(relatorio, dados)
        relatorios.append(relatorio)

    agrupador = RelatorioGestaoProgramas.VALORES_GASTOS
    for programa, dados in list(programas.items()):
        relatorio = RelatorioGestaoProgramas()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.programa = programa
        preencher_relatorio_valores(relatorio, dados)
        relatorios.append(relatorio)

    RelatorioGestaoProgramas.objects.bulk_create(relatorios)


def obter_relatorio_programas(rel):
    relatorios_programas = rel.relatoriogestaoprogramas_set.all()

    programas = OrderedDict()
    for relatorio_programas in relatorios_programas:
        if relatorio_programas.programa in programas:
            dados = programas[relatorio_programas.programa]
        else:
            dados = {}
            programas[relatorio_programas.programa] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses
        if relatorio_programas.agrupador == RelatorioGestaoProgramas.TOTAL_PARTICIPACOES:
            dados['total_1_sem'] = relatorio_programas.total_1_semestre
            dados['total_2_sem'] = relatorio_programas.total_2_semestre
            dados['total'] = relatorio_programas.total_anual
            preencher_valores_meses(relatorio_programas, meses, 'qtd')
        if relatorio_programas.agrupador == RelatorioGestaoProgramas.ALUNOS_ASSISTIDOS:
            dados['total_alunos_1_sem'] = relatorio_programas.total_1_semestre
            dados['total_alunos_2_sem'] = relatorio_programas.total_2_semestre
            dados['total_alunos'] = relatorio_programas.total_anual
            preencher_valores_meses(relatorio_programas, meses, 'qtd_aluno')
        if relatorio_programas.agrupador == RelatorioGestaoProgramas.VALORES_GASTOS:
            dados['valor_total_1_sem'] = relatorio_programas.total_1_semestre
            dados['valor_total_2_sem'] = relatorio_programas.total_2_semestre
            dados['valor_total'] = relatorio_programas.total_anual
            preencher_valores_meses(relatorio_programas, meses, 'valor')

    return programas


def get_tipo_atendimento_nome(tipo_atendimento):
    tipo_atendimento_nome = None
    if tipo_atendimento == 'aval_bio_aberta':
        tipo_atendimento_nome = 'Avaliação Biomédica Aberta'
    elif tipo_atendimento == 'aval_bio_fechada':
        tipo_atendimento_nome = 'Avaliação Biomédica Fechada'
    elif tipo_atendimento == 'medico':
        tipo_atendimento_nome = 'Atendimento Médico'
    elif tipo_atendimento == 'enfermagem':
        tipo_atendimento_nome = 'Atendimento de Enfermagem'
    elif tipo_atendimento == 3:
        tipo_atendimento_nome = 'Atendimento Odontológico'
    elif tipo_atendimento == 4:
        tipo_atendimento_nome = 'Atendimento Psicológico'
    elif tipo_atendimento == 5:
        tipo_atendimento_nome = 'Atendimento Nutricional'
    elif tipo_atendimento == 6:
        tipo_atendimento_nome = 'Atendimento Multidisciplinar'
    return tipo_atendimento_nome


def preencher_relatorio_saude(rel, saude):
    relatorios = []
    agrupador = RelatorioGestaoSaude.TOTAL_ATENDIMENTOS
    for tipo_atendimento, dados in list(saude.items()):
        relatorio = RelatorioGestaoSaude()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo_atendimento = get_tipo_atendimento_nome(tipo_atendimento)
        if relatorio.tipo_atendimento:
            preencher_relatorio_total(relatorio, dados)
            relatorios.append(relatorio)

    agrupador = RelatorioGestaoSaude.ALUNOS_ASSISTIDOS
    for tipo_atendimento, dados in list(saude.items()):
        relatorio = RelatorioGestaoSaude()
        relatorio.relatorio = rel
        relatorio.agrupador = agrupador
        relatorio.tipo_atendimento = get_tipo_atendimento_nome(tipo_atendimento)
        if relatorio.tipo_atendimento:
            preencher_relatorio_alunos(relatorio, dados)
            relatorios.append(relatorio)

    RelatorioGestaoSaude.objects.bulk_create(relatorios)


def obter_relatorio_saude(rel):
    relatorios_saude = rel.relatoriogestaosaude_set.all()

    saude = OrderedDict()
    for relatorio_saude in relatorios_saude:
        if relatorio_saude.tipo_atendimento in saude:
            dados = saude[relatorio_saude.tipo_atendimento]
        else:
            dados = {}
            saude[relatorio_saude.tipo_atendimento] = dados

        if 'meses' in dados:
            meses = dados['meses']
        else:
            meses = obter_dict_meses()
            dados['meses'] = meses

        if relatorio_saude.agrupador == RelatorioGestaoSaude.TOTAL_ATENDIMENTOS:
            dados['total_1_sem'] = relatorio_saude.total_1_semestre
            dados['total_2_sem'] = relatorio_saude.total_2_semestre
            dados['total'] = relatorio_saude.total_anual
            preencher_valores_meses(relatorio_saude, meses, 'qtd')
        if relatorio_saude.agrupador == RelatorioGestaoSaude.ALUNOS_ASSISTIDOS:
            dados['total_alunos_1_sem'] = relatorio_saude.total_1_semestre
            dados['total_alunos_2_sem'] = relatorio_saude.total_2_semestre
            dados['total_alunos'] = relatorio_saude.total_anual
            preencher_valores_meses(relatorio_saude, meses, 'qtd_aluno')

    return saude


def preencher_relatorio_resumo_total(relatorio, dados, total_1_sem, total_2_sem, total):
    relatorio.qtd_janeiro = len(dados[1])
    relatorio.qtd_fevereiro = len(dados[2])
    relatorio.qtd_marco = len(dados[3])
    relatorio.qtd_abril = len(dados[4])
    relatorio.qtd_maio = len(dados[5])
    relatorio.qtd_junho = len(dados[6])
    relatorio.qtd_julho = len(dados[7])
    relatorio.qtd_agosto = len(dados[8])
    relatorio.qtd_setembro = len(dados[9])
    relatorio.qtd_outubro = len(dados[10])
    relatorio.qtd_novembro = len(dados[11])
    relatorio.qtd_dezembro = len(dados[12])
    relatorio.total_1_semestre = len(total_1_sem)
    relatorio.total_2_semestre = len(total_2_sem)
    relatorio.total_anual = len(total)


def obter_dados_valores_resumo(relatorio):
    dados = {}
    dados[1] = relatorio.qtd_janeiro
    dados[2] = relatorio.qtd_fevereiro
    dados[3] = relatorio.qtd_marco
    dados[4] = relatorio.qtd_abril
    dados[5] = relatorio.qtd_maio
    dados[6] = relatorio.qtd_junho
    dados[7] = relatorio.qtd_julho
    dados[8] = relatorio.qtd_agosto
    dados[9] = relatorio.qtd_setembro
    dados[10] = relatorio.qtd_outubro
    dados[11] = relatorio.qtd_novembro
    dados[12] = relatorio.qtd_dezembro
    dados['total_1_semestre'] = relatorio.total_1_semestre
    dados['total_2_semestre'] = relatorio.total_2_semestre
    dados['total_anual'] = relatorio.total_anual
    return dados


def preencher_relatorio_resumo(rel, total_geral_atendimentos, total_geral_auxilios, total_geral_bolsas, total_geral_programas, total_geral_saude):
    total_geral = set()
    total_geral_1_sem = set()
    total_geral_2_sem = set()
    total_geral_mes = {}
    somatorio_atendimentos_unicos_1_sem = set()
    somatorio_atendimentos_unicos_2_sem = set()
    somatorio_atendimentos_unicos = set()
    somatorio_auxilios_unicos_1_sem = set()
    somatorio_auxilios_unicos_2_sem = set()
    somatorio_auxilios_unicos = set()
    somatorio_bolsas_unicos_1_sem = set()
    somatorio_bolsas_unicos_2_sem = set()
    somatorio_bolsas_unicos = set()
    somatorio_programas_unicos_1_sem = set()
    somatorio_programas_unicos_2_sem = set()
    somatorio_programas_unicos = set()
    somatorio_saude_unicos_1_sem = set()
    somatorio_saude_unicos_2_sem = set()
    somatorio_saude_unicos = set()
    for mes in range(1, 13):
        total_mes = set()
        total_mes = total_mes.union(total_geral_atendimentos[mes])
        somatorio_atendimentos_unicos = somatorio_atendimentos_unicos.union(total_geral_atendimentos[mes])
        total_mes = total_mes.union(total_geral_auxilios[mes])
        somatorio_auxilios_unicos = somatorio_auxilios_unicos.union(total_geral_auxilios[mes])
        total_mes = total_mes.union(total_geral_bolsas[mes])
        somatorio_bolsas_unicos = somatorio_bolsas_unicos.union(total_geral_bolsas[mes])
        total_mes = total_mes.union(total_geral_programas[mes])
        somatorio_programas_unicos = somatorio_programas_unicos.union(total_geral_programas[mes])
        total_mes = total_mes.union(total_geral_saude[mes])
        somatorio_saude_unicos = somatorio_saude_unicos.union(total_geral_saude[mes])
        total_geral = total_geral.union(total_mes)
        total_geral_mes[mes] = total_mes
        if mes <= 6:
            somatorio_atendimentos_unicos_1_sem = somatorio_atendimentos_unicos_1_sem.union(total_geral_atendimentos[mes])
            somatorio_auxilios_unicos_1_sem = somatorio_auxilios_unicos_1_sem.union(total_geral_auxilios[mes])
            somatorio_bolsas_unicos_1_sem = somatorio_bolsas_unicos_1_sem.union(total_geral_bolsas[mes])
            somatorio_programas_unicos_1_sem = somatorio_programas_unicos_1_sem.union(total_geral_programas[mes])
            somatorio_saude_unicos_1_sem = somatorio_saude_unicos_1_sem.union(total_geral_saude[mes])
            total_geral_1_sem = total_geral_1_sem.union(total_mes)
        else:
            somatorio_atendimentos_unicos_2_sem = somatorio_atendimentos_unicos_2_sem.union(total_geral_atendimentos[mes])
            somatorio_auxilios_unicos_2_sem = somatorio_auxilios_unicos_2_sem.union(total_geral_auxilios[mes])
            somatorio_bolsas_unicos_2_sem = somatorio_bolsas_unicos_2_sem.union(total_geral_bolsas[mes])
            somatorio_programas_unicos_2_sem = somatorio_programas_unicos_2_sem.union(total_geral_programas[mes])
            somatorio_saude_unicos_2_sem = somatorio_saude_unicos_2_sem.union(total_geral_saude[mes])
            total_geral_2_sem = total_geral_2_sem.union(total_mes)

    relatorios = []
    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.ATENDIMENTOS
    preencher_relatorio_resumo_total(
        relatorio, total_geral_atendimentos, somatorio_atendimentos_unicos_1_sem, somatorio_atendimentos_unicos_2_sem, somatorio_atendimentos_unicos
    )
    relatorios.append(relatorio)

    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.AUXILIOS
    preencher_relatorio_resumo_total(
        relatorio, total_geral_auxilios, somatorio_auxilios_unicos_1_sem, somatorio_auxilios_unicos_2_sem, somatorio_auxilios_unicos
    )
    relatorios.append(relatorio)

    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.BOLSAS
    preencher_relatorio_resumo_total(
        relatorio, total_geral_bolsas, somatorio_bolsas_unicos_1_sem, somatorio_bolsas_unicos_2_sem, somatorio_bolsas_unicos
    )
    relatorios.append(relatorio)

    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.PARTICIPANTES_PROGRAMAS
    preencher_relatorio_resumo_total(
        relatorio, total_geral_programas, somatorio_programas_unicos_1_sem, somatorio_programas_unicos_2_sem, somatorio_programas_unicos
    )
    relatorios.append(relatorio)

    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.ATENDIMENTOS_SAUDE
    preencher_relatorio_resumo_total(relatorio, total_geral_saude, somatorio_saude_unicos_1_sem, somatorio_saude_unicos_2_sem, somatorio_saude_unicos)
    relatorios.append(relatorio)

    agrupador = RelatorioGestaoResumo.ALUNOS_ASSISTIDOS
    relatorio = RelatorioGestaoResumo()
    relatorio.relatorio = rel
    relatorio.agrupador = agrupador
    relatorio.tipo = RelatorioGestaoResumo.TOTAL
    preencher_relatorio_resumo_total(relatorio, total_geral_mes, total_geral_1_sem, total_geral_2_sem, total_geral)
    relatorios.append(relatorio)

    RelatorioGestaoResumo.objects.bulk_create(relatorios)

    return total_geral


def obter_dados_resumo(rel):
    relatorios = rel.relatoriogestaoresumo_set.all()
    for relatorio in relatorios:
        if relatorio.tipo == RelatorioGestaoResumo.ATENDIMENTOS:
            dados_resumo_atendimentos = obter_dados_valores_resumo(relatorio)
        elif relatorio.tipo == RelatorioGestaoResumo.AUXILIOS:
            dados_resumo_auxilios = obter_dados_valores_resumo(relatorio)
        elif relatorio.tipo == RelatorioGestaoResumo.BOLSAS:
            dados_resumo_bolsas = obter_dados_valores_resumo(relatorio)
        elif relatorio.tipo == RelatorioGestaoResumo.PARTICIPANTES_PROGRAMAS:
            dados_resumo_programas = obter_dados_valores_resumo(relatorio)
        elif relatorio.tipo == RelatorioGestaoResumo.ATENDIMENTOS_SAUDE:
            dados_resumo_saude = obter_dados_valores_resumo(relatorio)
        elif relatorio.tipo == RelatorioGestaoResumo.TOTAL:
            dados_resumo_total = obter_dados_valores_resumo(relatorio)

    return dados_resumo_atendimentos, dados_resumo_auxilios, dados_resumo_bolsas, dados_resumo_programas, dados_resumo_saude, dados_resumo_total


# GRÁFICOS
def preencher_relatorio_grafico(relatorio, nome, tipo, tipo_relatorio, dados, categorias=None):
    grafico = RelatorioGrafico()
    grafico.nome = nome
    grafico.tipo = tipo
    grafico.relatorio = relatorio
    grafico.tipo_relatorio = tipo_relatorio
    grafico.save()

    dados_graficos = []
    if tipo in [RelatorioGrafico.PIE, RelatorioGrafico.BAR]:
        for label, valor in dados:
            dados = DadosRelatorioGrafico()
            dados.grafico = grafico
            dados.label = label
            dados.valor = valor
            dados_graficos.append(dados)

    elif tipo == RelatorioGrafico.GROUPEDCOLUMN:
        for label_valores in dados:
            label = label_valores[0]
            for index, valor in enumerate(label_valores[1:]):
                dados = DadosRelatorioGrafico()
                dados.grafico = grafico
                dados.categoria = categorias[index]
                dados.label = label
                dados.valor = valor or 0
                dados_graficos.append(dados)
    DadosRelatorioGrafico.objects.bulk_create(dados_graficos)


def obter_relatorio_grafico(relatorio, nome, tipo, tipo_relatorio):
    grafico = relatorio.graficos.get(nome=nome, tipo=tipo, tipo_relatorio=tipo_relatorio)
    return grafico.get_dados()
