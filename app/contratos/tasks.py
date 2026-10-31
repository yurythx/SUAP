from django.conf import settings

from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse, anonimizar_cpf
from suap import nomenclatura


@task('Exportar Fiscais para XLS')
def exportar_fiscais_para_xls(fiscais, task=None):
    def formata_booleano(valor):
        return valor and 'Sim' or 'Não'

    rows = [['#', 'Nome', 'Matrícula', 'Email', nomenclatura.campus, 'Tipo', 'Categoria', 'Contrato Ativo', 'Quantidade']]
    contador = 0
    for item in task.iterate(fiscais):
        contador += 1
        row = [
            contador,
            format_(item['nome']),
            format_(item['matricula']),
            format_(item['email']),
            format_(item['campus']),
            format_(item['tipo']),
            format_(item['categoria']),
            format_(formata_booleano(item['contrato_ativo'])),
            format_(item['quantidade']),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Resultado da Busca por Contratos para XLS')
def buscar_contrato_export_to_xls(contratos, task=None):
    rows = [['#', 'Número', 'Contratada', 'Período de Vigência', 'Termos Aditivos']]

    contador = 0
    for contrato in task.iterate(contratos):
        contador += 1
        if contrato.data_vencimento != contrato.data_fim:
            data_fim = f'Prorrogado de {format_(contrato.data_fim)} para {format_(contrato.data_vencimento)}'
        else:
            data_fim = f'{format_(contrato.data_fim)}'
        vigencia = f'Início: {format_(contrato.data_inicio)}, Vencimento: {format_(data_fim)}'
        aditivos = ''
        for aditivo in contrato.aditivos.all():
            aditivos = aditivos + f'{aditivo}, '

        row = [contador, format_(contrato.numero), format_(contrato.vinculo_contratado), format_(vigencia), format_(aditivos[:-2])]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Contratos para XLS')
def exportar_contratos_xls(contratos, quadro_publicacao, quadro_cronograma, quadro_empenhos, quadro_terceirizados, task=None):
    def p(valor):
        if type(valor) is bool:
            return valor and 'Sim' or 'Não'
        return valor and valor or ''

    rows = [
        [
            'Número',
            'Tipo',
            'Subtipo',
            'Valor do Contrato',
            'Valor Executado',
            'Valor Total',
            'Início',
            'Final',
            'Vencimento',
            'Objeto',
            f'{nomenclatura.campus} Gerenciador',
            'Setores Gerenciadores',
            'Continuidade',
            'Processo',
            'Contratada',
            'Qtd Parcelas',
            'Tipo de Licitação',
            'Pregão',
            'Estimativa de Início',
            'Concluido?',
            'Motivo de Conclusão',
            'Cancelado',
            'Motivo do Cancelamento',
            'Data/Hora Cancelamento',
            'Numero Processo',
            'Números de Empenhos',
        ]
    ]

    for c in contratos:
        row = []
        row.append(f'{p(c.numero)}')
        row.append(f'{p(c.tipo)}')
        row.append(f'{p(c.subtipo)}')
        row.append(f'{p(c.valor)}')
        row.append(f'{p(c.valor_executado)}')
        row.append(f'{p(c.valor_total)}')
        row.append(f'{p(c.data_inicio)}')
        row.append(f'{p(c.data_fim)}')
        row.append(f'{p(c.data_vencimento)}')
        row.append(f'{p(c.objeto)}')
        row.append(f'{p(str(c.campus_gerenciador) if c.campus_gerenciador_id else None)}')
        row.append(f'{p(", ".join([setor.sigla for setor in c.setores_gerenciadores.all()]))}')
        row.append(f'{p(c.continuidade)}')
        row.append(f'{p(c.processo.get_numero() if c.processo else None)}')
        row.append(f'{p(c.vinculo_contratado)}')
        row.append(f'{p(c.qtd_parcelas)}')
        row.append(f'{p(c.tipo_licitacao)}')
        row.append(f'{p(c.pregao)}')
        row.append(f'{p(c.estimativa_licitacao)}')
        row.append(f'{p(c.concluido)}')
        row.append(f'{p(c.motivo_conclusao)}')
        row.append(f'{p(c.cancelado)}')
        row.append(f'{p(c.motivo_cancelamento)}')
        row.append(f'{p(c.dh_cancelamento)}')
        row.append(f'{p(c.numero_processo)}')
        row.append(f'{p(c.numero_empenho)}')
        rows.append(row)

        if quadro_publicacao:
            publicacoes = c.get_publicacoes_anexo()
            if publicacoes.exists():
                row = ['', '']
                row.append('Tipo')
                row.append('Número')
                row.append('Data Publicação')
                rows.append(row)

                count = 0
                for pub in publicacoes:
                    row = ['']
                    count += 1
                    row.append(f'Publicação {count}')
                    row.append(f'{p(pub.tipo)}')
                    row.append(f'{p(pub.numero)}')
                    row.append(f'{p(pub.data)}')
                    rows.append(row)

        if quadro_empenhos:
            empenhos = c.get_empenhos()
            if empenhos.exists():
                row = ['', '']
                row.append('Número')
                row.append('Valor Total')
                row.append('Saldo')
                rows.append(row)

                count = 0
                for doc_empenho in empenhos:
                    row = ['']
                    count += 1
                    row.append(f'Empenho {count}')
                    row.append(f'{p(doc_empenho.empenho.numero)}')
                    row.append(f'{p(doc_empenho.empenho.get_valor())}')
                    row.append(f'{p(doc_empenho.empenho.get_saldo_restante())}')
                    rows.append(row)

        if quadro_terceirizados:
            terceirizados = c.maosdeobra.filter(desligamento__isnull=True)
            if terceirizados.exists():
                row = ['', '']
                row.append('Nome')
                row.append('Função')
                row.append('Salário Bruto')
                row.append('Custo Mensal')
                row.append(nomenclatura.campus)
                rows.append(row)

                count = 0
                for terceirizado in terceirizados:
                    row = ['']
                    count += 1
                    row.append(f'Terceirizado {count}')
                    row.append(f'{p(terceirizado.prestador_servico.pessoa_fisica.nome)}')
                    row.append(f'{p(terceirizado.funcao)}')
                    row.append(f'{p(terceirizado.salario_bruto)}')
                    row.append(f'{p(terceirizado.custo_mensal)}')
                    row.append(f'{p(terceirizado.campus)}')
                    rows.append(row)

        if quadro_cronograma:
            cronogramas = c.cronogramas.all().prefetch_related('parcelas')
            if cronogramas:
                row = ['', '']
                row.append('Número do Cronograma')
                row.append('Nota de Lançamento')
                row.append('Registro de Contrato')
                rows.append(row)
                for cronograma in cronogramas:
                    row = ['']
                    row.append('Cronograma')
                    row.append(f'{p(cronograma.numero)}')
                    row.append(f'{p(cronograma.nl)}')
                    row.append(f'{p(cronograma.rc)}')
                    rows.append(row)
                    parcelas = cronograma.parcelas.all()
                    if parcelas:
                        row = ['', '']
                        row.append('Início Previsto')
                        row.append('Final Previsto')
                        row.append('Valor Previsto')
                        row.append('Valor Executado')
                        row.append('Sem Medição')
                        rows.append(row)
                        for parcela in parcelas:
                            row = ['', '']
                            row.append(f'{p(parcela.data_prevista_inicio)}')
                            row.append(f'{p(parcela.data_prevista_fim)}')
                            row.append(f'{p(parcela.valor_previsto)}')
                            row.append(f'{p(parcela.valor_executado_parcela())}')
                            row.append(f'{p(parcela.sem_medicao)}')
                            rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Consumo de Energia Elétrica para XLS')
def relatorio_consumo_energia_xls(medicoes, task=None):
    rows = [['Contrato', 'Unidades', 'Ano de Referência', 'Mês de Referencia', 'Cons. Ponta (kWh)', 'Cons. Fora de Ponta (kWh)', 'Despesa (R$)']]
    for medicaoeletrica in medicoes:
        url = f'{settings.SITE_URL}{medicaoeletrica.medicao.parcela.cronograma.contrato.get_absolute_url()}'
        row = [
            url,
            medicaoeletrica.medicao.campus.nome if medicaoeletrica.medicao.campus else 'Sem informação na medição',
            medicaoeletrica.ano_referencia,
            medicaoeletrica.mes_referencia,
            medicaoeletrica.consumo_ponta or 'Não informado',
            medicaoeletrica.consumo_fora_ponta or 'Não informado',
            medicaoeletrica.medicao.valor_executado,
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Terceirizados para XLS')
def relatorio_terceirizados_xls(terceirizados, mascarar_cpfs, task=None):
    rows = [
        [
            'Código da UG - Unidade Gestora',
            'Nome da UG - Unidade Gestora',
            'Número do contrato',
            'CNPJ',
            'Razão Social da Empresa',
            'CPF',
            'Nome Completo',
            'Categoria Profissional',
            'Jornada de Trabalho (Semanal)',
            'Unidade de Prestação de Serviços',
            'Salário Mensal Bruto (R$)',
            'Custo Mensal do Terceirizado (R$)',
            'Escolaridade exigida pelo cargo',
        ]
    ]
    for terceirizado in terceirizados:
        if terceirizado.contrato.vinculo_contratado.eh_pessoajuridica():
            documento_empresa = terceirizado.contrato.vinculo_contratado.pessoa.pessoajuridica.cnpj
        else:
            documento_empresa = terceirizado.contrato.vinculo_contratado.pessoa.pessoafisica.cpf

        if mascarar_cpfs:
            cpf_terceirizado = anonimizar_cpf(terceirizado.prestador_servico.pessoa_fisica.cpf)
        else:
            cpf_terceirizado = terceirizado.prestador_servico.pessoa_fisica.cpf
        row = [
            terceirizado.contrato.campus_gerenciador.codigo_ug
            if terceirizado.contrato.campus_gerenciador
            else f'Sem informação do {nomenclatura.campus} Gerenciador',
            terceirizado.contrato.campus_gerenciador.nome
            if terceirizado.contrato.campus_gerenciador
            else f'Sem informação do {nomenclatura.campus} Gerenciador',
            terceirizado.contrato.numero,
            documento_empresa,
            terceirizado.contrato.vinculo_contratado.pessoa.nome,
            cpf_terceirizado,
            terceirizado.prestador_servico.pessoa_fisica.nome,
            terceirizado.categoria,
            terceirizado.jornada_trabalho,
            terceirizado.campus,
            terceirizado.salario_bruto,
            terceirizado.custo_mensal,
            terceirizado.escolaridade,
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)


@task('Exportar Relatório de Emepenhos para XLS')
def relatorio_empenhos_xls(contratos_com_empenho, task=None):
    rows = [
        [
            nomenclatura.campus,
            'Contrato',
            'Número do empenho',
            'CNPJ',
            'Razão Social da Empresa',
            'Valor (R$)',
            'Valor Liquidado (R$)',
            'Valor Pago (R$)',
            'Saldo restante (R$)',
        ]
    ]
    for contrato_empenho in contratos_com_empenho:
        row = [
            contrato_empenho.empenho.emitente_ug.uo,
            contrato_empenho.contrato.numero,
            contrato_empenho.empenho.numero,
            contrato_empenho.empenho.favorecido_codigo,
            contrato_empenho.empenho.favorecido_nome,
            contrato_empenho.empenho.get_valor(),
            contrato_empenho.empenho.get_valor_liquidado(),
            contrato_empenho.empenho.get_valor_pago(),
            contrato_empenho.empenho.get_saldo_restante(),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)
