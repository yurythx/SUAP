"""Tela de empenhos do SIAFI sem requisição de despesa (``/plan_estrategico/empenhos_sem_requisicao/<plano>/``)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from comum.models import User
from plan_estrategico.models import PlanoAtividade, UnidadeGestora
from plan_estrategico.tests.factories import NotaEmpenhoFactory, PlanoInternoPlanoAtividadeFactory
from rh.tests.factories import ServidorFactory
from tesouro_gerencial.models import DocumentoEmpenho, EventoNotaEmpenho
from tesouro_gerencial.tests.factories import (
    DocumentoEmpenhoFactory,
    DocumentoEmpenhoItemFactory,
    EventoNotaEmpenhoFactory,
    PlanoInternoFactory,
    UnidadeGestoraFactory,
)

pytestmark = pytest.mark.django_db

ANO = date.today().year


@pytest.fixture
def plano_atividade() -> PlanoAtividade:
    return PlanoInternoPlanoAtividadeFactory().plano_atividade


def usuario(*grupos: str) -> User:
    user = ServidorFactory().get_user()
    user.groups.add(*Group.objects.filter(name__in=grupos))
    return user


def empenho(numero: str, valor: str, evento: int, inicial: DocumentoEmpenho | None = None) -> DocumentoEmpenho:
    tipo = DocumentoEmpenho.TIPO_RO if inicial else DocumentoEmpenho.TIPO_NE
    documento = DocumentoEmpenhoFactory(numero=numero, tipo=tipo, documento_empenho_inicial=inicial)
    DocumentoEmpenhoItemFactory(documento_empenho=documento, valor=Decimal(valor), evento=EventoNotaEmpenhoFactory(codigo=str(evento)))
    return documento


def url(plano_atividade: PlanoAtividade) -> str:
    return f'/plan_estrategico/empenhos_sem_requisicao/{plano_atividade.pk}/'


def test_lista_os_empenhos_sem_requisicao_e_exporta_xls(client: Client, sync_permissions, plano_atividade: PlanoAtividade) -> None:
    sem_requisicao = empenho(f'{ANO}NE000001', '1000.00', EventoNotaEmpenho.INCLUSAO)
    informada = empenho(f'{ANO}NE000002', '800.00', EventoNotaEmpenho.INCLUSAO)
    NotaEmpenhoFactory(numero_empenho=informada.numero)
    anulacao = empenho(f'{ANO}RO000001', '-300.00', EventoNotaEmpenho.ANULACAO, inicial=informada)
    client.force_login(usuario('Administrador de Planejamento Estratégico'))

    resposta = client.get(url(plano_atividade))

    assert resposta.status_code == 200
    assert [r.documento_empenho.numero for r in resposta.context['registros']] == [sem_requisicao.numero, anulacao.numero]
    assert resposta.context['resumo'] == {'total': 2, 'empenhos': 2, 'inclusoes': 1, 'reforcos': 0, 'anulacoes': 1}

    xls = client.get(url(plano_atividade), {'xls': '1'})

    assert xls.status_code == 200
    assert 'attachment' in xls['Content-Disposition']


def test_executor_orcamentario_ve_so_as_ugs_do_seu_setor(client: Client, sync_permissions, plano_atividade: PlanoAtividade) -> None:
    empenho(f'{ANO}NE000001', '1000.00', EventoNotaEmpenho.INCLUSAO)
    unidade_gestora = UnidadeGestora.objects.get(pdi=plano_atividade.pdi)
    executor = usuario('Executor Orçamentário')
    client.force_login(executor)

    assert client.get(url(plano_atividade)).context['resumo']['total'] == 0

    unidade_gestora.setor_financeiro = executor.get_relacionamento().setor
    unidade_gestora.save()

    assert client.get(url(plano_atividade)).context['resumo']['total'] == 1


def test_usuario_sem_grupo_orcamentario_e_barrado(client: Client, sync_permissions, plano_atividade: PlanoAtividade) -> None:
    client.force_login(usuario())

    assert client.get(url(plano_atividade)).status_code == 403


def test_combo_de_ugr_oferece_so_as_do_escopo_da_listagem(client: Client, sync_permissions, plano_atividade: PlanoAtividade) -> None:
    no_plano = UnidadeGestoraFactory(codigo='999101', nome='UGR do plano')
    fora_do_plano = UnidadeGestoraFactory(codigo='999102', nome='UGR de outro PI')
    DocumentoEmpenhoFactory(numero=f'{ANO}NE000001', tipo=DocumentoEmpenho.TIPO_NE, responsavel_ug=no_plano)
    DocumentoEmpenhoFactory(
        numero=f'{ANO}NE000002', tipo=DocumentoEmpenho.TIPO_NE, responsavel_ug=fora_do_plano, plano_interno=PlanoInternoFactory(codigo='FORA')
    )
    client.force_login(usuario('Administrador de Planejamento Estratégico'))

    ugrs = client.get(url(plano_atividade)).context['form'].fields['ugr'].queryset

    assert list(ugrs) == [no_plano]


def test_busca_pelo_numero_do_empenho_traz_a_ne_e_seus_ros(client: Client, sync_permissions, plano_atividade: PlanoAtividade) -> None:
    buscada = empenho(f'{ANO}NE000001', '1000.00', EventoNotaEmpenho.INCLUSAO)
    reforco = empenho(f'{ANO}RO000001', '200.00', EventoNotaEmpenho.REFORCO, inicial=buscada)
    empenho(f'{ANO}NE000002', '800.00', EventoNotaEmpenho.INCLUSAO)
    client.force_login(usuario('Administrador de Planejamento Estratégico'))

    resposta = client.get(url(plano_atividade), {'numero_empenho': ' NE000001 '})

    assert [r.documento_empenho.numero for r in resposta.context['registros']] == [buscada.numero, reforco.numero]
    assert resposta.context['resumo']['empenhos'] == 1
