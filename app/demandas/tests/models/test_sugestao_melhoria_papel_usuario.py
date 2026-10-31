"""Issue #17175: o "alerta" de pendências do dashboard ("N Sugestões de melhoria
a avaliar", em `demandas/views.py`) e o tab `tab_como_demandante` do admin usam
`SugestaoMelhoria.sugestoes_por_papel_usuario(user_demandante=...)`. Quando o
demandante é também o requisitante de uma sugestão, ela não deveria aparecer
nessa lista — o demandante não avalia a própria sugestão.
"""

import pytest

from comum.tests.factories import UserFactory
from demandas.models import SugestaoMelhoria
from demandas.tests.factories import AreaAtuacaoDemandaFactory, SugestaoMelhoriaFactory
from djtools.middleware import threadlocals


@pytest.fixture
def requisitante(db):
    return UserFactory()


@pytest.fixture(autouse=True)
def usuario_logado_threadlocal(requisitante):
    """SugestaoMelhoria.save() grava o histórico de situação com `tl.get_user()`."""
    threadlocals.context.user = requisitante
    yield
    threadlocals.context.user = None


@pytest.fixture
def area_demanda(requisitante):
    area_demanda = AreaAtuacaoDemandaFactory()
    area_demanda.demandantes.add(requisitante)
    return area_demanda


@pytest.mark.django_db
def test_demandante_nao_ve_a_propria_sugestao_como_pendente_de_avaliacao(area_demanda, requisitante):
    SugestaoMelhoriaFactory(area_atuacao=area_demanda, requisitante=requisitante, titulo='Minha própria sugestão')

    sugestoes = SugestaoMelhoria.sugestoes_por_papel_usuario(user_demandante=requisitante)

    assert not sugestoes.exists()


@pytest.mark.django_db
def test_demandante_ve_sugestao_de_outro_requisitante(area_demanda, requisitante):
    outro_usuario = UserFactory()
    sugestao = SugestaoMelhoriaFactory(area_atuacao=area_demanda, requisitante=outro_usuario, titulo='Sugestão de outro')

    sugestoes = SugestaoMelhoria.sugestoes_por_papel_usuario(user_demandante=requisitante)

    assert list(sugestoes) == [sugestao]


@pytest.mark.django_db
def test_demandante_responsavel_nao_ve_a_propria_sugestao(requisitante):
    area_demanda_resp = AreaAtuacaoDemandaFactory()
    area_demanda_resp.demandante_responsavel = requisitante
    area_demanda_resp.save()

    SugestaoMelhoriaFactory(area_atuacao=area_demanda_resp, requisitante=requisitante, titulo='Minha sugestão')

    sugestoes = SugestaoMelhoria.sugestoes_por_papel_usuario(user_demandante=requisitante)

    assert not sugestoes.exists()
