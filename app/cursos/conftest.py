from decimal import Decimal
from types import SimpleNamespace

import pytest

from comum.models import Ano

# `sync_permissions` vem do plugin global (`pytest_plugins` no conftest raiz); não a
# importamos aqui para poder usá-la como parâmetro de fixture.
from cursos.enums import SituacaoParticipante, TipoCurso
from cursos.models import Atividade, Curso, Participante
from rh.tests.factories import ServidorFactory, SetorFactory


# --- Fixtures de fluxo (GECC) ------------------------------------------------
# Montam o estado mínimo de cada etapa por ORM. Os fluxos (iniciar/finalizar
# curso, deferir/indeferir participante) são exercitados pelos métodos de
# domínio nos testes — não pelo HTTP/templates.


@pytest.fixture
def ano(db):
    return Ano.objects.get_or_create(ano=2013)[0]


@pytest.fixture
def atividade(db):
    return Atividade.objects.create(descricao='Atividade A', valor_hora=Decimal('50.00'))


@pytest.fixture
def campus(db):
    """Campus do curso — o `SetorFactory` já cria a `UnidadeOrganizacional` do setor."""
    return SetorFactory().uo


@pytest.fixture
def servidor(db, sync_permissions):
    """Quem participa do curso."""
    return ServidorFactory()


@pytest.fixture
def aprovador(db, sync_permissions):
    """Quem defere ou indefere a participação — outra pessoa, necessariamente."""
    return ServidorFactory()


@pytest.fixture
def curso(ano, campus):
    """Curso recém-criado (nasce NAO_INICIADO)."""
    # Curso.save() é sobrescrito sem aceitar kwargs do Django, então não dá para usar objects.create().
    curso = Curso(
        descricao='Reciclagem',
        ano_pagamento=ano,
        campus=campus,
        tipo=TipoCurso.CURSO,
    )
    curso.save()
    return curso


@pytest.fixture
def adicionar_participante(atividade):
    """Factory: inscreve um servidor num curso (nasce AGUARDANDO_LIBERACAO)."""

    def _adicionar(curso, servidor, *, horas_prevista=40.0, situacao=SituacaoParticipante.AGUARDANDO_LIBERACAO, horas_trabalhada=None):
        return Participante.objects.create(
            curso=curso,
            servidor=servidor,
            atividade=atividade,
            horas_prevista=horas_prevista,
            situacao=situacao,
            horas_trabalhada=horas_trabalhada,
        )

    return _adicionar


@pytest.fixture
def curso_iniciado(curso, servidor, aprovador, adicionar_participante):
    """Curso já INICIADO, com um participante deferido (pré-condição da finalização)."""
    participante = adicionar_participante(curso, servidor)
    participante.deferir_participacao(aprovador)
    curso.iniciar()
    return SimpleNamespace(curso=curso, participante=participante)
