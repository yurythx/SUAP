"""Encaminhamento em lote de processos apensados entre si (#17774).

Encaminhar um processo apensado já encaminha os demais processos do apensamento. Quando o lote
traz mais de um processo do mesmo apensamento, cada um deve ganhar um único trâmite: o trâmite
duplicado fica "Aguardando recebimento" para sempre, porque o recebimento só alcança o último.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.test import Client
from django.utils import timezone

from comum.utils import get_sigla_reitoria
from processo_eletronico.models import ModeloDespacho, Processo, Tramite
from processo_eletronico.tests.factories import (
    ApensamentoFactory,
    ApensamentoProcessoFactory,
    CompartilhamentoPoderChefeFactory,
    ProcessoFactory,
    TramiteFactory,
)
from rh.models import Setor
from rh.tests.factories import PapelFactory, ServidorFactory, SetorFactory

SENHA = '123'


@pytest.fixture
def cenario(db: None, sync_permissions: None, setor_com_siorg: Setor) -> SimpleNamespace:
    """Dois processos apensados, recebidos no meu setor, e um servidor que opera o setor de destino."""
    # O despacho resolve variáveis que procuram o campus da reitoria.
    destino = SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria')
    eu = ServidorFactory(setor=setor_com_siorg)
    colega_do_destino = ServidorFactory(setor=destino)
    user = eu.get_user()
    user.set_password(SENHA)
    user.save()
    CompartilhamentoPoderChefeFactory(setor_dono=setor_com_siorg, vinculo_permitido=eu.get_vinculo())
    CompartilhamentoPoderChefeFactory(setor_dono=destino, vinculo_permitido=colega_do_destino.get_vinculo())
    ModeloDespacho.objects.create(cabecalho='Cabeçalho', rodape='Rodapé')

    apensamento = ApensamentoFactory()
    processos = []
    for _ in range(2):
        processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=user)
        processo.interessados.add(colega_do_destino.get_vinculo())
        TramiteFactory(
            processo=processo,
            remetente_setor=destino,
            remetente_vinculo=colega_do_destino.get_vinculo(),
            destinatario_setor=setor_com_siorg,
            data_hora_recebimento=timezone.now(),
            recebido_por=eu.get_vinculo(),
        )
        ApensamentoProcessoFactory(apensamento=apensamento, processo=processo)
        processos.append(processo)

    return SimpleNamespace(
        user=user,
        papel=PapelFactory(servidor=eu),
        destino=destino,
        colega_do_destino=colega_do_destino.get_user(),
        processos=processos,
    )


def _encaminhar_em_lote(client: Client, cenario: SimpleNamespace, processos: list[Processo]) -> None:
    client.force_login(cenario.user)
    ids = '-'.join(str(p.pk) for p in processos)
    resposta = client.post(
        f'/processo_eletronico/processo/encaminhar_lote/{ids}/',
        {
            'despacho_corpo': 'Segue para análise.',
            'tipo_busca_setor': 'autocompletar',
            'destinatario_setor_autocompletar': cenario.destino.pk,
            'papel': cenario.papel.pk,
            'senha': SENHA,
        },
    )
    assert resposta.status_code == 302


def test_lote_com_processos_apensados_gera_um_tramite_por_processo(client: Client, cenario: SimpleNamespace) -> None:
    principal, apensado = cenario.processos

    _encaminhar_em_lote(client, cenario, [principal, apensado])

    for processo in cenario.processos:
        assert Tramite.objects.filter(processo=processo, destinatario_setor=cenario.destino).count() == 1


def test_receber_no_destino_nao_deixa_tramite_aguardando_recebimento(client: Client, cenario: SimpleNamespace) -> None:
    principal, apensado = cenario.processos
    _encaminhar_em_lote(client, cenario, [principal, apensado])

    client.force_login(cenario.colega_do_destino)
    resposta = client.get(f'/processo_eletronico/processo/receber/{principal.pk}/')

    assert resposta.status_code == 302
    assert not Tramite.objects.filter(processo__in=cenario.processos, data_hora_recebimento__isnull=True).exists()
