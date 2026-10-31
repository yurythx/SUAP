"""Confere e alinha o histórico de migrações com o esquema já existente.

Uso, no suap-app, com o ambiente da aplicação::

    DATABASE_NAME=suap_migrate_prova python scripts/reconciliar_migracoes.py probe
    DATABASE_NAME=suap_migrate_prova python scripts/reconciliar_migracoes.py fake

``fake`` grava as migrações pendentes como aplicadas, sem executar SQL.
Só deve rodar no banco real depois que a cópia de ensaio passar em ``probe``.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')

import django

django.setup()

from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def pendentes() -> list[str]:
    executor = MigrationExecutor(connection)
    plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f'{migration.app_label}.{migration.name}' for migration, _backwards in plano]


def sondar_modelos() -> list[str]:
    falhas: list[str] = []
    for modelo in apps.get_models():
        if not modelo._meta.managed or modelo._meta.proxy:
            continue
        try:
            list(modelo.objects.all()[:1])
        except Exception as exc:  # noqa: BLE001 - a sonda registra qualquer falha de consulta
            falhas.append(f'{modelo._meta.label}: {type(exc).__name__}')
    return falhas


def main() -> None:
    acao = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    banco = connection.settings_dict['NAME']
    print(f'banco={banco}')
    antes = pendentes()
    print(f'pendentes={len(antes)}')
    if acao == 'probe':
        falhas = sondar_modelos()
        print(f'modelos_com_falha={len(falhas)}')
        for item in falhas[:40]:
            print(item)
        return
    if acao != 'fake':
        raise SystemExit('acao deve ser probe ou fake')
    if os.environ.get('CONFIRMAR_FAKE') != 'sim':
        raise SystemExit('Defina CONFIRMAR_FAKE=sim para gravar o histórico.')
    call_command('migrate', fake=True, interactive=False, verbosity=1)
    depois = pendentes()
    print(f'pendentes_depois={len(depois)}')
    falhas = sondar_modelos()
    print(f'modelos_com_falha={len(falhas)}')
    for item in falhas[:40]:
        print(item)
    if depois or falhas:
        raise SystemExit('o histórico ficou pendente ou algum modelo não consulta')
    call_command('migrate', interactive=False, verbosity=1)
    print('MIGRATE_FUTURO_OK')


if __name__ == '__main__':
    main()
