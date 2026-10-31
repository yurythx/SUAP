"""Testes do endpoint público de obras (engenharia) dos dados abertos."""

from datetime import date
from decimal import Decimal

import pytest

from comum.tests.factories import PrestadorServicoFactory
from contratos.models import Contrato, TipoContrato
from rh.tests.factories import PessoaJuridicaFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_obras_publica_cnpj_e_razao_social_da_empresa(client):
    empresa = PessoaJuridicaFactory()
    prestador = PrestadorServicoFactory()
    # O endpoint filtra as obras pelo tipo de contrato de id 5.
    tipo = TipoContrato.objects.create(id=5, descricao='Obra')
    for numero, vinculo in (('00001/2024', empresa.get_vinculo()), ('00002/2024', prestador.get_vinculo())):
        Contrato.objects.create(
            numero=numero,
            tipo=tipo,
            valor=Decimal('1000.00'),
            data_inicio=date(2024, 1, 1),
            objeto='Reforma do bloco',
            vinculo_contratado=vinculo,
        )

    resposta = client.get('/dados_abertos/api/engenharia/engenharia/')

    assert resposta.status_code == 200
    empresas = {o['numero_contrato']: (o['cnpj_empresa'], o['razao_social_empresa']) for o in resposta.json()['results']}
    assert empresas['00001/2024'] == (empresa.cnpj, empresa.nome)
    # Pessoa física não tem CNPJ, e o CPF dela não é publicado.
    assert empresas['00002/2024'] == (None, prestador.pessoa_fisica.nome)
