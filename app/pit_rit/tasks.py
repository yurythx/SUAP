from djtools.assincrono import task
from djtools.utils import XlsResponse
from rh.models import Servidor


@task('Exportar Relatório de CH de Docente para XLS')
def exportar_relatorio_ch_docente_xls(pits, task=None):
    rows = [
        [
            'Ano',
            'Período',
            'Matrícula',
            'Nome',
            'Setor de Lotação SUAP',
            'Setor de Exercício SIAPE',
            'Setor de Lotação SIAPE',
            'Disciplina de Ingress',
            'Jornada de Trabalho',
            'CH Sala de Aula',
            'CH Tota',
            'Campus',
        ]
    ]

    for plano in task.iterate(pits):
        servidor = Servidor.objects.get(pessoa_fisica__id=plano.professor.vinculo.pessoa.id)
        rows.append(
            [
                plano.ano_letivo.ano,
                plano.periodo_letivo,
                servidor.matricula,
                servidor.pessoa_fisica.nome,
                servidor.setor and servidor.setor.sigla or '',
                servidor.setor_exercicio and servidor.setor_exercicio.sigla or '',
                servidor.setor_lotacao and servidor.setor_lotacao.sigla or '',
                servidor.disciplina_ingresso or '' or '',
                servidor.jornada_trabalho.nome,
                plano.get_ch_diarios(),
                plano.get_ch_semanal_total(),
                servidor.setor and servidor.setor.uo.sigla or '',
            ]
        )
    return XlsResponse(rows, processo=task)
