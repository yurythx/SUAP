"""Pacotes de fotos que o terminal baixa (``/comum/get_fotos_funcionarios/`` e ``/comum/get_fotos_alunos/``).

São webservices anônimos, autorizados pelo IP da ``ponto.Maquina`` ativa. O que se afirma aqui é
a auditoria: todo pacote servido deixa um ``MaquinaLog`` de quem baixou (#17398 — o de alunos não
deixava). O ``REMOTE_ADDR`` é explícito e fora do ``127.0.0.1``, que o e2e do ``comum`` cadastra
como máquina ativa (ver ``comum/tests/views/test_webservice.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.core.files.base import ContentFile
from django.test import Client

from djtools.storages.utils import get_temp_storage
from ponto.models import MaquinaLog
from ponto.tests.factories import MaquinaFactory
from rh.tests.factories import SetorFactory

pytestmark = pytest.mark.django_db

IP_TERMINAL = '10.99.0.31'


@pytest.mark.parametrize(
    ('rota', 'arquivo', 'operacao'),
    [
        ('/comum/get_fotos_funcionarios/', 'fotos/fotos_funcionarios.zip', 'comum_get_fotos_funcionarios'),
        ('/comum/get_fotos_alunos/', 'fotos/fotos_alunos_{sigla}.zip', 'comum_get_fotos_alunos'),
    ],
    ids=['funcionarios', 'alunos'],
)
def test_pacote_de_fotos_registra_o_acesso_da_maquina(client: Client, settings: Any, tmp_path: Path, rota: str, arquivo: str, operacao: str) -> None:
    settings.TEMP_DIR = str(tmp_path)
    uo = SetorFactory().uo
    maquina = MaquinaFactory(ip=IP_TERMINAL, cliente_refeitorio=True, uo=uo)
    get_temp_storage().save(arquivo.format(sigla=uo.sigla), ContentFile(b'zip'))

    resposta = client.get(rota, REMOTE_ADDR=IP_TERMINAL)

    assert resposta.status_code == 200
    assert MaquinaLog.objects.filter(maquina=maquina, operacao=operacao).count() == 1
