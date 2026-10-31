"""Gera um dump (``pg_dump -Fc``) de um banco SUAP inteiro com dados fictícios.

Guia: ``docs/banco-mock.md``. Desenho: ``docs/superpowers/specs/2026-09-19-banco-mock-design.md``.

O processo que o dev chama só orquestra. Toda etapa que escreve roda num processo filho
sob ``suap.settings_test`` apontado para ``BANCO`` — nunca para o banco de desenvolvimento —
e com e-mail em memória (fora do pytest o ``settings_test`` herda o SMTP do ``.env``).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any  # fronteira com o parser do Django: options é dict não tipado

import psycopg
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from comum.management.commands.create_db import criar_objetos_sql_das_migrations
from djtools import banco_mock
from djtools.management.commands import BaseCommandPlus

BANCO = f'test_suap{banco_mock.SUFIXO_BANCO}'
LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


def parametros_pg() -> dict[str, str]:
    """Conexão com as mesmas variáveis e defaults de ``suap/settings_test.py``."""
    return {
        'host': os.environ.get('DATABASE_HOST', '127.0.0.1'),
        'port': os.environ.get('DATABASE_PORT', '5432'),
        'user': os.environ.get('DATABASE_USER', 'postgres'),
        'password': os.environ.get('DATABASE_PASSWORD', ''),
    }


def _conectar() -> psycopg.Connection:
    """Conexão ao banco de manutenção ``postgres`` (nunca ao de dev nem ao mockado)."""
    pg = parametros_pg()
    try:
        return psycopg.connect(dbname='postgres', autocommit=True, host=pg['host'], port=pg['port'], user=pg['user'], password=pg['password'])
    except psycopg.OperationalError as erro:
        raise CommandError(f'não foi possível conectar a {pg["host"]}:{pg["port"]}: {erro}') from erro


def caminhos_dos_stubs(modulos: str) -> list[Path]:
    """Stubs de seed dos módulos pedidos (vírgula); vazio = todos os que existem."""
    base = Path(settings.BASE_DIR)
    if not modulos:
        return sorted(base.glob('*/tests/e2e/test_mock.py'))
    caminhos = [base / nome.strip() / 'tests' / 'e2e' / 'test_mock.py' for nome in modulos.split(',') if nome.strip()]
    faltando = [str(caminho.relative_to(base)) for caminho in caminhos if not caminho.exists()]
    if faltando:
        raise CommandError(f'módulo sem stub de seed: {", ".join(faltando)}')
    return caminhos


def _major(versao: str) -> int:
    achado = re.search(r'\d+', versao)
    if achado is None:
        raise CommandError(f'versão ilegível: {versao!r}')
    return int(achado.group())


def checar_pg_dump() -> None:
    """``pg_dump`` no PATH e com major ≥ o do servidor (falha antes dos ~3 min de seeds)."""
    if shutil.which('pg_dump') is None:
        raise CommandError('pg_dump não está no PATH; instale o postgresql-client da mesma versão do servidor.')
    try:
        versao = subprocess.run(['pg_dump', '--version'], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as erro:
        raise CommandError(f'pg_dump --version falhou (código {erro.returncode}): {erro.stderr}') from erro
    cliente = _major(versao.stdout)
    with _conectar() as conexao:
        servidor = conexao.info.server_version // 10000
    if cliente < servidor:
        raise CommandError(f'pg_dump {cliente} é mais antigo que o servidor PostgreSQL {servidor}.')


def dropar_banco() -> None:
    with _conectar() as conexao:
        conexao.execute(f'DROP DATABASE IF EXISTS "{BANCO}" WITH (FORCE)')


class Command(BaseCommandPlus):
    help = 'Gera um dump de um banco SUAP inteiro com dados fictícios (seeds e2e + volume sintético).'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--saida', default='suap_mock.dump', help='arquivo de saída (pg_dump -Fc)')
        parser.add_argument('--volume', type=int, default=20, help='instâncias sintéticas por model')
        parser.add_argument('--semente', type=int, default=0, help='semente do random (reprodutibilidade)')
        parser.add_argument('--sem-volume', action='store_true', help='só o substrato dos seeds, sem bakery')
        parser.add_argument('--modulos', default='', help='módulos separados por vírgula; vazio = todos com stub')
        parser.add_argument('--manter-banco', action='store_true', help=f'não dropa {BANCO} ao fim')
        parser.add_argument('--etapa', choices=['volume'], help=argparse.SUPPRESS)

    def handle(self, *args: str, **options: Any) -> None:
        if options['etapa'] == 'volume':
            self._etapa_volume(options)
        else:
            self._orquestrar(options)

    def _etapa_volume(self, options: dict[str, Any]) -> None:
        """Roda no filho, já conectado a ``BANCO``."""
        banco_mock.exigir_banco_mock(connection.settings_dict['NAME'])
        criar_objetos_sql_das_migrations()  # trigger/função de RunSQL que o schema por models não vê
        if not options['sem_volume']:
            resultados = banco_mock.gerar_volume(banco_mock.modelos_do_suap(), options['volume'], options['semente'])
            self.stdout.write(banco_mock.formatar_relatorio(resultados, options['volume']))
        total = banco_mock.redefinir_senhas()
        self.stdout.write(f'Senha {banco_mock.SENHA!r} definida para {total} usuários.')

    def _orquestrar(self, options: dict[str, Any]) -> None:
        stubs = caminhos_dos_stubs(options['modulos'])
        checar_pg_dump()
        manage = [sys.executable, 'manage.py']
        self._rodar('makemigrations --check', [*manage, 'makemigrations', '--check', '--dry-run'], DATABASE_NAME='postgres')
        seeds = [sys.executable, '-m', 'pytest', '-m', 'mock', '-n', '0', '-p', 'no:randomly', '--create-db', '--reuse-db', *map(str, stubs)]
        self._rodar('seeds', seeds, DATABASE_NAME='postgres', TEST_DATABASE_NAME=BANCO)
        volume = [*manage, 'gerar_banco_mock', '--etapa', 'volume', '--volume', str(options['volume']), '--semente', str(options['semente'])]
        self._rodar('volume', volume + (['--sem-volume'] if options['sem_volume'] else []), DATABASE_NAME=BANCO)
        self._rodar('migrate --fake', [*manage, 'migrate', '--fake'], DATABASE_NAME=BANCO)
        saida = Path(options['saida']).resolve()
        temporario = saida.with_name(saida.name + '.tmp')
        pg = parametros_pg()
        dump = ['pg_dump', '-Fc', '-h', pg['host'], '-p', pg['port'], '-U', pg['user'], '-f', str(temporario), BANCO]
        try:
            self._rodar('pg_dump', dump, PGPASSWORD=pg['password'])
        except CommandError:
            temporario.unlink(missing_ok=True)  # pg_dump pode deixar arquivo parcial; nunca sobrescreve o dump bom anterior
            raise
        os.replace(temporario, saida)
        if not options['manter_banco']:
            dropar_banco()
        self.stdout.write(f'Dump gerado em {saida}. Restaure com: createdb suap_mock && pg_restore -d suap_mock --no-owner {saida}')

    def _rodar(self, nome: str, comando: list[str], **ambiente: str) -> None:
        """Processo filho com saída no terminal; código ≠ 0 aborta mantendo o banco."""
        self.stdout.write(f'>>> {nome}')
        self.stdout.flush()  # sem isto o '>>> etapa' sai depois da saída do filho
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'suap.settings_test', 'EMAIL_BACKEND': LOCMEM, **ambiente}
        codigo = subprocess.run(comando, cwd=settings.BASE_DIR, env=env, check=False).returncode
        if codigo != 0:
            raise CommandError(f'etapa {nome!r} falhou (código {codigo}); {BANCO}, se já criado, foi mantido para inspeção (dropdb {BANCO}).')
