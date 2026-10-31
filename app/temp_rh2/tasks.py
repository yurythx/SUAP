from djtools.assincrono import task
from djtools.templatetags.filters import format_
from djtools.utils import XlsResponse
from temp_rh2.models import ModalidadeDesportiva, Prova


@task('Exportar relatório inscritos por modalidades e provas')
def exportar_relatorio_inscritos_por_modalidades_provas_xls(inscritos, modalidades=None, task=None):
    rows = [
        [
            '#',
            'Modalidade',
            'Prova',
            'Inscrito',
            'Matricula',
            'Campus Inscrito',
            'Campus do Servidor(Lotação)',
            'Campus do Servidor(Exercício)',
            'Categoria',
            'Situação',
        ]
    ]

    count = 0
    for inscricao in task.iterate(inscritos):
        for prova in inscricao.get_todas_provas_modalidades(modalidades):
            if isinstance(prova, Prova):
                modalidade = prova.modalidade
                nome_prova = prova
            elif isinstance(prova, ModalidadeDesportiva):
                modalidade = prova
                nome_prova = ''
            uo_lotacao = inscricao.servidor.setor_lotacao and inscricao.servidor.setor_lotacao.uo.equivalente or None
            row = [
                count,
                format_(modalidade),
                nome_prova,
                format_(inscricao.servidor.pessoa_fisica.nome),
                format_(inscricao.servidor.matricula),
                format_(inscricao.uo),
                format_(uo_lotacao),
                format_(inscricao.servidor.campus),
                format_(inscricao.categoria),
                format_(inscricao.get_situacao_display()),
            ]
            rows.append(row)
            count += 1
    return XlsResponse(rows, processo=task)
