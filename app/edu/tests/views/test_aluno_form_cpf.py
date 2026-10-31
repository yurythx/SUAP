"""O formulário de aluno (admin, CRA e sica, que herdam do ``AlunoForm``) recusa o CPF de outra pessoa física."""

import pytest

from edu.forms.alunos import AlunoForm
from edu.models import Aluno, CursoCampus, Diretoria
from edu.tests.factories import AlunoFactory
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db
CPF = '529.982.247-25'


def _erros_do_cpf(aluno: Aluno, cpf: str) -> list[str]:
    # o clean_polo só lê a diretoria do curso: em memória, sem montar o grafo de curso/matriz
    aluno.curso_campus = CursoCampus(diretoria=Diretoria(ead=False))
    form = AlunoForm(data={'cpf': cpf}, instance=aluno)
    form.is_valid()
    return form.errors.get('cpf', [])


def test_trocar_para_o_cpf_de_outra_pessoa_e_erro_de_campo() -> None:
    PessoaFisicaFactory(cpf=CPF)
    aluno = AlunoFactory(pessoa_fisica__cpf='390.533.447-05')

    assert _erros_do_cpf(aluno, '52998224725') == ['Já existe uma pessoa física com este CPF.']


def test_salvar_sem_mudar_o_cpf_passa_mesmo_com_duplicata_legada(sem_unicidade_pessoa: None) -> None:
    PessoaFisicaFactory(cpf=CPF)
    aluno = AlunoFactory(pessoa_fisica__cpf=CPF)

    assert _erros_do_cpf(aluno, '52998224725') == []
