"""O botão Atribuir da caixa de processos segue a chefia de quem abre a caixa (#17811)."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from comum.models import User
from processo_eletronico.tests.factories import (
    CompartilhamentoPoderChefeFactory,
    CompartilhamentoProcessoEletronicoSetorPessoaFactory,
    ProcessoFactory,
    TramiteFactory,
)
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

LINK_ATRIBUIR = '/processo_eletronico/atribuir_processo/'


@pytest.fixture
def setor_com_chefe_e_comum(db: None, sync_permissions: None, setor_com_siorg: Setor) -> tuple[Setor, User, User]:
    cache.clear()
    setor = setor_com_siorg
    chefe, comum, de_fora = ServidorFactory(setor=setor), ServidorFactory(setor=setor), ServidorFactory(setor=SetorFactory())
    CompartilhamentoPoderChefeFactory(setor_dono=setor, vinculo_permitido=chefe.get_vinculo())
    CompartilhamentoProcessoEletronicoSetorPessoaFactory(setor_dono=setor, vinculo_permitido=comum.get_vinculo())
    processo = ProcessoFactory(setor_criacao=setor, usuario_gerador=chefe.get_user())
    processo.interessados.add(de_fora.get_vinculo())  # o post_save do NUP 17 exige um interessado
    TramiteFactory(
        processo=processo,
        remetente_setor=de_fora.setor,
        remetente_vinculo=de_fora.get_vinculo(),
        destinatario_setor=setor,
        data_hora_recebimento=timezone.now(),
        recebido_por=comum.get_vinculo(),
    )
    return setor, chefe.get_user(), comum.get_user()


def _ve_atribuir(client: Client, user: User, setor: Setor) -> bool:
    client.force_login(user)
    resposta = client.get(
        '/processo_eletronico/caixa_processos/', {'setor': setor.pk, 'tab': 'a-encaminhar'}, headers={'x-requested-with': 'XMLHttpRequest'}
    )
    assert resposta.status_code == 200
    return LINK_ATRIBUIR in resposta.content.decode()


@pytest.mark.parametrize('chefe_primeiro', [True, False])
def test_atribuir_aparece_so_para_o_chefe(client: Client, setor_com_chefe_e_comum: tuple[Setor, User, User], chefe_primeiro: bool) -> None:
    setor, chefe, comum = setor_com_chefe_e_comum
    ordem = [(chefe, True), (comum, False)] if chefe_primeiro else [(comum, False), (chefe, True)]
    assert [_ve_atribuir(client, user, setor) for user, _ in ordem] == [esperado for _, esperado in ordem]
