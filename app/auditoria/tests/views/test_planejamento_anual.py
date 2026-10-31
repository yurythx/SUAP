"""Planejamento anual do auditor com id inexistente (#17437).

``planejamento_anual_auditor`` buscava o planejamento com ``.get(pk=...)`` e respondia 500
(``PlanejamentoAnual.DoesNotExist``) para um id que não existe; agora responde 404.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_planejamento_inexistente_responde_404(client: Client, sync_permissions) -> None:
    auditor = ServidorFactory().get_user()
    auditor.groups.add(Group.objects.get(name='Auditor'))
    client.force_login(auditor)

    resposta = client.get('/auditoria/paint/planejamento/anual/999999')

    assert resposta.status_code == 404
