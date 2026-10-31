"""Fluxo da tarefa agendada que remove ambientes de homologação expirados (#17387 → banco órfão).

A remoção é um job ``destroy-suapdev`` disparado no GitLab. O defeito medido no florania: o
``play`` era recusado (job recém-criado ainda ``created``), ninguém conferia a resposta e o
ambiente virava inativo com o banco ``database-<branch>-suap`` ainda lá — e inativo nunca mais
entrava na fila. O GitLab é a fronteira externa, então é ele que é falso aqui, no nível do
``requests``; ``execute_job``, o modelo e o comando rodam de verdade.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import StringIO
from unittest import mock

import pytest
import requests
from django.core.management import call_command

from demandas.tests.factories import AmbienteHomologacaoFactory

# `AnalistaDesenvolvedor.save()` busca o grupo 'Analista': sem `sync_permissions` o teste só passava
# quando outro teste do mesmo worker xdist já tinha sincronizado os grupos.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('sync_permissions')]


class Resposta:
    def __init__(self, dados: object = None, status: int = 200) -> None:
        self.dados, self.status_code = dados, status
        self.ok = status < 400
        self.text = str(dados)

    def json(self) -> object:
        return self.dados


class GitlabFalso:
    """Pipelines com os três jobs de homologação; ``aceita_play`` decide a resposta do play."""

    def __init__(self, aceita_play: bool = True, status_inicial: str = 'manual') -> None:
        self.aceita_play = aceita_play
        self.status_inicial = status_inicial
        self.proximo_pipeline = 5000
        self.jobs: dict[int, dict[str, dict]] = {}
        self.disparos: list[tuple[int, str, str]] = []

    def pipeline(self, pipeline_id: int, destroy: str = 'manual') -> None:
        self.jobs[pipeline_id] = {
            nome: {'id': pipeline_id * 10 + i, 'name': nome, 'status': destroy if nome == 'destroy-suapdev' else 'manual', 'started_at': None}
            for i, nome in enumerate(('deploy-suapdev', 'undeploy-suapdev', 'destroy-suapdev'))
        }

    def get(self, url: str, **kwargs) -> Resposta:
        if m := re.search(r'/pipelines/(\d+)/jobs', url):
            return Resposta(list(self.jobs.get(int(m.group(1)), {}).values()))
        return Resposta({})

    def post(self, url: str, **kwargs) -> Resposta:
        if '/repository/branches' in url:
            return Resposta({'message': 'Branch already exists'})
        if '/pipeline?ref=' in url:
            self.proximo_pipeline += 1
            self.pipeline(self.proximo_pipeline, destroy=self.status_inicial)
            return Resposta({'id': self.proximo_pipeline, 'web_url': f'https://gitlab.exemplo/{self.proximo_pipeline}'})
        if m := re.search(r'/jobs/(\d+)/(play|retry)', url):
            job = next(j for js in self.jobs.values() for j in js.values() if j['id'] == int(m.group(1)))
            # Como o GitLab real: play só em job `manual`, retry só em job que já terminou.
            if m.group(2) == 'play' and (job['status'] != 'manual' or not self.aceita_play):
                return Resposta({'message': '400 Bad request - Unplayable Job'}, status=400)
            if m.group(2) == 'retry' and job['status'] not in ('success', 'failed', 'canceled'):
                return Resposta({'message': '403 Forbidden - Job is not retryable'}, status=403)
            job['status'] = 'pending'
            self.disparos.append((int(m.group(1)) // 10, job['name'], m.group(2)))
            return Resposta({'id': job['id'], 'status': 'pending'})
        raise AssertionError(f'POST inesperado: {url}')


@pytest.fixture
def gitlab_falso():
    def _com(**kwargs) -> GitlabFalso:
        falso = GitlabFalso(**kwargs)
        patches.append(mock.patch('djtools.utils.gitlab.requests', falso))
        patches[-1].start()
        return falso

    patches: list = [mock.patch('time.sleep')]
    patches[0].start()
    yield _com
    for p in patches:
        p.stop()


def _rodar() -> str:
    erros = StringIO()
    call_command('remover_ambientes_homolog_expirados', stderr=erros)
    return erros.getvalue()


def test_expirado_so_fica_inativo_se_o_gitlab_aceitar_o_destroy(gitlab_falso):
    ambiente = AmbienteHomologacaoFactory(data_expiracao=date.today() - timedelta(days=1))
    falso = gitlab_falso(aceita_play=False)

    erros = _rodar()

    ambiente.refresh_from_db()
    assert ambiente.ativo, 'destroy recusado não pode tirar o ambiente da fila'
    assert 'Unplayable Job' in erros

    falso.aceita_play = True
    _rodar()

    ambiente.refresh_from_db()
    assert not ambiente.ativo
    assert [(nome, acao) for _, nome, acao in falso.disparos] == [('destroy-suapdev', 'play')]


def test_espera_o_job_recem_criado_ficar_manual_antes_do_play(gitlab_falso):
    """O caso da corrida: o pipeline novo nasce com o destroy ``created``."""
    ambiente = AmbienteHomologacaoFactory(data_expiracao=date.today() - timedelta(days=1))
    falso = gitlab_falso(status_inicial='created')
    estados = iter(['created', 'manual'])
    get_original = falso.get

    def get_que_amadurece(url: str, **kwargs) -> Resposta:
        for jobs in falso.jobs.values():
            if jobs['destroy-suapdev']['status'] == 'created':
                jobs['destroy-suapdev']['status'] = next(estados, 'manual')
        return get_original(url, **kwargs)

    falso.get = get_que_amadurece

    _rodar()

    ambiente.refresh_from_db()
    assert not ambiente.ativo
    assert [nome for _, nome, _ in falso.disparos] == ['destroy-suapdev']


def test_remover_provisoriamente_e_depois_expirar_destroi_o_banco(gitlab_falso):
    """Undeploy deixa o banco; ao expirar, o inativo com destroy pendente é destruído."""
    falso = gitlab_falso()
    ambiente = AmbienteHomologacaoFactory()
    falso.pipeline(ambiente.pipeline)
    ambiente.excluir_container()
    assert not ambiente.ativo

    ambiente.data_expiracao = date.today() - timedelta(days=1)
    ambiente.save()
    _rodar()

    assert [nome for _, nome, _ in falso.disparos] == ['undeploy-suapdev', 'destroy-suapdev']

    _rodar()
    assert len(falso.disparos) == 2, 'destroy já disparado não pode ser repetido'


def test_inativo_fora_da_janela_nao_e_reprocessado(gitlab_falso):
    falso = gitlab_falso()
    ambiente = AmbienteHomologacaoFactory(ativo=False, data_expiracao=date.today() - timedelta(days=60))
    falso.pipeline(ambiente.pipeline)

    _rodar()

    assert falso.disparos == []


def test_falha_de_rede_ao_consultar_o_job_e_tolerada(gitlab_falso):
    """#17448: ``get_job`` só engolia o ``ConnectionError`` embutido, e o do ``requests`` abortava a remoção."""
    ambiente = AmbienteHomologacaoFactory(data_expiracao=date.today() - timedelta(days=1))
    falso = gitlab_falso()
    falhas = iter([requests.exceptions.ConnectionError('GitLab fora do ar')])
    get_original = falso.get

    def get_instavel(url: str, **kwargs) -> Resposta:
        if re.search(r'/pipelines/\d+/jobs', url) and (falha := next(falhas, None)):
            raise falha
        return get_original(url, **kwargs)

    falso.get = get_instavel

    _rodar()

    ambiente.refresh_from_db()
    assert not ambiente.ativo
    assert [(nome, acao) for _, nome, acao in falso.disparos] == [('destroy-suapdev', 'play')]
