"""Infraestrutura comum aos testes de service do ``comum``.

Os services de API externa (``comum/services/``) são construídos a partir de
``APIExterna.<NOME>``, e esse acesso passa pelo ``APIExternaMeta.__getattr__``, que
consulta banco e cache. Como o que se quer testar é a conversa HTTP, e não o cadastro da
API, os testes instanciam o service com ``__new__`` (pulando o ``__init__``) e injetam
uma configuração falsa — o mesmo caminho já usado por ``test_cad_unico.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def api_externa_falsa() -> Callable[..., SimpleNamespace]:
    """Devolve um construtor de ``APIExterna`` falso, com as constantes de autenticação.

    Cada chamada recebe um ``nome`` distinto por padrão, porque o nome vira a chave de
    cache do token (``TOKEN_API_EXTERNA_<nome>``): dois testes com o mesmo nome
    contaminariam um ao outro conforme a ordem de execução.
    """
    contador = iter(range(1000))

    def construir(**overrides: Any) -> SimpleNamespace:
        config = {
            'CONECTA_AUTH': 'CONECTA',
            'DATAPREV_AUTH': 'DATAPREV',
            'CLIENT_CREDENTIALS_AUTH': 'OAUTH2_CLIENT_CREDENTIALS',
            'API_KEY_AUTH': 'API KEY',
            'BASIC_AUTH': 'BASIC AUTH',
            'CPF_AUTH': 'CPF AUTH',
            'TOKEN_AUTH': 'TOKEN_AUTH',
            'nome': f'API_FALSA_{next(contador)}',
            'url_base': 'https://api.exemplo.gov.br',
            'url_token': 'https://api.exemplo.gov.br/oauth/token',
            'endpoint': '/v1/dados/',
            'tipo_autenticacao': 'CONECTA',
            'client_id': 'cliente',
            'secret': 'segredo',
            'headers': {},
            'cpf_operador': '12345678901',
            'dias_para_expirar': 1,
            'usuario_responsavel': None,
        }
        config.update(overrides)
        return SimpleNamespace(**config)

    return construir


@pytest.fixture
def montar_service(api_externa_falsa: Callable[..., SimpleNamespace]) -> Callable[..., Any]:
    """Instancia um service de API externa sem tocar em banco, cache ou ``__init__``."""

    def construir(classe: type, **overrides: Any) -> Any:
        service = classe.__new__(classe)
        service.api_externa = api_externa_falsa(**overrides)
        service.cache_name = f'TOKEN_API_EXTERNA_{service.api_externa.nome.lower()}'
        service.cpf_operador = service.api_externa.cpf_operador
        service.timeout = 30
        return service

    return construir
