from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from avaliacao_integrada.tests.factories import RespondenteFactory
from comum.tests.factories import AnoFactory
from edu.tests.factories import AlunoFactory, CursoCampusFactory, FormaIngressoFactory, ModalidadeFactory


@pytest.mark.django_db
def test_respondente_get_aluno_retorna_aluno_via_usuario() -> None:
    aluno = AlunoFactory()
    respondente = RespondenteFactory(user=aluno.get_user())

    assert respondente._get_aluno() == aluno


@pytest.mark.django_db
def test_respondente_get_aluno_fallback_profile_quando_nao_marcado_como_aluno() -> None:
    aluno = AlunoFactory()
    user = aluno.get_user()
    get_user_model().objects.filter(pk=user.pk).update(eh_aluno=False)
    user.refresh_from_db()
    respondente = RespondenteFactory(user=user)

    assert respondente._get_aluno() == aluno


@pytest.mark.django_db
def test_respondente_metodos_autocalculados_de_aluno() -> None:
    modalidade = ModalidadeFactory(descricao='Técnico Integrado')
    curso_campus = CursoCampusFactory(modalidade=modalidade, descricao_historico='Informática')
    forma_ingresso = FormaIngressoFactory(descricao='Processo Seletivo')
    ano_letivo = AnoFactory(ano=2026)
    aluno = AlunoFactory(
        curso_campus=curso_campus,
        forma_ingresso=forma_ingresso,
        ano_letivo=ano_letivo,
        periodo_atual=1,
    )
    respondente = RespondenteFactory(user=aluno.get_user())

    assert respondente.get_modalidade_vinculacao() == 'Técnico Integrado'
    assert respondente.get_curso_vinculacao() == 'Informática'
    assert respondente.get_ano_ingresso_curso() == 2026
    assert respondente.get_forma_ingresso_curso() == 'Processo Seletivo'
    assert respondente.get_serie_periodo_curso() == 1
