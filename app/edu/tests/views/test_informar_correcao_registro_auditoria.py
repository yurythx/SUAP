"""Correção de registro de auditoria cuja matrícula não existe no SUAP (#17435).

Os formulários de correção faziam ``Aluno.objects.get(matricula=...)`` e estouravam
``Aluno.DoesNotExist``; agora a view avisa e volta para a auditoria.
"""

from __future__ import annotations

import pytest
from django.test import Client

from edu.models import RegistroAuditoriaEnsino
from edu.tests.factories import RegistroAuditoriaEnsinoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_matricula_inexistente_volta_para_a_auditoria(client: Client, sync_permissions) -> None:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    registro = RegistroAuditoriaEnsinoFactory()
    client.force_login(user)

    resposta = client.get(f'/edu/informar_correcao_registro_auditoria/{registro.pk}/')

    assert resposta.status_code == 302
    assert RegistroAuditoriaEnsino.objects.get(pk=registro.pk).situacao is None
