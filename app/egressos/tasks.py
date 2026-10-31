from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse


@task('Exportar Lista de Alunos da Pesquisa de Egressos')
def relatorio_planilha_alunos_alvo_xls(pesquisa, task=None):
    rows = [['#', 'Matrícula', 'Nome', 'Curso', 'Diretoria', 'Campus', 'Situação', 'E-mail']]
    count = 0
    queryset = pesquisa.get_alunos_alvo()
    for aluno in task.iterate(queryset):
        count += 1
        row = [
            count,
            format_(aluno.matricula),
            format_(aluno.pessoa_fisica.nome),
            format_(aluno.curso_campus),
            format_(aluno.curso_campus.diretoria),
            format_(aluno.curso_campus.diretoria.setor.uo),
            format_(aluno.situacao),
            format_(aluno.email_notificacao),
        ]
        rows.append(row)
    return XlsResponse(rows, processo=task)
