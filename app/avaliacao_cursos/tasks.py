from avaliacao_cursos.models import Segmento
from djtools.assincrono import task
from djtools.utils import CsvResponse, XlsResponse
from edu.models import Aluno, Matriz


@task('Exportar respostas da avaliação de cursos para XLS')
def xls_avaliacao(respostas, segmento_id, matriz_id, task=None):
    rows = [['Avaliação', 'Grupo', 'Segmento', 'Campus', 'Matriz', 'Modalidade', 'Pergunta', 'Resposta']]
    for resposta in task.iterate(respostas):
        modalidade = '-'
        matriz = '-'
        if segmento_id == Segmento.ALUNO:
            aluno = Aluno.objects.filter(id=resposta.respondente.vinculo.id_relacionamento).first()
            if aluno:
                modalidade = aluno.curso_campus.modalidade.descricao
                matriz = aluno.matriz
        else:
            matriz = matriz_id and Matriz.objects.filter(id=matriz_id).first() or '-'

        row = [
            resposta.pergunta.grupo_pergunta.questionario.avaliacao.descricao,
            resposta.pergunta.grupo_pergunta.descricao,
            resposta.respondente.segmento.descricao,
            resposta.respondente.setor.uo.sigla,
            matriz,
            modalidade,
            resposta.pergunta.enunciado,
            resposta.resposta,
        ]
        rows.append(row)
    if len(rows) >= 65536:
        return CsvResponse(rows, processo=task)
    else:
        return XlsResponse(rows, processo=task)
