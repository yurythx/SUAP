"""Contatos de emergência: quem lista e quem adiciona os contatos de outra pessoa.

A listagem pede ``view_contatoemergencia`` e a adição pede ``add_contatoemergencia`` — o dono
dos contatos (``verificacao_propria``) passa pelas duas sem permissão nenhuma. Até a #17399 as
duas checagens estavam trocadas: quem tinha só ``view`` (os três grupos de Gestão de Pessoas do
``comum/permissions.yaml``) adicionava contato de terceiro e tomava 403 ao listá-lo — inclusive
pelo link *Contatos de Emergência* da página do servidor, que já era condicionado a ``view``.
Com a correção, os três grupos passaram a carregar também ``add_contatoemergencia``.
"""

import pytest
from django.contrib.auth.models import Group, Permission

from comum.models import ContatoEmergencia
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

LISTAR = '/comum/pessoa_fisica/{pk}/listar_contatos_de_emergencia'
ADICIONAR = '/comum/pessoa_fisica/{pk}/adicionar_contato_de_emergencia'
CONTATO = {'nome_contato': 'Maria da Silva (mãe)', 'telefone': '(84) 3215-1234'}


def test_terceiro_so_com_view_lista_mas_nao_adiciona(client, sync_permissions):
    alvo = ServidorFactory().pessoa_fisica
    user = ServidorFactory().get_user()
    user.user_permissions.add(Permission.objects.get(codename='view_contatoemergencia', content_type__app_label='comum'))
    client.force_login(user)

    assert client.get(LISTAR.format(pk=alvo.pk)).status_code == 200
    assert client.get(ADICIONAR.format(pk=alvo.pk)).status_code == 403
    assert client.post(ADICIONAR.format(pk=alvo.pk), CONTATO).status_code == 403
    assert not ContatoEmergencia.objects.filter(pessoa_fisica=alvo).exists()


def test_terceiro_com_add_adiciona(client, sync_permissions):
    alvo = ServidorFactory().pessoa_fisica
    user = ServidorFactory().get_user()
    user.user_permissions.add(Permission.objects.get(codename='add_contatoemergencia', content_type__app_label='comum'))
    client.force_login(user)

    assert client.get(ADICIONAR.format(pk=alvo.pk)).status_code == 200
    assert client.post(ADICIONAR.format(pk=alvo.pk), CONTATO).status_code == 302
    assert ContatoEmergencia.objects.filter(pessoa_fisica=alvo, nome_contato=CONTATO['nome_contato']).exists()
    assert client.get(LISTAR.format(pk=alvo.pk)).status_code == 200


def test_gestao_de_pessoas_lista_e_adiciona_contato_de_terceiro(client, sync_permissions):
    alvo = ServidorFactory().pessoa_fisica
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Operador de Gestão de Pessoas'))
    client.force_login(user)

    assert client.get(LISTAR.format(pk=alvo.pk)).status_code == 200
    assert client.post(ADICIONAR.format(pk=alvo.pk), CONTATO).status_code == 302
    assert ContatoEmergencia.objects.filter(pessoa_fisica=alvo, nome_contato=CONTATO['nome_contato']).exists()


def test_dono_lista_e_adiciona_sem_permissao(client, sync_permissions):
    dono = ServidorFactory()
    client.force_login(dono.get_user())
    pk = dono.pessoa_fisica.pk

    assert client.get(LISTAR.format(pk=pk)).status_code == 200
    assert client.post(ADICIONAR.format(pk=pk), CONTATO).status_code == 302
    assert ContatoEmergencia.objects.filter(pessoa_fisica=dono.pessoa_fisica).exists()


def test_terceiro_sem_permissao_nao_lista_nem_adiciona(client, sync_permissions):
    alvo = ServidorFactory().pessoa_fisica
    client.force_login(ServidorFactory().get_user())

    assert client.get(LISTAR.format(pk=alvo.pk)).status_code == 403
    assert client.get(ADICIONAR.format(pk=alvo.pk)).status_code == 403
