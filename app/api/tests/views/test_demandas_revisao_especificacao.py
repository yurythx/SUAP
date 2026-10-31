"""Proposta de revisão de especificação pela API (/api/ti/demandas/{id}/revisoes-especificacao/).

Depois de aprovada, a consolidação só muda pelo fluxo de revisão: o endpoint cria a
``RevisaoEspecificacao`` pendente e nunca toca a ``Especificacao`` — quem aplica é o
demandante, ao validar. As regras são as da tela: permissão ``add_especificacao``, ser
analista da demanda, demanda em desenvolvimento ou homologação e validação ainda não pedida.
"""

import json
from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from ninja_jwt.tokens import AccessToken

from comum.tests.factories import UserFactory
from demandas.models import HistoricoRevisao, RevisaoEspecificacao
from demandas.models.demanda import Situacao
from demandas.tests.factories import DemandaFactory, DoDFactory, EspecificacaoFactory


@pytest.fixture(autouse=True)
def sem_email():
    """A solicitação de validação notifica os demandantes por e-mail: fronteira externa."""
    with mock.patch('demandas.models.consolidacao.Notificar') as notificar:
        yield notificar


@pytest.fixture
def analista(db):
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename='add_especificacao', content_type__app_label='demandas'))
    return user


@pytest.fixture
def especificacao(analista):
    demanda = DemandaFactory(situacao=Situacao.ESTADO_EM_DESENVOLVIMENTO)
    demanda.analistas.add(analista)
    return EspecificacaoFactory(dod=DoDFactory(demanda=demanda), nome='Listar pendências', atividades='<p>Listar.</p>')


def _post(client, user, demanda_id, corpo):
    return client.post(
        f'/api/ti/demandas/{demanda_id}/revisoes-especificacao/',
        data=json.dumps(corpo),
        content_type='application/json',
        HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(user)}',
    )


def test_revisa_especificacao_existente_sem_alterar_a_aprovada(client, analista, especificacao):
    response = _post(client, analista, especificacao.dod.demanda_id, {'especificacao_id': especificacao.pk, 'atividades': '<p>Listar e filtrar.</p>'})

    assert response.status_code == 201, response.content
    revisao = RevisaoEspecificacao.objects.get(pk=response.json()['id'])
    assert (revisao.especificacao, revisao.nome, revisao.atividades) == (especificacao, 'Listar pendências', '<p>Listar e filtrar.</p>')
    especificacao.refresh_from_db()
    assert especificacao.atividades == '<p>Listar.</p>'
    assert not especificacao.dod.validacao_revisao_solicitada


def test_revisar_de_novo_atualiza_a_revisao_pendente(client, analista, especificacao):
    demanda_id = especificacao.dod.demanda_id
    _post(client, analista, demanda_id, {'especificacao_id': especificacao.pk, 'nome': 'Primeira proposta'})

    response = _post(client, analista, demanda_id, {'especificacao_id': especificacao.pk, 'nome': 'Segunda proposta'})

    assert response.status_code == 200, response.content
    assert list(RevisaoEspecificacao.objects.filter(especificacao=especificacao).values_list('nome', flat=True)) == ['Segunda proposta']


def test_propoe_especificacao_nova(client, analista, especificacao):
    response = _post(client, analista, especificacao.dod.demanda_id, {'nome': 'Indicadores', 'atividades': '<p>Medir retrocessos.</p>'})

    assert response.status_code == 201, response.content
    assert response.json()['especificacao_id'] is None
    assert response.json()['titulo'] == 'Nova especificação: Indicadores'
    assert especificacao.dod.especificacao_set.count() == 1


def test_propoe_remocao(client, analista, especificacao):
    response = _post(client, analista, especificacao.dod.demanda_id, {'especificacao_id': especificacao.pk, 'remocao_solicitada': True})

    assert response.status_code == 201, response.content
    revisao = RevisaoEspecificacao.objects.get(pk=response.json()['id'])
    assert revisao.remocao_solicitada
    assert especificacao.dod.especificacao_set.filter(pk=especificacao.pk).exists()


def test_solicitar_validacao_marca_a_consolidacao_e_registra_historico(client, analista, especificacao, sem_email):
    demanda = especificacao.dod.demanda

    response = _post(client, analista, demanda.pk, {'nome': 'Indicadores', 'atividades': '<p>x</p>', 'solicitar_validacao': True})

    assert response.status_code == 201, response.content
    assert response.json()['validacao_solicitada']
    assert HistoricoRevisao.objects.filter(demanda=demanda, usuario=analista, acao=HistoricoRevisao.AVALIACAO_SOLICITADA).exists()
    sem_email.solicitacao_aprovacao_modificacoes_especificacao.assert_called_once_with(demanda)
    # Pedida a validação, a consolidação fecha para novas revisões até os demandantes avaliarem.
    response = _post(client, analista, demanda.pk, {'nome': 'Outra', 'atividades': '<p>y</p>'})
    assert response.status_code == 422
    assert response.json()['error'] == 'revisao_nao_aceita'


def test_atividades_perde_html_ativo(client, analista, especificacao):
    corpo = {'nome': 'Indicadores', 'atividades': '<p>ok</p><script>alert(1)</script><img src="x" onerror="alert(1)">'}

    response = _post(client, analista, especificacao.dod.demanda_id, corpo)

    atividades = RevisaoEspecificacao.objects.get(pk=response.json()['id']).atividades
    assert '<p>ok</p>' in atividades
    assert 'script' not in atividades
    assert 'onerror' not in atividades


def test_revisao_igual_a_original_e_recusada(client, analista, especificacao):
    response = _post(client, analista, especificacao.dod.demanda_id, {'especificacao_id': especificacao.pk})

    assert response.status_code == 422
    assert response.json()['error'] == 'revisao_invalida'
    assert not RevisaoEspecificacao.objects.exists()


def test_especificacao_de_outra_demanda_responde_404(client, analista, especificacao):
    alheia = EspecificacaoFactory()

    response = _post(client, analista, especificacao.dod.demanda_id, {'especificacao_id': alheia.pk, 'nome': 'Invasão'})

    assert response.status_code == 404
    assert response.json()['error'] == 'especificacao_not_found'


@pytest.mark.parametrize('papel', ['sem_permissao', 'nao_analista'])
def test_usuario_sem_permissao_responde_403(client, analista, especificacao, papel):
    if papel == 'sem_permissao':
        usuario = UserFactory()
        especificacao.dod.demanda.analistas.add(usuario)
    else:
        usuario = UserFactory()
        usuario.user_permissions.add(Permission.objects.get(codename='add_especificacao', content_type__app_label='demandas'))

    response = _post(client, usuario, especificacao.dod.demanda_id, {'nome': 'Indicadores', 'atividades': '<p>x</p>'})

    assert response.status_code == 403
    assert not RevisaoEspecificacao.objects.exists()


@pytest.mark.parametrize('situacao', [Situacao.ESTADO_EM_NEGOCIACAO, Situacao.ESTADO_APROVADO, Situacao.ESTADO_CONCLUIDO])
def test_etapa_que_nao_aceita_revisao_responde_422(client, analista, especificacao, situacao):
    demanda = especificacao.dod.demanda
    demanda.situacao = situacao
    demanda.save()

    response = _post(client, analista, demanda.pk, {'nome': 'Indicadores', 'atividades': '<p>x</p>'})

    assert response.status_code == 422
    assert response.json()['error'] == 'revisao_nao_aceita'


def test_lista_as_revisoes_pendentes(client, analista, especificacao):
    analista.user_permissions.add(Permission.objects.get(codename='view_demanda', content_type__app_label='demandas'))
    demanda_id = especificacao.dod.demanda_id
    _post(client, analista, demanda_id, {'especificacao_id': especificacao.pk, 'remocao_solicitada': True})
    _post(client, analista, demanda_id, {'nome': 'Indicadores', 'atividades': '<p>x</p>'})

    response = client.get(f'/api/ti/demandas/{demanda_id}/revisoes-especificacao/', HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(analista)}')

    assert response.status_code == 200, response.content
    assert [(r['especificacao_id'], r['remocao_solicitada']) for r in response.json()] == [(especificacao.pk, True), (None, False)]


def test_agent_context_expoe_o_id_da_especificacao_a_revisar(client, analista, especificacao):
    analista.user_permissions.add(Permission.objects.get(codename='view_demanda', content_type__app_label='demandas'))

    response = client.get(
        f'/api/ti/demandas/{especificacao.dod.demanda_id}/agent-context/', HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(analista)}'
    )

    assert response.status_code == 200, response.content
    assert [e['id'] for e in response.json()['dod']['especificacoes']] == [especificacao.pk]
