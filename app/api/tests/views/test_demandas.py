"""Autenticação dos endpoints de demandas e entregas (/api/ti/demandas/..., /api/ti/entregas/...).

Os endpoints usam a autenticação padrão da API (JWT, token OAuth2 e sessão): o suap-mcp
chama com um access token OAuth2 ``client_credentials`` e o CI (living spec) com um JWT.
Um id inexistente responde 404 em JSON só depois de autenticar; sem credencial, 401.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from ninja_jwt.tokens import AccessToken as JWTAccessToken
from oauth2_provider.models import get_access_token_model, get_application_model

from comum.tests.factories import UserFactory
from demandas.tests.factories import DemandaFactory

ID_INEXISTENTE = 999999

ENDPOINTS = [
    pytest.param('get', f'/api/ti/demandas/{ID_INEXISTENTE}/agent-context/', None, 'demanda_not_found', id='agent-context'),
    pytest.param('get', f'/api/ti/demandas/{ID_INEXISTENTE}/subdemandas/', None, 'demanda_not_found', id='subdemandas'),
    pytest.param('get', f'/api/ti/demandas/{ID_INEXISTENTE}/mr-status/', None, 'demanda_not_found', id='mr-status'),
    pytest.param('post', f'/api/ti/demandas/{ID_INEXISTENTE}/merge-request/', None, 'demanda_not_found', id='merge-request'),
    pytest.param(
        'post',
        f'/api/ti/demandas/{ID_INEXISTENTE}/spec-decisions/',
        {'decisao': 'Usar a autenticação padrão da API.'},
        'demanda_not_found',
        id='spec-decisions',
    ),
    pytest.param(
        'post',
        f'/api/ti/demandas/{ID_INEXISTENTE}/revisoes-especificacao/',
        {'nome': 'Nova', 'atividades': 'x'},
        'demanda_not_found',
        id='revisoes-especificacao-post',
    ),
    pytest.param('get', f'/api/ti/demandas/{ID_INEXISTENTE}/revisoes-especificacao/', None, 'demanda_not_found', id='revisoes-especificacao-get'),
    pytest.param('get', f'/api/ti/demandas/by-mr/?mr_iid={ID_INEXISTENTE}', None, 'demanda_not_found', id='by-mr'),
    pytest.param('get', f'/api/ti/entregas/{ID_INEXISTENTE}/pipeline-status/', None, 'entrega_not_found', id='pipeline-status'),
]


@pytest.fixture
def dono_da_aplicacao(db):
    return UserFactory()


@pytest.fixture
def token_client_credentials(dono_da_aplicacao):
    """Access token emitido por ``/o/token/`` no grant ``client_credentials`` (sem usuário no token)."""
    Application = get_application_model()
    aplicacao = Application.objects.create(
        name='suap-mcp',
        user=dono_da_aplicacao,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )
    token = get_access_token_model().objects.create(
        user=None,
        application=aplicacao,
        token='token-client-credentials',
        expires=timezone.now() + timedelta(hours=1),
        scope='read write',
    )
    return token.token


@pytest.fixture
def token_jwt(dono_da_aplicacao):
    return str(JWTAccessToken.for_user(dono_da_aplicacao))


def _chamar(client, metodo, url, corpo, token=None):
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
    if metodo == 'post':
        return client.post(url, data=json.dumps(corpo or {}), content_type='application/json', **headers)
    return client.get(url, **headers)


@pytest.mark.parametrize(('metodo', 'url', 'corpo', 'erro'), ENDPOINTS)
def test_aceita_token_oauth2_client_credentials(client, token_client_credentials, metodo, url, corpo, erro):
    response = _chamar(client, metodo, url, corpo, token_client_credentials)

    assert response.status_code == 404, response.content
    assert response.json()['error'] == erro


@pytest.mark.parametrize(('metodo', 'url', 'corpo', 'erro'), ENDPOINTS)
def test_aceita_jwt(client, token_jwt, metodo, url, corpo, erro):
    response = _chamar(client, metodo, url, corpo, token_jwt)

    assert response.status_code == 404, response.content
    assert response.json()['error'] == erro


@pytest.mark.parametrize(('metodo', 'url', 'corpo', 'erro'), ENDPOINTS)
def test_recusa_sem_credencial(client, db, metodo, url, corpo, erro):
    response = _chamar(client, metodo, url, corpo)

    assert response.status_code == 401


def test_subdemandas_com_token_oauth2_lista_as_filhas_sem_paginar(client, dono_da_aplicacao, token_client_credentials):
    """O token ``client_credentials`` age como o dono da aplicação, que precisa poder ver a demanda."""
    dono_da_aplicacao.user_permissions.add(Permission.objects.get(codename='view_demanda', content_type__app_label='demandas'))
    pai = DemandaFactory()
    filhas = [DemandaFactory(parent=pai, prioridade_interna=ordem) for ordem in (1, 2)]

    response = _chamar(client, 'get', f'/api/ti/demandas/{pai.pk}/subdemandas/', None, token_client_credentials)

    assert response.status_code == 200, response.content
    assert [item['id'] for item in response.json()] == [filha.pk for filha in filhas]
