"""O guard de banco do e2e barra a run ANTES de o banco ser criado e semeado (#17654).

Roda uma mini-suíte num pytest separado, montada como um conftest de e2e de verdade: só o
star-import diz se a fixture chegou ao conftest. Não basta o guard falhar — se ele rodar
depois do seed (o ``_verify_url`` autouse do pytest-base-url puxa ``live_server`` →
``e2e_seed``), o banco errado já levou o commit. Por isso a run usa ``--reuse-db`` (o banco
sobreviveria ao fim da sessão) e o teste confere que ele nem chegou a existir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from django.conf import settings

RAIZ_DO_REPO = Path(__file__).resolve().parents[3]
BANCO_UNITARIO = 'test_suap_guard_17654'


def _banco_existe(nome: str) -> bool:
    config = settings.DATABASES['default']
    with psycopg.connect(
        host=config['HOST'], port=config['PORT'], user=config['USER'], password=config['PASSWORD'], dbname='postgres', autocommit=True
    ) as conexao:
        if conexao.execute('SELECT 1 FROM pg_database WHERE datname = %s', (nome,)).fetchone():
            conexao.execute(f'DROP DATABASE "{nome}" WITH (FORCE)')  # limpa o estrago de uma regressão
            return True
    return False


def test_guard_aborta_a_run_e2e_antes_de_criar_o_banco_unitario(tmp_path: Path) -> None:
    (tmp_path / 'conftest.py').write_text('from djtools.e2e_fixtures import *  # noqa: F403\n')
    (tmp_path / 'test_mini.py').write_text('def test_nada():\n    pass\n')
    ambiente = {**os.environ, 'TEST_DATABASE_NAME': BANCO_UNITARIO, 'DJANGO_SETTINGS_MODULE': 'suap.settings_test', 'PYTHONPATH': str(RAIZ_DO_REPO)}

    processo = subprocess.run(
        [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-p', 'no:xdist', '--reuse-db', '--rootdir', str(tmp_path), str(tmp_path)],
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )

    saida = processo.stdout + processo.stderr
    assert processo.returncode != 0, saida
    assert f"banco de teste '{BANCO_UNITARIO}' não é de e2e" in saida, saida
    assert not _banco_existe(BANCO_UNITARIO), saida
