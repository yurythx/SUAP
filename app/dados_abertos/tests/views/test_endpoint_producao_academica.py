"""Testes do endpoint público de produção acadêmica dos dados abertos."""

import pytest

from cnpq.models import Autor, CurriculoVittaeLattes, ProducaoBibliografica
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_producao_academica_identifica_lattes_e_orcid_como_do_servidor_ifrn(client):
    # O currículo é do servidor; o autor declarado na produção é outra pessoa.
    servidor = ServidorFactory(pessoa_fisica__orcid='https://orcid.org/0000-0002-1825-0097')
    curriculo = CurriculoVittaeLattes.objects.create(numero_identificador='1234567890123456', vinculo=servidor.get_vinculo())
    producao = ProducaoBibliografica.objects.create(curriculo=curriculo, titulo='Artigo em coautoria', ano=2024, tipo_pub='ARTIGO-PUBLICADO')
    producao.autores.add(Autor.objects.create(nome_completo='Outra Pessoa', nome_citacao='PESSOA, O.', ordem='1'))

    resposta = client.get('/dados_abertos/api/cnpq/producao_academica/', {'ano': 2024})

    assert resposta.status_code == 200
    [item] = resposta.json()['results']
    assert item['autor'] == 'Outra Pessoa'
    assert item['lattes_servidor_ifrn'] == 'http://lattes.cnpq.br/1234567890123456'
    assert item['orcid_servidor_ifrn'] == 'https://orcid.org/0000-0002-1825-0097'
    assert 'link_lattes' not in item
    assert 'orcid' not in item
