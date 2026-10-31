"""Anuência da despesa (``/plan_estrategico/anuir_despesa/<id>/``): o Diretor da UA anui e o processo segue ao ordenador."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.messages import get_messages
from django.test import Client

from comum.utils import get_sigla_reitoria

from plan_estrategico.models import RequisicaoDespesa, RequisicaoDespesaHistorico
from plan_estrategico.tests.factories import RequisicaoDespesaFactory
from processo_eletronico.models import ModeloDespacho, Processo, Tramite
from processo_eletronico.tests.factories import ProcessoFactory
from rh.models import Atividade, Servidor, Setor
from rh.tests.factories import PapelFactory, ServidorFactory, ServidorFuncaoHistoricoFactory, SetorFactory, SetorSiapeFactory

pytestmark = pytest.mark.django_db

DESPACHO = 'Dou anuência à realização da despesa.'


def diretor_da_ua(setor_equivalente: Setor) -> Servidor:
    """Servidor com função ativa de Diretor no setor equivalente da UG e senha ``123`` para assinar o trâmite."""
    servidor = ServidorFactory()
    atividade, _ = Atividade.objects.get_or_create(codigo=Atividade.DIRETOR, defaults={'nome': 'Diretor'})
    ServidorFuncaoHistoricoFactory(servidor=servidor, atividade=atividade, setor=SetorSiapeFactory(), setor_suap=setor_equivalente)
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    return servidor


@pytest.fixture
def cenario(sync_permissions) -> SimpleNamespace:
    """Requisição aguardando anuência, com o processo na caixa do setor de anuência e o Diretor da UA logável."""
    ModeloDespacho.objects.create(cabecalho='Cabeçalho', rodape='Rodapé')
    # O cabeçalho do despacho resolve a UO da reitoria pela sigla (`get_variaveis`).
    SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria')
    requisicao = RequisicaoDespesaFactory(status=RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA, finalidade='Aquisição de material')
    unidade_gestora = requisicao.unidade_gestora
    unidade_gestora.setor_anuencia_despesa = SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))
    unidade_gestora.setor_ordenador_despesa = SetorFactory()
    unidade_gestora.save()
    diretor = diretor_da_ua(unidade_gestora.setor_equivalente)
    requisicao.processo = ProcessoFactory(setor_criacao=unidade_gestora.setor_anuencia_despesa, usuario_gerador=diretor.get_user())
    requisicao.processo.interessados.add(diretor.get_vinculo())  # o post_save do NUP 17 exige um interessado
    requisicao.save()
    return SimpleNamespace(requisicao=requisicao, unidade_gestora=unidade_gestora, diretor=diretor, papel=PapelFactory(servidor=diretor))


def url(requisicao: RequisicaoDespesa) -> str:
    return f'/plan_estrategico/anuir_despesa/{requisicao.pk}/'


def test_diretor_anui_e_o_processo_segue_ao_ordenador(client: Client, cenario: SimpleNamespace) -> None:
    client.force_login(cenario.diretor.get_user())

    resposta = client.post(url(cenario.requisicao), {'despacho_anuencia': DESPACHO, 'papel': cenario.papel.pk, 'senha': '123'})

    assert resposta.status_code in (200, 302)
    requisicao = RequisicaoDespesa.objects.get(pk=cenario.requisicao.pk)
    assert requisicao.status == RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
    assert requisicao.vinculo_anuencia == cenario.diretor.get_vinculo()
    assert requisicao.data_anuencia is not None
    assert requisicao.despacho_anuencia == DESPACHO
    tramite = Tramite.objects.get(processo=requisicao.processo)
    assert tramite.remetente_setor == cenario.unidade_gestora.setor_anuencia_despesa
    assert tramite.destinatario_setor == cenario.unidade_gestora.setor_ordenador_despesa
    assert tramite.despacho_corpo == DESPACHO
    assert list(RequisicaoDespesaHistorico.objects.filter(despesa=requisicao).values_list('status', flat=True)) == [
        RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
    ]


def test_quem_nao_e_diretor_da_ua_nao_anui(client: Client, cenario: SimpleNamespace) -> None:
    client.force_login(ServidorFactory().get_user())

    assert client.get(url(cenario.requisicao)).status_code == 403


def test_diretor_nao_anui_fora_do_status_de_anuencia(client: Client, cenario: SimpleNamespace) -> None:
    RequisicaoDespesa.objects.filter(pk=cenario.requisicao.pk).update(status=RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO)
    client.force_login(cenario.diretor.get_user())

    assert client.get(url(cenario.requisicao)).status_code == 403


def test_processo_fora_da_caixa_do_setor_de_anuencia_nao_e_anuido(client: Client, cenario: SimpleNamespace) -> None:
    Processo.objects.filter(pk=cenario.requisicao.processo_id).update(setor_atual=SetorFactory())
    client.force_login(cenario.diretor.get_user())

    resposta = client.post(url(cenario.requisicao), {'despacho_anuencia': DESPACHO, 'papel': cenario.papel.pk, 'senha': '123'})

    setor_anuencia = cenario.unidade_gestora.setor_anuencia_despesa
    processo = Processo.objects.get(pk=cenario.requisicao.processo_id)
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == [
        f'Para anuir a despesa o processo {processo} deve estar na caixa do setor {setor_anuencia}.'
    ]
    assert RequisicaoDespesa.objects.get(pk=cenario.requisicao.pk).status == RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
    assert not Tramite.objects.filter(processo=processo).exists()
