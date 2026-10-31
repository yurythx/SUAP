"""Tela do avaliador (``/rh/avaliador/<id>/``): mostra CPF, nascimento e telefones.

Só exigia login, então qualquer usuário autenticado lia os dados de qualquer avaliador (#17645).
Agora exige ``rh.view_avaliador`` (Coordenador de Gestão de Pessoas Sistêmico, Membro e Presidente
CPPD) ou ser o próprio avaliador.
"""

import pytest
from django.contrib.auth.models import Group

from rh.tests.factories import AvaliadorFactory, ServidorFactory, SetorFactory

URL = '/rh/avaliador/{}/'


@pytest.fixture
def avaliador(db, sync_permissions):
    return AvaliadorFactory(vinculo=ServidorFactory(setor=SetorFactory()).get_vinculo())


def test_servidor_qualquer_nao_ve_avaliador_alheio(client, avaliador):
    client.force_login(ServidorFactory(setor=SetorFactory()).get_user())
    assert client.get(URL.format(avaliador.pk)).status_code == 403


def test_avaliador_ve_o_proprio_registro(client, avaliador):
    client.force_login(avaliador.vinculo.user)
    assert client.get(URL.format(avaliador.pk)).status_code == 200


def test_gestao_de_pessoas_sistemico_ve_qualquer_avaliador(client, avaliador):
    usuario = ServidorFactory(setor=SetorFactory()).get_user()
    usuario.groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
    client.force_login(usuario)
    resposta = client.get(URL.format(avaliador.pk))
    assert resposta.status_code == 200
    assert avaliador.vinculo.pessoa.nome in resposta.content.decode()
