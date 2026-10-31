import pytest

from edu.tests.factories import AlunoFactory
from saude.models import CartaoVacinal, Vacina

pytestmark = pytest.mark.django_db


def test_get_aluno_com_dois_alunos_na_mesma_pessoa(aluno, prontuario) -> None:
    AlunoFactory(pessoa_fisica=aluno.pessoa_fisica)  # mesma pessoa, outra matrícula
    cartao = CartaoVacinal.objects.create(prontuario=prontuario, vacina=Vacina.objects.create(nome='Hepatite B', doses=3), numero_dose=1)

    assert cartao.get_aluno() == aluno
