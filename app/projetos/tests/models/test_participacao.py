from __future__ import annotations

import pytest

from edu.models import SituacaoMatricula
from edu.tests.factories import AlunoFactory, MatrizFactory, SituacaoMatriculaFactory
from projetos.tests.factories import ParticipacaoFactory
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
def test_participacao_get_aluno_extensao_retorna_aluno_quando_matricula_qualificada() -> None:
    matriz = MatrizFactory(ch_atividades_extensao=10)
    aluno = AlunoFactory(matriz=matriz)
    participacao = ParticipacaoFactory(vinculo_pessoa=aluno.get_vinculo())

    assert participacao.get_aluno_extensao() == aluno


@pytest.mark.django_db
def test_participacao_get_aluno_extensao_retorna_none_quando_ch_extensao_zerada() -> None:
    matriz = MatrizFactory(ch_atividades_extensao=0)
    aluno = AlunoFactory(matriz=matriz)
    participacao = ParticipacaoFactory(vinculo_pessoa=aluno.get_vinculo())

    assert participacao.get_aluno_extensao() is None


@pytest.mark.django_db
def test_participacao_get_aluno_extensao_retorna_none_quando_matricula_inativa() -> None:
    situacao_concluido = SituacaoMatriculaFactory(id=SituacaoMatricula.CONCLUIDO, descricao='Concluído', ativo=False)
    aluno = AlunoFactory(matriz=MatrizFactory(ch_atividades_extensao=10), situacao=situacao_concluido)
    participacao = ParticipacaoFactory(vinculo_pessoa=aluno.get_vinculo())

    assert participacao.get_aluno_extensao() is None


@pytest.mark.django_db
def test_participacao_get_aluno_extensao_retorna_none_quando_vinculo_nao_eh_aluno(sync_permissions: None) -> None:
    servidor = ServidorFactory()
    participacao = ParticipacaoFactory(vinculo_pessoa=servidor.get_vinculo())

    assert participacao.get_aluno_extensao() is None


@pytest.mark.django_db
def test_participacao_get_aluno_extensao_sem_vinculo_retorna_none() -> None:
    participacao = ParticipacaoFactory(vinculo_pessoa=None)

    assert participacao.get_aluno_extensao() is None
