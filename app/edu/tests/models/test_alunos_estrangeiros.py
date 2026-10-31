import pytest

from edu.models.alunos import Aluno
from edu.tests.factories import AlunoFactory
from rh.tests.factories import PessoaFisicaFactory


@pytest.mark.parametrize(
    ('nacionalidade', 'passaporte', 'esperado'),
    [
        ('Estrangeira', 'AB123456', True),
        ('Estrangeira', '', False),
        ('Brasileira', 'AB123456', False),
    ],
)
def test_eh_estrangeiro_com_passaporte(nacionalidade: str, passaporte: str, esperado: bool) -> None:
    aluno = Aluno(nacionalidade=nacionalidade, passaporte=passaporte)

    assert aluno.eh_estrangeiro_com_passaporte() is esperado


def test_dados_sincronizacao_usuario_estrangeiro_mantem_acesso_local() -> None:
    aluno = Aluno(nacionalidade='Estrangeira', passaporte='AB123456')

    assert aluno.get_dados_sincronizacao_usuario() == {
        'eh_aluno': True,
        'eh_estrangeiro': True,
        'is_active': True,
        'is_staff': True,
    }


def test_dados_sincronizacao_usuario_brasileiro_nao_altera_acesso() -> None:
    aluno = Aluno(nacionalidade='Brasileira', passaporte='')

    assert aluno.get_dados_sincronizacao_usuario() == {'eh_aluno': True, 'eh_estrangeiro': False}


@pytest.mark.django_db
def test_aluno_nao_sobrescreve_passaporte_da_pessoa_compartilhada() -> None:
    pessoa = PessoaFisicaFactory(passaporte='AB123456')
    AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Estrangeira', passaporte='AB123456')

    AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Estrangeira', passaporte='ZZ999999')

    pessoa.refresh_from_db()
    assert pessoa.passaporte == 'AB123456'


@pytest.mark.django_db
def test_aluno_nao_devolve_passaporte_anulado_a_pessoa() -> None:
    # a higiene da deduplicação anula o passaporte da PF de propósito (inválido ou resíduo de mesclagem)
    pessoa = PessoaFisicaFactory(passaporte=None)

    AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Estrangeira', passaporte='ZZ999999')

    pessoa.refresh_from_db()
    assert pessoa.passaporte is None
    assert pessoa.eh_estrangeiro is True


@pytest.mark.django_db
def test_aluno_brasileiro_nao_desmarca_pessoa_estrangeira() -> None:
    pessoa = PessoaFisicaFactory(passaporte='AB123456')
    AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Estrangeira', passaporte='AB123456')

    AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Brasileira', passaporte='')

    pessoa.refresh_from_db()
    assert pessoa.eh_estrangeiro is True
