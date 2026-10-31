"""Importação da lista de presença com planilha de uma coluna só (#17878, Sentry SUAP-WYQ).

Quando a primeira coluna da linha estava vazia, o form lia o CPF da segunda coluna
(``row.iloc[1]``); numa planilha de uma coluna só, o índice não existe e a tela respondia 500
(``IndexError``). Agora a linha sem CPF vira erro de validação do formulário.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from eventos.models import Participante
from eventos.tests.factories import ParticipanteFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def _planilha(linhas: list[list[object]]) -> SimpleUploadedFile:
    """Planilha .xlsx sem cabeçalho; ``None`` é célula vazia."""
    buffer = io.BytesIO()
    pd.DataFrame(linhas).to_excel(buffer, header=False, index=False)
    return SimpleUploadedFile(
        'presenca.xlsx',
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@pytest.fixture
def client_superusuario(client: Client, sync_permissions) -> Client:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)
    return client


def _importar(client: Client, participante: Participante, linhas: list[list[object]]):
    url = f'/eventos/importar_lista_presenca/{participante.evento_id}/{participante.tipo_id}/'
    # O token CSRF que o navegador sempre envia: a view só liga o form quando o POST tem campo de texto.
    return client.post(url, {'csrfmiddlewaretoken': 'token', 'planilha': _planilha(linhas)})


def test_linha_sem_cpf_em_planilha_de_uma_coluna_vira_erro_de_validacao(client_superusuario: Client) -> None:
    participante = ParticipanteFactory()

    resposta = _importar(client_superusuario, participante, [[participante.cpf], [None], [participante.cpf]])

    assert resposta.status_code == 200
    assert 'sem CPF' in resposta.content.decode()
    assert not Participante.objects.get(pk=participante.pk).presenca_confirmada


def test_planilha_valida_de_uma_coluna_confirma_a_presenca(client_superusuario: Client) -> None:
    participante = ParticipanteFactory()

    resposta = _importar(client_superusuario, participante, [[participante.cpf]])

    assert resposta.status_code == 302
    assert Participante.objects.get(pk=participante.pk).presenca_confirmada


def test_cpf_na_segunda_coluna_continua_aceito_quando_a_primeira_esta_vazia(client_superusuario: Client) -> None:
    participante = ParticipanteFactory()

    resposta = _importar(client_superusuario, participante, [[None, participante.cpf]])

    assert resposta.status_code == 302
    assert Participante.objects.get(pk=participante.pk).presenca_confirmada
