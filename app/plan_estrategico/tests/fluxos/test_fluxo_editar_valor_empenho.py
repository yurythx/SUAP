"""Edição do valor da linha de empenho/RO (``/plan_estrategico/editar_valorempenho/<id>/``) pelo Executor Orçamentário.

O valor pode ser ajustado na emissão (com ou sem empenho informado) e enquanto a requisição aguarda a validação do
SIAFI, quando a conferência com o tesouro é refeita após salvar.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.test import Client

from comum.models import User
from plan_estrategico.models import NotaEmpenho, RequisicaoDespesa, RequisicaoDespesaHistorico
from plan_estrategico.tests.factories import NotaEmpenhoFactory, RequisicaoDespesaFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def executor(sync_permissions) -> User:
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Executor Orçamentário'))
    return user


def linha(executor: User, status: int, tipo: int = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO, **kwargs) -> NotaEmpenho:
    """Linha de R$ 800,00 numa requisição de R$ 1.000,00 cuja UG tem o setor do executor como setor financeiro."""
    requisicao = RequisicaoDespesaFactory(status=status, tipo_requisicao=tipo, valor_inicial=Decimal('1000.00'), valor=Decimal('800.00'))
    requisicao.unidade_gestora.setor_financeiro = executor.get_relacionamento().setor
    requisicao.unidade_gestora.save()
    RequisicaoDespesaHistorico.objects.create(despesa=requisicao, status=status, alterado_em=datetime.now(), alterado_por=executor)
    return NotaEmpenhoFactory(requisicao=requisicao, valor=Decimal('800.00'), **kwargs)


def url_editar(empenho: NotaEmpenho) -> str:
    return f'/plan_estrategico/editar_valorempenho/{empenho.pk}/'


def url_detalhe(empenho: NotaEmpenho) -> str:
    return f'/plan_estrategico/detalhar_requisicaodespesa/{empenho.requisicao.pk}/'


def test_executor_edita_valor_durante_a_validacao_e_a_requisicao_e_reconferida(client: Client, executor: User) -> None:
    empenho = linha(executor, RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)
    client.force_login(executor)

    assert url_editar(empenho) in client.get(url_detalhe(empenho)).content.decode()

    resposta = client.post(url_editar(empenho), {'valor': '900,00'})

    assert NotaEmpenho.objects.get(pk=empenho.pk).valor == Decimal('900.00')
    assert RequisicaoDespesa.objects.get(pk=empenho.requisicao.pk).valor == Decimal('900.00')
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == [
        'Valor do empenho atualizado. A requisição segue aguardando a validação do SIAFI.'
    ]


def test_executor_edita_valor_da_linha_ainda_sem_empenho(client: Client, executor: User) -> None:
    empenho = linha(executor, RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO, numero_empenho=None)
    client.force_login(executor)

    assert url_editar(empenho) in client.get(url_detalhe(empenho)).content.decode()

    resposta = client.post(url_editar(empenho), {'valor': '1.000,00'})

    assert NotaEmpenho.objects.get(pk=empenho.pk).valor == Decimal('1000.00')
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == ['Valor do empenho atualizado.']


def test_editar_valor_ro_aparece_na_validacao_do_reforco(client: Client, executor: User) -> None:
    empenho = linha(executor, RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO, tipo=RequisicaoDespesa.TIPO_REFORCO_EMPENHO, numero_ro='2026RO000001')
    client.force_login(executor)

    assert url_editar(empenho) in client.get(url_detalhe(empenho)).content.decode()


def test_valor_nao_passa_do_valor_da_requisicao(client: Client, executor: User) -> None:
    empenho = linha(executor, RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)
    client.force_login(executor)

    client.post(url_editar(empenho), {'valor': '1.000,01'})

    assert NotaEmpenho.objects.get(pk=empenho.pk).valor == Decimal('800.00')


@pytest.mark.parametrize('status', [RequisicaoDespesa.STATUS_CONCLUIDA, RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO])
def test_executor_nao_edita_valor_fora_da_emissao_e_da_validacao(client: Client, executor: User, status: int) -> None:
    empenho = linha(executor, status)
    client.force_login(executor)

    assert url_editar(empenho) not in client.get(url_detalhe(empenho)).content.decode()
    assert client.post(url_editar(empenho), {'valor': '900,00'}).status_code == 403
    assert NotaEmpenho.objects.get(pk=empenho.pk).valor == Decimal('800.00')


def test_executor_de_outro_setor_financeiro_nao_edita_valor(client: Client, executor: User) -> None:
    empenho = linha(executor, RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)
    outro_executor = ServidorFactory().get_user()
    outro_executor.groups.add(Group.objects.get(name='Executor Orçamentário'))
    client.force_login(outro_executor)

    assert client.post(url_editar(empenho), {'valor': '900,00'}).status_code == 403
    assert NotaEmpenho.objects.get(pk=empenho.pk).valor == Decimal('800.00')
