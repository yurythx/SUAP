"""Testes do endpoint público de contratos dos dados abertos."""

from datetime import date
from decimal import Decimal

import pytest

from comum.tests.factories import PrestadorServicoFactory
from contratos.models import Contrato, TipoContrato
from rh.tests.factories import PessoaJuridicaFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_contratos_publica_cnpj_e_razao_social_da_contratada(client):
    empresa = PessoaJuridicaFactory()
    prestador = PrestadorServicoFactory()
    tipo = TipoContrato.objects.create(descricao='Serviço')
    for numero, vinculo in (('00001/2024', empresa.get_vinculo()), ('00002/2024', prestador.get_vinculo())):
        Contrato.objects.create(
            numero=numero,
            tipo=tipo,
            valor=Decimal('1000.00'),
            data_inicio=date(2024, 1, 1),
            objeto='Manutenção',
            vinculo_contratado=vinculo,
        )

    resposta = client.get('/dados_abertos/api/contrato/contratos/', {'ano': 2024})

    assert resposta.status_code == 200
    contratadas = {c['numero']: (c['cnpj_contrata'], c['razao_social_contrata']) for c in resposta.json()['results']}
    assert contratadas['00001/2024'] == (empresa.cnpj, empresa.nome)
    # Pessoa física não tem CNPJ, e o CPF dela não é publicado.
    assert contratadas['00002/2024'] == (None, prestador.pessoa_fisica.nome)
