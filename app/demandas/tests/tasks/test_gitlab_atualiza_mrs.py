"""Comando ``gitlab_atualiza_mrs``, chamado pelo ``sync`` a cada deploy (fora de DEBUG)."""

from __future__ import annotations

import json
from io import StringIO
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest import mock

import pytest
import requests
from django.core.management import call_command

from comum.models import Configuracao

pytestmark = pytest.mark.django_db

PRODUCTION = 'state: Production'


class GitlabFalso:
    """Servidor GitLab mínimo: lista MRs ``merged`` sem o label, paginando por offset como o real."""

    POR_PAGINA = 2

    def __init__(self, total: int) -> None:
        self.mrs = {iid: {'id': iid, 'iid': iid, 'project_id': 8, 'state': 'merged', 'labels': []} for iid in range(1, total + 1)}

    def responder(self, request: requests.PreparedRequest, **kwargs) -> requests.Response:
        url = urlsplit(request.url)
        caminho = url.path.removeprefix('/api/v4')
        if request.method == 'GET' and caminho == '/projects/8':
            return self._resposta({'id': 8})
        if request.method == 'GET' and caminho == '/projects/8/merge_requests':
            return self._listar(url, parse_qs(url.query))
        if request.method == 'PUT' and caminho.startswith('/projects/8/merge_requests/'):
            mr = self.mrs[int(caminho.rsplit('/', 1)[1])]
            labels = json.loads(request.body)['labels']
            mr['labels'] = labels.split(',') if isinstance(labels, str) else labels
            return self._resposta(mr)
        raise AssertionError(f'Requisição inesperada: {request.method} {request.url}')

    def _listar(self, url, params: dict[str, list[str]]) -> requests.Response:
        pendentes = [mr for mr in self.mrs.values() if PRODUCTION not in mr['labels']]
        pagina = int(params.get('page', ['1'])[0])
        inicio = (pagina - 1) * self.POR_PAGINA
        headers = {}
        if inicio + self.POR_PAGINA < len(pendentes):
            proxima = {chave: valores[0] for chave, valores in params.items()} | {'page': pagina + 1}
            headers['Link'] = f'<{url.scheme}://{url.netloc}{url.path}?{urlencode(proxima)}>; rel="next"'
        return self._resposta(pendentes[inicio : inicio + self.POR_PAGINA], headers)

    @staticmethod
    def _resposta(corpo, headers: dict[str, str] | None = None) -> requests.Response:
        resposta = requests.Response()
        resposta.status_code = 200
        resposta._content = json.dumps(corpo).encode()
        resposta.headers.update({'Content-Type': 'application/json', **(headers or {})})
        return resposta


@pytest.fixture
def gitlab_configurado():
    for chave, valor in (('gitlab_url', 'https://gitlab.exemplo'), ('gitlab_token', 'token'), ('gitlab_suap_id', '8')):
        Configuracao.objects.update_or_create(app='demandas', chave=chave, defaults={'valor': valor})
    Configuracao.clear_cache()
    yield
    # O cache sobrevive ao rollback: sem limpar, os testes seguintes enxergariam o GitLab configurado.
    Configuracao.clear_cache()


@pytest.mark.usefixtures('gitlab_configurado')
def test_gitlab_fora_do_ar_nao_derruba_o_comando() -> None:
    """#17448: o python-gitlab deixa o ``ConnectionError`` do ``requests`` escapar cru, e o embutido não o captura."""
    erros = StringIO()

    with mock.patch('requests.Session.send', side_effect=requests.exceptions.ConnectionError('GitLab fora do ar')) as send:
        call_command('gitlab_atualiza_mrs', stderr=erros)

    assert send.called
    assert 'Problema de conexão com o gitlab.' in erros.getvalue()


@pytest.mark.usefixtures('gitlab_configurado')
def test_rotula_todos_os_mrs_merged_alem_da_primeira_pagina() -> None:
    gitlab = GitlabFalso(total=7)

    with mock.patch('requests.Session.send', side_effect=gitlab.responder):
        call_command('gitlab_atualiza_mrs')

    assert all(PRODUCTION in mr['labels'] for mr in gitlab.mrs.values())
