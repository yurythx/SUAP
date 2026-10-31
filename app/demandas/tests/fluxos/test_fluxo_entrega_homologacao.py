"""Fluxo da homologação pela entrega.

"Em homologação" significa que existe uma entrega aguardando o demandante: a etapa entra e
sai desse estado pela entrega, e a aprovação só leva a "Homologada" quando o escopo está
coberto (docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md).

E-mail e GitLab são isolados pela fixture autouse ``sem_efeitos_externos`` (conftest.py).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from comum.models import User
from comum.tests.factories import UserFactory
from demandas.models import Demanda, Entrega, Situacao, StatusEntrega
from demandas.services import EntregaService
from demandas.tests.factories import DoDFactory, EspecificacaoFactory, RevisaoEspecificacaoFactory
from demandas.views import entrega_aprovar, entrega_reprovar
from rh.tests.factories import ServidorFactory

PRAZO = date.today() + timedelta(days=7)
PREVISAO_DESENVOLVIMENTO = date.today() + timedelta(days=30)

pytestmark = [pytest.mark.django_db(databases='__all__'), pytest.mark.usefixtures('sync_permissions')]


@pytest.fixture
def desenvolvedor(db):
    return UserFactory()


@pytest.fixture
def demandante(db):
    return UserFactory()


@pytest.fixture
def em_desenvolvimento(demanda: Demanda, desenvolvedor, demandante) -> Demanda:
    demanda.demandantes.add(demandante)
    demanda.alterar_situacao(desenvolvedor, Situacao.ESTADO_EM_DESENVOLVIMENTO, data_previsao=PREVISAO_DESENVOLVIMENTO)
    return demanda


def _entregar(demanda: Demanda, usuario, especificacoes=(), **kwargs) -> Entrega:
    return EntregaService.criar(demanda=demanda, titulo='Pacote', usuario=usuario, prazo_feedback=PRAZO, especificacoes=especificacoes, **kwargs)


def _recarregar(demanda: Demanda) -> Demanda:
    return Demanda.objects.get(pk=demanda.pk)


def test_registrar_entrega_leva_a_demanda_para_homologacao_com_o_prazo_como_previsao(em_desenvolvimento, desenvolvedor):
    entrega = _entregar(em_desenvolvimento, desenvolvedor)

    demanda = _recarregar(em_desenvolvimento)
    assert demanda.situacao == Situacao.ESTADO_EM_HOMOLOGACAO
    assert demanda.entrega_pendente == entrega
    assert demanda.get_ultimo_historico_situacao().data_previsao == PRAZO


def test_nao_registra_entrega_fora_do_desenvolvimento(demanda, desenvolvedor):
    with pytest.raises(ValidationError):
        _entregar(demanda, desenvolvedor)


def test_reprovar_devolve_ao_desenvolvimento_com_a_previsao_anterior(em_desenvolvimento, desenvolvedor, demandante):
    entrega = _entregar(em_desenvolvimento, desenvolvedor)

    EntregaService.reprovar(entrega, demandante, motivo='Falta o filtro por campus')

    demanda = _recarregar(em_desenvolvimento)
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO
    assert demanda.get_ultimo_historico_situacao().data_previsao == PREVISAO_DESENVOLVIMENTO
    assert Entrega.objects.get(pk=entrega.pk).motivo_rejeicao == 'Falta o filtro por campus'


def test_reprovar_nao_reaproveita_previsao_de_desenvolvimento_que_ja_passou(em_desenvolvimento, desenvolvedor, demandante):
    # A previsão de desenvolvimento venceu enquanto a demanda esperava a homologação.
    historico = em_desenvolvimento.historicosituacao_set.get(situacao=Situacao.ESTADO_EM_DESENVOLVIMENTO)
    historico.data_previsao = date.today() - timedelta(days=60)
    historico.save()
    entrega = _entregar(em_desenvolvimento, desenvolvedor)

    EntregaService.reprovar(entrega, demandante, motivo='Ainda não dá para aprovar')

    demanda = _recarregar(em_desenvolvimento)
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO
    assert demanda.get_ultimo_historico_situacao().data_previsao is None, 'previsão vencida deixaria a demanda em atraso na volta'
    assert not demanda.em_atraso()


def test_aprovacao_parcial_volta_ao_desenvolvimento_e_a_que_cobre_o_escopo_homologa(em_desenvolvimento, desenvolvedor, demandante):
    dod = DoDFactory(demanda=em_desenvolvimento)
    login, relatorio = EspecificacaoFactory(dod=dod), EspecificacaoFactory(dod=dod)

    EntregaService.aprovar(_entregar(em_desenvolvimento, desenvolvedor, [login]), demandante)
    demanda = _recarregar(em_desenvolvimento)
    assert demanda.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO
    assert list(demanda.get_especificacoes_sem_entrega_aprovada()) == [relatorio]

    EntregaService.aprovar(_entregar(demanda, desenvolvedor, [relatorio]), demandante)
    demanda = _recarregar(demanda)
    assert demanda.situacao == Situacao.ESTADO_HOMOLOGADA
    assert not demanda.get_especificacoes_sem_entrega_aprovada().exists()


@pytest.mark.parametrize(('conclui_demanda', 'etapa_final'), [(True, Situacao.ESTADO_HOMOLOGADA), (False, Situacao.ESTADO_EM_DESENVOLVIMENTO)])
def test_sem_especificacoes_quem_decide_e_a_marca_da_entrega(em_desenvolvimento, desenvolvedor, demandante, conclui_demanda, etapa_final):
    entrega = _entregar(em_desenvolvimento, desenvolvedor, conclui_demanda=conclui_demanda)

    EntregaService.aprovar(entrega, demandante)

    assert _recarregar(em_desenvolvimento).situacao == etapa_final


def test_so_demandante_valida_e_nunca_quem_cadastrou(em_desenvolvimento, desenvolvedor, demandante):
    em_desenvolvimento.demandantes.add(desenvolvedor)
    interessado = UserFactory()
    em_desenvolvimento.interessados.add(interessado)
    entrega = _entregar(em_desenvolvimento, desenvolvedor)

    for usuario in (desenvolvedor, interessado):
        with pytest.raises(PermissionDenied):
            EntregaService.aprovar(entrega, usuario)

    EntregaService.aprovar(entrega, demandante, observacao='ok')
    assert Entrega.objects.get(pk=entrega.pk).status == StatusEntrega.APROVADA


def test_aprovacao_recusada_com_revisao_de_consolidacao_pendente(em_desenvolvimento, desenvolvedor, demandante):
    dod = DoDFactory(demanda=em_desenvolvimento)
    especificacao = EspecificacaoFactory(dod=dod)
    entrega = _entregar(em_desenvolvimento, desenvolvedor, [especificacao])
    RevisaoEspecificacaoFactory(dod=dod)

    with pytest.raises(ValidationError):
        EntregaService.aprovar(entrega, demandante)

    assert Entrega.objects.get(pk=entrega.pk).esta_pendente
    assert _recarregar(em_desenvolvimento).situacao == Situacao.ESTADO_EM_HOMOLOGACAO


def test_cancelar_entrega_devolve_ao_desenvolvimento(em_desenvolvimento, desenvolvedor):
    entrega = _entregar(em_desenvolvimento, desenvolvedor)

    EntregaService.cancelar(entrega, desenvolvedor)

    assert _recarregar(em_desenvolvimento).situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO
    assert Entrega.objects.get(pk=entrega.pk).status == StatusEntrega.CANCELADA


def test_suspender_a_demanda_em_homologacao_cancela_a_entrega_pendente(em_desenvolvimento, desenvolvedor):
    entrega = _entregar(em_desenvolvimento, desenvolvedor)
    demanda = _recarregar(em_desenvolvimento)

    demanda.alterar_situacao(desenvolvedor, Situacao.ESTADO_SUSPENSO, comentario='Aguardando outra demanda')

    assert Entrega.objects.get(pk=entrega.pk).status == StatusEntrega.CANCELADA
    assert _recarregar(demanda).entrega_pendente is None


def test_homologacao_nao_e_mais_transicao_manual(em_desenvolvimento, desenvolvedor):
    assert not Situacao.eh_estado_possivel(em_desenvolvimento, Situacao.ESTADO_EM_HOMOLOGACAO)

    _entregar(em_desenvolvimento, desenvolvedor)
    demanda = _recarregar(em_desenvolvimento)
    assert not Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_HOMOLOGADA)
    assert not Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_EM_DESENVOLVIMENTO)
    assert Situacao.eh_estado_possivel(demanda, Situacao.ESTADO_SUSPENSO)


@pytest.mark.parametrize('view', [entrega_aprovar, entrega_reprovar])
def test_telas_de_validacao_barram_quem_nao_e_demandante(em_desenvolvimento, desenvolvedor, view):
    entrega = _entregar(em_desenvolvimento, desenvolvedor)
    interessado = UserFactory()
    em_desenvolvimento.interessados.add(interessado)

    for usuario in (desenvolvedor, interessado):
        request = RequestFactory().get(f'/demandas/entrega/{entrega.pk}/')
        request.user = usuario
        with pytest.raises(PermissionDenied):
            view(request, entrega.pk)


@pytest.mark.parametrize(('pode_ver_ambiente', 've_a_senha'), [(True, True), (False, False)])
def test_aba_entregas_so_mostra_as_credenciais_a_quem_pode(em_desenvolvimento, desenvolvedor, pode_ver_ambiente, ve_a_senha):
    entrega = _entregar(em_desenvolvimento, desenvolvedor, url_validacao='https://homolog.exemplo/', senha_homologacao='s3gr3d0')
    demanda = _recarregar(em_desenvolvimento)

    html = render_to_string(
        'tabs/entregas.html',
        {'demanda': demanda, 'entregas': [entrega], 'entrega_pendente': entrega, 'pode_ver_ambiente': pode_ver_ambiente, 'perms': {}},
    )

    assert ('s3gr3d0' in html) is ve_a_senha
    assert ('https://homolog.exemplo/' in html) is ve_a_senha


# --- Atalho "Homologar" ------------------------------------------------------


def _analista():
    usuario = ServidorFactory().get_user()
    usuario.groups.add(Group.objects.get(name='Analista'))
    return User.objects.get(pk=usuario.pk)


def test_homologar_e_atalho_para_entregar_tudo_o_que_falta(client, em_desenvolvimento, demandante):
    dod = DoDFactory(demanda=em_desenvolvimento)
    especificacoes = [EspecificacaoFactory(dod=dod, atividades='Relatório'), EspecificacaoFactory(dod=dod, atividades='Filtro')]
    analista = _analista()
    homologar = Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_EM_HOMOLOGACAO]
    assert homologar in em_desenvolvimento.get_etapas(analista)
    assert homologar not in em_desenvolvimento.get_etapas(demandante), 'só a equipe cadastra entrega'

    client.force_login(analista)
    atalho = client.get(reverse('demanda_situacao_alterar', kwargs={'demanda_id': em_desenvolvimento.pk, 'situacao': homologar}))
    url_entrega = f'{reverse("criar_enrega", kwargs={"demanda_id": em_desenvolvimento.pk})}?homologar=1'
    assert (atalho.status_code, atalho.url) == (302, url_entrega)

    formulario = client.get(url_entrega).context['form']
    assert sorted(formulario.initial['especificacoes']) == sorted(e.pk for e in especificacoes)
    assert formulario.initial['prazo_feedback'] > date.today().isoformat()

    resposta = client.post(url_entrega, {**formulario.initial, 'especificacoes': formulario.initial['especificacoes']})

    assert resposta.status_code == 302
    demanda = _recarregar(em_desenvolvimento)
    assert demanda.situacao == Situacao.ESTADO_EM_HOMOLOGACAO
    assert set(demanda.entrega_pendente.especificacoes.all()) == set(especificacoes)
    assert homologar not in demanda.get_etapas(analista), 'com entrega pendente não há o que homologar'


def test_homologar_fora_do_desenvolvimento_e_recusado(client, demanda):
    client.force_login(_analista())
    resposta = client.get(reverse('demanda_situacao_alterar', kwargs={'demanda_id': demanda.pk, 'situacao': 'Homologar'}))

    assert resposta.status_code == 403
