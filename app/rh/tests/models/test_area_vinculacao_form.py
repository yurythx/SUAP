"""Reordenação de ``AreaVinculacaoForm.save`` ao adicionar ou mover uma área (#17650)."""

from __future__ import annotations

import pytest

from rh.forms import AreaVinculacaoForm
from rh.models import AreaVinculacao
from rh.tests.factories import AreaVinculacaoFactory

pytestmark = pytest.mark.django_db


def _descricoes() -> list[str]:
    return list(AreaVinculacao.objects.order_by('ordem').values_list('descricao', flat=True))


def _ordens() -> list[int]:
    return list(AreaVinculacao.objects.order_by('ordem').values_list('ordem', flat=True))


def _salvar(descricao: str, ordem: int, instance: AreaVinculacao | None = None) -> AreaVinculacao:
    form = AreaVinculacaoForm({'descricao': descricao, 'ordem': str(ordem)}, instance=instance)
    assert form.is_valid(), form.errors
    return form.save()


def _criar_tres() -> list[AreaVinculacao]:
    return [AreaVinculacaoFactory(descricao=nome, ordem=ordem) for ordem, nome in enumerate('ABC', start=1)]


@pytest.mark.parametrize(
    ('ordem', 'esperado'),
    [(1, ['N', 'A', 'B', 'C']), (2, ['A', 'N', 'B', 'C']), (3, ['A', 'B', 'N', 'C']), (4, ['A', 'B', 'C', 'N'])],
)
def test_adicionar_area_em_qualquer_ordem_reordena_as_demais(ordem: int, esperado: list[str]) -> None:
    _criar_tres()

    _salvar('N', ordem)

    assert _descricoes() == esperado
    assert _ordens() == [1, 2, 3, 4]


@pytest.mark.parametrize(
    ('indice', 'ordem', 'esperado'),
    [(2, 1, ['C', 'A', 'B']), (0, 3, ['B', 'C', 'A']), (0, 2, ['B', 'A', 'C']), (1, 1, ['B', 'A', 'C'])],
)
def test_mover_area_existente_reordena_as_demais(indice: int, ordem: int, esperado: list[str]) -> None:
    area = _criar_tres()[indice]

    _salvar(area.descricao, ordem, instance=area)

    assert _descricoes() == esperado
    assert _ordens() == [1, 2, 3]
