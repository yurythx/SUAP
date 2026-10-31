"""Smoke das rotas da atividade em grupo do Saúde.

Separadas do `test_99_rotas.py` porque o alvo vem do `test_11`, que não depende da cadeia do
prontuário: é o que deixa a suíte `saude-2` (`DIVISOES_E2E` no `suap_check`) rodar sozinha, num
banco novo.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ROTAS_DA_ATIVIDADE = [
    '/saude/atividade_em_grupo/{atividade}/',
    '/saude/visualizar_acao_educativa/{atividade}/',
]


def test_rotas_da_atividade_em_grupo_abrem(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador sistêmico abre a atividade em grupo e a ação educativa criadas no `test_11`."""
    from saude.models import AtividadeGrupo

    atividade = AtividadeGrupo.objects.order_by('-id').first()
    assert atividade is not None, 'nenhuma atividade em grupo: rode junto do `test_11_atividade_grupo.py`'
    tela = Tela(logado_saude('coordenador_sistemico'))

    for rota in ROTAS_DA_ATIVIDADE:
        url = rota.format(atividade=atividade.pk)
        assert tela.buscar(url).status == 200, url
