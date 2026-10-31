from behave import given

from comum.models import Ano
from edu.models import Aluno, MatriculaPeriodo, SituacaoMatriculaPeriodo


@given('os dados basicos cadastrados da pedagogia')
def step_atual_pagina(context):
    aluno = Aluno.objects.get(matricula='20191101011031')
    MatriculaPeriodo.objects.get_or_create(
        aluno=aluno,
        ano_letivo=Ano.objects.get_or_create(ano=2019)[0],
        periodo_letivo=1,
        periodo_matriz=1,
        situacao=SituacaoMatriculaPeriodo.objects.get_or_create(id=SituacaoMatriculaPeriodo.MATRICULADO, descricao='Matriculado')[0],
    )
