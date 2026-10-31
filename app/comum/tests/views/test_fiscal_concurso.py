"""Inscrição do servidor como fiscal de concurso público (``/comum/fiscal_concurso/``).

O envio era inalcançável: a view passava ``servidor=`` ao ``InscricaoFiscalForm``, que não aceita o
argumento, e todo ``POST`` estourava ``TypeError`` (#17396). O servidor entra agora pela instância.
"""

from __future__ import annotations

import datetime

import pytest
from django.test import Client

from comum.models import InscricaoFiscal
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

ROTA = '/comum/fiscal_concurso/'


def test_servidor_se_inscreve_como_fiscal(client: Client, sync_permissions) -> None:
    servidor = ServidorFactory()
    client.force_login(servidor.get_user())

    resposta = client.post(ROTA, {'numero_filhos_menores_21_anos': '2', 'data_inicio_servico_na_instituicao': '01/03/2019'})

    assert resposta.status_code == 302
    inscricao = InscricaoFiscal.objects.get(servidor=servidor)
    assert inscricao.numero_filhos_menores_21_anos == 2
    assert inscricao.data_inicio_servico_na_instituicao == datetime.date(2019, 3, 1)


def test_data_futura_nao_grava_inscricao(client: Client, sync_permissions) -> None:
    servidor = ServidorFactory()
    client.force_login(servidor.get_user())
    amanha = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%d/%m/%Y')

    resposta = client.post(ROTA, {'numero_filhos_menores_21_anos': '0', 'data_inicio_servico_na_instituicao': amanha})

    assert resposta.status_code == 200
    assert resposta.context['form'].errors['data_inicio_servico_na_instituicao'] == ['A data deve estar no passado.']
    assert not InscricaoFiscal.objects.filter(servidor=servidor).exists()
