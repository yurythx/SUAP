from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse


@task('Exportar Folha de Pagamento para XLS')
def folha_pagamento_to_xls(
    lista, ver_nome, ver_matricula, ver_cpf, ver_banco, ver_agencia, ver_operacao, ver_conta, ver_valor_pagar, total, task=None
):
    colunas = []
    rows = []
    conta_atributos = 0
    colunas.append('#')
    if ver_nome:
        colunas.append('Nome')
        conta_atributos += 1
    if ver_matricula:
        colunas.append('Matrícula')
        conta_atributos += 1
    if ver_cpf:
        colunas.append('CPF')
        conta_atributos += 1
    if ver_banco:
        colunas.append('Banco')
        conta_atributos += 1
    if ver_agencia:
        colunas.append('Agência')
        conta_atributos += 1
    if ver_operacao:
        colunas.append('Operação')
        conta_atributos += 1
    if ver_conta:
        colunas.append('Conta')
        conta_atributos += 1
    if ver_valor_pagar:
        colunas.append('Valor a Pagar')
        conta_atributos += 1
    rows.append(colunas)

    contador = 1
    for participante, valor in task.iterate(lista):
        row = [contador]
        if ver_nome:
            row.append(format_(participante.aluno.pessoa_fisica.nome))
        if ver_matricula:
            row.append(format_(participante.aluno.matricula))
        if ver_cpf:
            row.append(format_(participante.get_inscricao_aluno().cpf))
        if ver_banco:
            texto = format_(participante.get_inscricao_aluno().banco)
            row.append(texto)
        if ver_agencia:
            texto = format_(participante.get_inscricao_aluno().numero_agencia)
            row.append(texto)
        if ver_operacao:
            texto = format_(participante.get_inscricao_aluno().operacao)
            row.append(texto)
        if ver_conta:
            texto = f'{participante.get_inscricao_aluno().numero_conta} ({participante.get_inscricao_aluno().tipo_conta})'
            row.append(texto)
        if ver_valor_pagar:
            row.append(format_(valor))

        rows.append(row)
        contador += 1

    if ver_valor_pagar:
        row = ['Total']
        item = 1
        while item < conta_atributos:
            row.append('')
            item += 1
        row.append(format_(total))
        rows.append(row)

    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Rendimento de Frequência para XLS')
def relatorio_rendimento_frequencia_xls(matriculas, inscricao, data_inicio, data_fim, task=None):
    rows = [
        [
            '#',
            'Nome do Aluno',
            'Curso',
            'Programas que participa',
            'Rendimento Acadêmico',
            'Frequência Escolar',
            'IRA por Curso',
            'Medidas Disciplinares / Premiações',
            'Atividades Complementares',
        ]
    ]

    contador = 0
    for matricula in task.iterate(matriculas):
        contador += 1
        texto = ''
        for registro in inscricao.filter(aluno=matricula.aluno):
            data = '-'
            if registro.termo_compromisso_assinado_em:
                data = registro.termo_compromisso_assinado_em.strftime('%d/%m/%Y')
            texto = texto + f'{registro.__str__()} (Entrada em: {data}), '
        texto = texto[:-2]
        row = [
            contador,
            format_(matricula.aluno.pessoa_fisica.nome),
            format_(matricula.aluno.curso_campus),
            format_(texto),
            format_(matricula.aluno.get_ira()),
            format_(f'{matricula.get_percentual_carga_horaria_frequentada()}%'),
            format_(matricula.aluno.get_ira_curso_aluno()),
            format_(matricula.aluno.get_total_medidas_disciplinares_premiacoes(data_inicio, data_fim)),
            format_(matricula.aluno.get_total_atividades_complementares(data_inicio, data_fim)),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)
