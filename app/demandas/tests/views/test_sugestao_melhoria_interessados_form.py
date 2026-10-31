"""Issue #17175: o requisitante não deve aparecer entre as sugestões do
autocomplete de 'Interessados'/'Outros Interessados' — ele já sabe que é o
requisitante (há inclusive um help_text avisando isso), então adicioná-lo a si
mesmo como interessado é redundante e confuso.
"""

from types import SimpleNamespace

import pytest

from comum.tests.factories import UserFactory
from demandas.forms import SugestaoMelhoriaAddForm, SugestaoMelhoriaEdicaoBasicaForm, SugestaoMelhoriaEdicaoCompletaForm
from demandas.tests.factories import AreaAtuacaoDemandaFactory, SugestaoMelhoriaFactory, TagFactory
from djtools.middleware import threadlocals


@pytest.fixture(autouse=True)
def usuario_logado_threadlocal(requisitante):
    """SugestaoMelhoria.save() grava o histórico de situação com `tl.get_user()`."""
    threadlocals.context.user = requisitante
    yield
    threadlocals.context.user = None


@pytest.fixture
def area_demanda(db):
    return AreaAtuacaoDemandaFactory(demandante_responsavel=UserFactory())


@pytest.fixture
def requisitante(db):
    return UserFactory()


@pytest.mark.django_db
def test_add_form_exclui_requisitante_das_opcoes_de_interessados(area_demanda, requisitante):
    tag = TagFactory(nome='Módulo de Teste')
    area_demanda.tags_relacionadas.add(tag)

    form = SugestaoMelhoriaAddForm(area_atuacao=area_demanda, tags=[tag], user_requisitante=requisitante)

    assert requisitante not in form.fields['interessados'].queryset


@pytest.mark.django_db
def test_edicao_basica_exclui_requisitante_quando_ele_edita_a_propria_sugestao(area_demanda, requisitante):
    sugestao = SugestaoMelhoriaFactory(area_atuacao=area_demanda, requisitante=requisitante, titulo='Teste')

    form = SugestaoMelhoriaEdicaoBasicaForm(instance=sugestao, request=SimpleNamespace(user=requisitante))

    assert requisitante not in form.fields['interessados'].queryset
    assert 'não precisa se colocar como Interessado' in form.fields['interessados'].help_text


@pytest.mark.django_db
def test_edicao_basica_nao_exclui_ninguem_quando_editor_nao_e_requisitante(area_demanda, requisitante):
    outro_usuario = UserFactory()
    sugestao = SugestaoMelhoriaFactory(area_atuacao=area_demanda, requisitante=requisitante, titulo='Teste')

    form = SugestaoMelhoriaEdicaoBasicaForm(instance=sugestao, request=SimpleNamespace(user=outro_usuario))

    assert requisitante in form.fields['interessados'].queryset


@pytest.mark.django_db
def test_edicao_completa_exclui_requisitante_quando_ele_edita_a_propria_sugestao(area_demanda, requisitante):
    tag = TagFactory(nome='Módulo de Teste Completo')
    area_demanda.tags_relacionadas.add(tag)
    sugestao = SugestaoMelhoriaFactory(area_atuacao=area_demanda, requisitante=requisitante, titulo='Teste')
    sugestao.tags.add(tag)

    form = SugestaoMelhoriaEdicaoCompletaForm(instance=sugestao, request=SimpleNamespace(user=requisitante))

    assert requisitante not in form.fields['interessados'].queryset
