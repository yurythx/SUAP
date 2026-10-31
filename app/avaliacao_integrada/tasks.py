import tempfile

import xlsxwriter
from django.core.exceptions import PermissionDenied

from avaliacao_integrada.models import Indicador, Segmento
from djtools.assincrono import task
from djtools.crosstab.exporters import XLSXCrosstabExporter
from djtools.utils import httprr
from edu.models import Modalidade


@task('Relatório em XLSX')
def relatorio_xlsx(respostas, task=None):
    response = tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False)
    workbook = xlsxwriter.Workbook(response)
    worksheet = workbook.add_worksheet('relatorio')

    header = [
        '#',
        'Indicador',
        'Subsídio p/ Avaliações',
        'Modalidade',
        'ID Respondente',
        'Eixo',
        'Dimensão',
        'Macroprocesso',
        'Segmento',
        'Campus',
        'Curso',
        'Resposta',
    ]
    rows = [header]
    idx = 0
    for obj in task.iterate(respostas.order_by('indicador', 'respondente')):
        row = [idx + 1]
        row.append(str(obj.indicador.aspecto))
        row.append(','.join(obj.indicador.subsidio_para.all().values_list('descricao', flat=True)))
        row.append(str(obj.objeto) if isinstance(obj.objeto, Modalidade) else '-')
        row.append(str(obj.respondente_id))
        row.append(str(obj.indicador.macroprocesso.dimensao.eixo))
        row.append(str(obj.indicador.macroprocesso.dimensao))
        row.append(str(obj.indicador.macroprocesso))
        row.append(str(obj.respondente.segmento))
        if obj.respondente.segmento_id == Segmento.ESTUDANTE:
            row.append(str(obj.respondente.get_unidade_diretoria_aluno()))
        if obj.respondente.segmento_id in Segmento.ALUNOS:
            row.append(str(obj.respondente.get_curso_vinculacao()))
        elif obj.respondente.segmento_id in Segmento.SERVIDORES:
            row.append(str(obj.respondente.get_unidade_atuacao_servidor()))
            row.append('-')
        else:
            row.append('-')
            row.append('-')

        if obj.indicador.tipo_resposta == Indicador.MULTIPLA_ESCOLHA:
            for valor in obj.valor.split('::'):
                if valor != '':
                    rows.append([*row, str(valor)])
        else:
            row.append(str(obj.valor))
            rows.append(row)
        idx += 1

    for row_idx, row_data in enumerate(rows):
        for col_idx, col in enumerate(row_data):
            worksheet.write(row_idx, col_idx, col)

    workbook.close()
    response.close()
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=response.name)


@task('Reprocessar público alvo')
def reprocessar_publico_alvo(user, avaliacao, excluir, task=None):
    if not avaliacao.pode_gerar_publico_alvo(user):
        raise PermissionDenied

    avaliacao.gerar_respondentes(excluir=excluir, task=task)
    msm = 'Público-Alvo reprocessado com sucesso.'
    url = f'/avaliacao_integrada/avaliacao/{avaliacao.pk}/'
    if task:
        return task.finalize(msm, url)
    else:
        return httprr(url, msm)


# Usa thread para evitar serialização de objetos complexos (TabelaBidimensional)
# na fila assíncrona via celery.
@task('Relatório crosstab em XLSX', method='thread')
def exportar_crosstab_xlsx(tabelas, task=None):
    """
    Recebe uma sequência de TabelaBidimensional e devolve um arquivo XLSX
    com uma guia por tabela.
    """
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', mode='w+b', delete=False)
    try:
        exporter = XLSXCrosstabExporter(tabelas)
        exporter.write(tmp)  # grava no arquivo temporário
        tmp.flush()
    finally:
        tmp.close()

    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)
