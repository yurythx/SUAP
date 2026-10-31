"""Testes da sincronização manual de uma base com o CKAN, disparada pelo dashboard do PDA."""

import datetime
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.template.loader import get_template
from django.test import RequestFactory

from dados_abertos.models import BaseDados, PDABaseDados, PlanoDadosAbertos
from dados_abertos.views import sincronizar_base_ckan


def _aba_do_ckan() -> str:
    """Nome que o ``tabs.js`` dá à aba CKAN: ``tab<posição>`` entre os ``tab-pane`` do dashboard.

    O template vem pelo loader do Django, não por caminho relativo a ``__file__``: assim o teste
    não depende de em que pasta ele mora.
    """
    dashboard = Path(get_template('dadosabertos/dashboard.html').origin.name)
    titulos = re.findall(r'class="tab-pane[^"]*"[^>]*data-title="([^"]+)"', dashboard.read_text())
    return f'tab{titulos.index("CKAN")}'


@pytest.mark.django_db
def test_sincronizar_volta_para_a_aba_do_ckan(rf: RequestFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Depois de sincronizar, o usuário volta para a aba CKAN do dashboard.

    O ``tabs.js`` nomeia as abas sem ``data-tab`` pela posição (``tab0``, ``tab1``...), então o
    ``?tab=`` do redirect precisa acompanhar a ordem dos ``tab-pane`` no template. O caminho sem
    API configurada basta: todos os retornos da view usam o mesmo destino.
    """
    pda = PlanoDadosAbertos.objects.create(
        titulo='PDA 2026-2027',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2027, 12, 31),
    )
    base = BaseDados.objects.create(nome='contratos', titulo='Contratos')
    rel = PDABaseDados.objects.create(pda=pda, base_dados=base)

    monkeypatch.setattr(BaseDados, 'lai_liberada_para_sync', lambda self: True)
    monkeypatch.setattr('dados_abertos.views.get_ckan_service', lambda: None)
    monkeypatch.setattr('dados_abertos.views.messages', SimpleNamespace(error=lambda *args, **kwargs: None))
    request = rf.post('/')
    request.user = SimpleNamespace(is_authenticated=True, has_perm=lambda perm: True)

    resposta = sincronizar_base_ckan(request, pda.pk, rel.pk)

    assert resposta.url.endswith(f'?tab={_aba_do_ckan()}')
