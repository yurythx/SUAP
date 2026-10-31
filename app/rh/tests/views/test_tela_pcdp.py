"""Tela da viagem do SCDP (``/rh/tela_pcdp/<id>/``) com viagem sem servidor.

O importador do SCDP grava viagem sem servidor quando o proposto não é servidor, e sem vínculo
quando a planilha não traz CPF. A view só definia ``verificacao_propria`` com servidor, então
respondia 500 (``UnboundLocalError``) em vez de 403; e o título lia ``viagem.vinculo.pessoa``,
que também quebrava sem vínculo (#17646).
"""

import pytest
from django.contrib.auth.models import Group

from rh.tests.factories import ServidorFactory, SetorFactory, ViagemFactory

URL = '/rh/tela_pcdp/{}/'


@pytest.fixture
def servidor(db, sync_permissions):
    return ServidorFactory(setor=SetorFactory())


def _viagem_sem_servidor(vinculo=None):
    return ViagemFactory(servidor=None, vinculo=vinculo, nome_proposto='Colaborador Eventual SCDP')


def test_sem_permissao_recebe_403_em_viagem_de_outro_sem_servidor(client, servidor):
    viagem = _viagem_sem_servidor(vinculo=ServidorFactory(setor=SetorFactory()).get_vinculo())
    client.force_login(servidor.get_user())
    assert client.get(URL.format(viagem.pk)).status_code == 403


def test_viajante_sem_servidor_ve_a_propria_viagem(client, servidor):
    viagem = _viagem_sem_servidor(vinculo=servidor.get_vinculo())
    client.force_login(servidor.get_user())
    assert client.get(URL.format(viagem.pk)).status_code == 200


def test_gestao_de_pessoas_ve_viagem_sem_vinculo(client, servidor):
    viagem = _viagem_sem_servidor()
    servidor.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
    client.force_login(servidor.get_user())
    resposta = client.get(URL.format(viagem.pk))
    assert resposta.status_code == 200
    assert 'Viagem de Colaborador Eventual SCDP' in resposta.content.decode()
