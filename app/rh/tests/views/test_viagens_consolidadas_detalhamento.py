"""Detalhamento do Relatório de Viagens Consolidadas (``/rh/viagens_consolidadas_detalhamento/<ano>/<mes>/<siorg>/``).

Sem nenhuma viagem consolidada no filtro a view não montava ``table`` e o template quebrava com 500 (#17661).
"""

import pytest
from django.contrib.auth.models import Group

from rh.tests.factories import ServidorFactory, SetorFactory, ViagemFactory

URL = '/rh/viagens_consolidadas_detalhamento/{}/{}/{}/'


@pytest.fixture
def gestor(db, sync_permissions, client):
    servidor = ServidorFactory(setor=SetorFactory())
    servidor.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
    client.force_login(servidor.get_user())
    return servidor


def test_sem_viagens_no_filtro_responde_200_com_mensagem_de_vazio(client, gestor):
    resposta = client.get(URL.format(2001, 0, 'todos'))
    assert resposta.status_code == 200
    assert 'Nenhuma viagem consolidada' in resposta.content.decode()


def test_com_viagens_lista_o_detalhamento(client, gestor):
    viagem = ViagemFactory()
    ano = viagem.data_inicio_viagem.year
    resposta = client.get(URL.format(ano, 0, 'todos'))
    assert resposta.status_code == 200
    assert viagem.numero_pcdp in resposta.content.decode()


def test_siorg_inexistente_responde_200(client, gestor):
    viagem = ViagemFactory()
    resposta = client.get(URL.format(viagem.data_inicio_viagem.year, 0, 'NAOEXISTE'))
    assert resposta.status_code == 200
