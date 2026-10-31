"""Leitura do ambiente de homologação da demanda pela API (/api/ti/demandas/{id}/ambiente-homologacao/).

É o que o suap-mcp consulta para acompanhar o ambiente: o registro no SUAP mais a situação do job
``deploy-suapdev``, lida no GitLab na hora. O GitLab é a fronteira externa, então é ele que é falso
aqui, no nível do ``requests``; o modelo e o endpoint rodam de verdade. A senha nunca sai: ela entra
no ambiente como qualquer usuário.
"""

from __future__ import annotations

import re
from unittest import mock

import pytest
import requests
from django.contrib.auth.models import Permission
from ninja_jwt.tokens import AccessToken

from comum.tests.factories import UserFactory
from demandas.models.demanda import Situacao
from demandas.tests.factories import AmbienteHomologacaoFactory, DemandaFactory, EntregaFactory

# `AnalistaDesenvolvedor.save()` busca o grupo 'Analista'.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('sync_permissions')]

LOG_SYNC = '$ docker run ...\n$ createdb -U postgres ...\n$ git pull origin ...\n$ python manage.py sync\n'


class Resposta:
    def __init__(self, dados: object = None, texto: str = '') -> None:
        self.dados, self.text = dados, texto

    def json(self) -> object:
        return self.dados


class GitlabFalso:
    """Um pipeline com o job de deploy no ``status`` dado; ``fora_do_ar`` faz toda chamada falhar."""

    def __init__(self, status: str = 'manual', log: str = '', fora_do_ar: bool = False) -> None:
        self.status, self.log, self.fora_do_ar = status, log, fora_do_ar

    def get(self, url: str, **kwargs) -> Resposta:
        if self.fora_do_ar:
            raise requests.ConnectionError('GitLab fora do ar')
        if re.search(r'/pipelines/\d+/jobs', url):
            return Resposta([{'id': 77, 'name': 'deploy-suapdev', 'status': self.status, 'web_url': 'https://gitlab.exemplo/-/jobs/77'}])
        if url.endswith('/jobs/77/trace'):
            return Resposta(texto=self.log)
        raise AssertionError(f'GET inesperado: {url}')


@pytest.fixture
def gitlab_falso():
    def _com(**kwargs) -> GitlabFalso:
        falso = GitlabFalso(**kwargs)
        patcher = mock.patch('djtools.utils.gitlab.requests', falso)
        patcher.start()
        patches.append(patcher)
        return falso

    patches: list = []
    yield _com
    for p in patches:
        p.stop()


@pytest.fixture
def leitor(db):
    user = UserFactory()
    user.user_permissions.add(Permission.objects.get(codename='view_demanda', content_type__app_label='demandas'))
    return user


def _get(client, user, demanda_id):
    return client.get(f'/api/ti/demandas/{demanda_id}/ambiente-homologacao/', HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(user)}')


def test_ambiente_em_deploy_mostra_a_etapa_do_log_e_nunca_a_senha(client, leitor, gitlab_falso):
    gitlab_falso(status='running', log=LOG_SYNC)
    ambiente = AmbienteHomologacaoFactory(branch='demanda_42', senha='s3gr3d0', ativo=True)
    demanda = EntregaFactory(demanda__situacao=Situacao.ESTADO_EM_HOMOLOGACAO, ambiente_homologacao=ambiente).demanda

    response = _get(client, leitor, demanda.pk)

    assert response.status_code == 200, response.content
    corpo = response.json()
    assert corpo['demanda_id'] == demanda.pk
    assert (corpo['id'], corpo['branch'], corpo['pipeline_id'], corpo['ativo']) == (ambiente.pk, 'demanda_42', ambiente.pipeline, True)
    assert corpo['criador'] == ambiente.criador.usuario.username
    assert corpo['url'] == ambiente.get_url_homologacao()
    assert corpo['deploy'] == {
        'status': 'running',
        'job_url': 'https://gitlab.exemplo/-/jobs/77',
        'progresso': 75,
        'etapa': 'Executando o comando sync.',
    }
    assert 'senha' not in corpo
    assert 's3gr3d0' not in response.content.decode()


def test_ambiente_ainda_nao_implantado_nao_tem_url_nem_etapa(client, leitor, gitlab_falso):
    gitlab_falso(status='manual')
    demanda = EntregaFactory(ambiente_homologacao=AmbienteHomologacaoFactory(ativo=False)).demanda

    corpo = _get(client, leitor, demanda.pk).json()

    assert corpo['url'] is None
    assert corpo['deploy'] == {'status': 'manual', 'job_url': 'https://gitlab.exemplo/-/jobs/77', 'progresso': None, 'etapa': None}


def test_gitlab_fora_do_ar_ainda_devolve_o_registro(client, leitor, gitlab_falso):
    gitlab_falso(fora_do_ar=True)
    demanda = EntregaFactory(ambiente_homologacao=AmbienteHomologacaoFactory()).demanda

    response = _get(client, leitor, demanda.pk)

    assert response.status_code == 200, response.content
    assert response.json()['deploy'] is None


def test_demanda_sem_ambiente_responde_404(client, leitor):
    demanda = DemandaFactory()

    response = _get(client, leitor, demanda.pk)

    assert response.status_code == 404
    assert response.json()['error'] == 'ambiente_not_found'


def test_usuario_que_nao_ve_demandas_responde_403(client, gitlab_falso):
    gitlab_falso()
    demanda = EntregaFactory(ambiente_homologacao=AmbienteHomologacaoFactory()).demanda

    response = _get(client, UserFactory(), demanda.pk)

    assert response.status_code == 403
    assert response.json()['error'] == 'permission_denied'
