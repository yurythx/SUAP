"""Preflight de conectividade com o banco usado pelos fluxos de desenvolvimento.

Este módulo centraliza uma checagem simples e reutilizável de acesso ao banco
configurado em ``DATABASES['default']``. O objetivo é falhar cedo com
diagnóstico claro antes de entrar em etapas mais custosas como keepdb,
``runserver`` ou execução do Behave.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import connections


@dataclass(frozen=True)
class DatabaseAccessResult:
    alias: str
    host: str
    port: str
    name: str
    ok: bool
    message: str


class DatabaseAccessError(RuntimeError):
    """Erro lançado quando o preflight de banco falha."""


def _connection_target(alias: str = 'default') -> tuple[str, str, str]:
    connection = connections[alias]
    settings_dict = connection.settings_dict
    host = str(settings_dict.get('HOST') or 'localhost')
    port = str(settings_dict.get('PORT') or '')
    name = str(settings_dict.get('NAME') or alias)
    return host, port, name


def check_database_access(alias: str = 'default') -> DatabaseAccessResult:
    """Testa abertura da conexão Django para o alias informado."""

    connection = connections[alias]
    host, port, name = _connection_target(alias)
    try:
        connection.ensure_connection()
    except Exception as exc:  # pragma: no cover - depende de ambiente externo
        message = f'Falha ao conectar no banco "{name}" em {host}:{port or "default"}: {exc}'
        return DatabaseAccessResult(alias=alias, host=host, port=port, name=name, ok=False, message=message)
    finally:
        connection.close()
    message = f'Conexão com banco "{name}" em {host}:{port or "default"} validada com sucesso.'
    return DatabaseAccessResult(alias=alias, host=host, port=port, name=name, ok=True, message=message)


def build_database_access_error(result: DatabaseAccessResult, *, purpose: str) -> str:
    tips = []
    if result.host == 'vpn':
        tips.append('Valide se o serviço `vpn` está ativo e se a rota para o PostgreSQL remoto está funcional.')
    elif result.host in {'localhost', '127.0.0.1'}:
        tips.append('Valide se a porta publicada no host corresponde ao mapeamento do `docker compose`.')
    tips.append('Confira `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER` e `DATABASE_PASSWORD` no ambiente em uso.')
    tips_text = '\n'.join(f'- {tip}' for tip in tips)
    return (
        f'[{purpose}] Preflight de banco falhou.\n'
        f'- Alias: {result.alias}\n'
        f'- Host: {result.host}\n'
        f'- Porta: {result.port or "default"}\n'
        f'- Banco: {result.name}\n'
        f'- Erro: {result.message}\n'
        f'{tips_text}'
    )


def ensure_database_access(*, alias: str = 'default', purpose: str = 'db_preflight') -> DatabaseAccessResult:
    """Executa o preflight e lança erro detalhado em caso de falha."""

    result = check_database_access(alias=alias)
    if not result.ok:
        raise DatabaseAccessError(build_database_access_error(result, purpose=purpose))
    return result


def database_access_summary(alias: str = 'default') -> str:
    """Retorna resumo textual do alvo de conexão configurado."""

    host, port, name = _connection_target(alias)
    environment = getattr(settings, 'SUAP_ENVIRONMENT', 'unknown')
    return f'Ambiente={environment} alias={alias} banco={name} host={host} porta={port or "default"}'
