from __future__ import annotations

import pytest

from edu.tests.factories import AlunoFactory, MatrizFactory
from eventos.tests.factories import DimensaoFactory, EventoFactory, ParticipanteFactory


@pytest.mark.django_db
def test_participante_get_aluno_extensao_retorna_aluno_quando_vinculo_eh_aluno() -> None:
    evento = EventoFactory()
    evento.dimensoes.add(DimensaoFactory())
    aluno = AlunoFactory(matriz=MatrizFactory(ch_atividades_extensao=15))
    participante = ParticipanteFactory(evento=evento, vinculo=aluno.get_vinculo())

    assert participante.get_aluno_extensao() == aluno


@pytest.mark.django_db
def test_participante_get_aluno_extensao_retorna_none_quando_ch_extensao_zerada() -> None:
    evento = EventoFactory()
    evento.dimensoes.add(DimensaoFactory())
    aluno = AlunoFactory(matriz=MatrizFactory(ch_atividades_extensao=0))
    participante = ParticipanteFactory(evento=evento, vinculo=aluno.get_vinculo())

    assert participante.get_aluno_extensao() is None


@pytest.mark.django_db
def test_participante_get_aluno_extensao_usa_cpf_quando_sem_vinculo() -> None:
    evento = EventoFactory()
    evento.dimensoes.add(DimensaoFactory())
    aluno = AlunoFactory(matriz=MatrizFactory(ch_atividades_extensao=15))
    participante = ParticipanteFactory(evento=evento, vinculo=None, cpf=aluno.pessoa_fisica.cpf)

    assert participante.get_aluno_extensao() == aluno


@pytest.mark.django_db
def test_participante_get_aluno_extensao_retorna_none_quando_evento_sem_dimensao_extensao() -> None:
    evento = EventoFactory()
    aluno = AlunoFactory(matriz=MatrizFactory(ch_atividades_extensao=15))
    participante = ParticipanteFactory(evento=evento, vinculo=aluno.get_vinculo())

    assert participante.get_aluno_extensao() is None
