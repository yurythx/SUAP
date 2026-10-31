from __future__ import annotations

from typing import TYPE_CHECKING

from djtools.assincrono import task
from djtools.utils import XlsResponse
from gestao.models import Variavel
from rh.models import UnidadeOrganizacional

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from djtools.models import Task


@task(name='Gestao >> Recuperar_valor Variavel de Gestão')
def recuperar_valor(variaveis, uos, task=None):
    task.count(variaveis, uos)
    for variavel in task.iterate(variaveis):
        Variavel.recuperar_valor(variavel.pk, 0)
        for uo in task.iterate(uos):
            Variavel.recuperar_valor(variavel.pk, uo.pk)
    task.finalize('Variáveis de Gestão calculadas com sucesso.', '')


@task('Exportar Detalhamento de Variáveis de Gestão')
def detalhar_variavel_ac_xls(qs_alunos, task=None):
    from gestao.views import get_exportacao

    rows = get_exportacao(
        qs_alunos,
        [
            'matricula',
            'pessoa_fisica.nome',
            'pessoa_fisica.cpf',
            'curso_campus',
            'curso_campus.diretoria.setor.uo.nome',
            'ano_letivo',
            'periodo_letivo',
        ],
        ['Matrícula', 'Nome', 'CPF', 'Curso', 'Campus', 'Ano Inicial', 'Período Inicial'],
        task,
    )
    return XlsResponse(rows, processo=task)


@task('Exportar Detalhamento de Variáveis de Gestão')
def detalhar_variavel_am_xls(qs_matriculas: QuerySet, task: Task | None = None) -> object:
    from gestao.views import get_exportacao_apenas_dados

    rows = get_exportacao_apenas_dados(
        qs_matriculas,
        [
            'aluno.matricula',
            'aluno.pessoa_fisica.nome',
            'aluno.pessoa_fisica.cpf',
            'aluno.curso_campus',
            'aluno.curso_campus.diretoria',
            'aluno.ano_letivo',
            'aluno.periodo_letivo',
        ],
        0,
        task=task,
    )

    # Sem matrículas não há nenhuma linha (esta exportação não tem cabeçalho) e o `XlsResponse` recusa `rows` vazio.
    if not rows:
        task.finalize('Nenhum registro para exportar.', '')
        return None

    return XlsResponse(rows, processo=task)


@task('Processar Indicadores de Gestão')
def processar_indicadores(indicadores, user, task=None):
    orgao_regulamentador = 'Outros'
    for indicador in task.iterate(indicadores):
        orgao_regulamentador = indicador.orgao_regulamentador
        indicador.get_valor_formatado(user=user)
        for uo in UnidadeOrganizacional.objects.suap().all():
            indicador.get_valor_formatado(uo, user=user)
    return task.finalize('Processamento finalizado', f'/gestao/exibir_indicadores/{orgao_regulamentador}/')
