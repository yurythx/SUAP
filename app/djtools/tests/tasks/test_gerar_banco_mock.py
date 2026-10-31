"""Testes da orquestração do ``manage.py gerar_banco_mock`` (sem subprocessos de verdade)."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import psycopg
import pytest
from comum.tests.factories import UserFactory
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from djtools import banco_mock
from djtools.management.commands import gerar_banco_mock as cmd

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'
ETAPAS = ('makemigrations', 'pytest', 'gerar_banco_mock', 'migrate', 'pg_dump')


def _etapa(comando: list[str]) -> str:
    return next(parte for parte in comando if parte in ETAPAS)


@pytest.fixture
def execucao(monkeypatch):
    registro = SimpleNamespace(chamadas=[], falhar=set(), dropados=[])

    def rodar(comando, **kwargs):
        registro.chamadas.append((comando, kwargs['env']))
        etapa = _etapa(comando)
        if etapa == 'pg_dump':
            Path(comando[comando.index('-f') + 1]).touch()  # simula pg_dump escrevendo, completo ou parcial
        return subprocess.CompletedProcess(comando, 1 if etapa in registro.falhar else 0)

    monkeypatch.setattr(cmd.subprocess, 'run', rodar)
    monkeypatch.setattr(cmd, 'checar_pg_dump', lambda: None)
    monkeypatch.setattr(cmd, 'dropar_banco', lambda: registro.dropados.append(cmd.BANCO))
    return registro


def test_orquestra_as_etapas_em_ordem_e_dropa(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    assert [_etapa(comando) for comando, _ in execucao.chamadas] == list(ETAPAS)
    assert execucao.dropados == [cmd.BANCO]


def test_filhos_nunca_apontam_para_o_banco_de_dev(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    comandos = {_etapa(comando): comando for comando, _ in execucao.chamadas}
    ambientes = {_etapa(comando): env for comando, env in execucao.chamadas}
    assert all(env['EMAIL_BACKEND'] == LOCMEM for env in ambientes.values())
    assert all(env['DJANGO_SETTINGS_MODULE'] == 'suap.settings_test' for env in ambientes.values())
    assert ambientes['makemigrations']['DATABASE_NAME'] == 'postgres'
    assert ambientes['pytest']['TEST_DATABASE_NAME'] == cmd.BANCO
    assert ambientes['pytest']['DATABASE_NAME'] == 'postgres'
    assert ambientes['gerar_banco_mock']['DATABASE_NAME'] == cmd.BANCO
    assert ambientes['migrate']['DATABASE_NAME'] == cmd.BANCO
    assert comandos['pg_dump'][-1] == cmd.BANCO


def test_seeds_rodam_so_os_stubs_pedidos(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    pytest_cmd = next(comando for comando, _ in execucao.chamadas if _etapa(comando) == 'pytest')
    assert pytest_cmd[-1].endswith('saude/tests/e2e/test_mock.py')
    assert {'-m', 'mock', '--create-db', '--reuse-db'} <= set(pytest_cmd)


def test_falha_nos_seeds_mantem_o_banco_e_nao_faz_dump(execucao, tmp_path):
    execucao.falhar.add('pytest')
    with pytest.raises(CommandError, match="etapa 'seeds' falhou"):
        call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', stdout=io.StringIO())
    assert 'pg_dump' not in [_etapa(comando) for comando, _ in execucao.chamadas]
    assert execucao.dropados == []


def test_sem_volume_repassa_a_flag(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', sem_volume=True, stdout=io.StringIO())
    volume = next(comando for comando, _ in execucao.chamadas if _etapa(comando) == 'gerar_banco_mock')
    assert '--sem-volume' in volume


def test_manter_banco_nao_dropa(execucao, tmp_path):
    call_command('gerar_banco_mock', saida=str(tmp_path / 'x.dump'), modulos='saude', manter_banco=True, stdout=io.StringIO())
    assert execucao.dropados == []


def test_pg_dump_escreve_em_tmp_e_promove_no_sucesso(execucao, tmp_path):
    saida = tmp_path / 'x.dump'
    call_command('gerar_banco_mock', saida=str(saida), modulos='saude', stdout=io.StringIO())
    pg_dump_cmd = next(comando for comando, _ in execucao.chamadas if _etapa(comando) == 'pg_dump')
    assert pg_dump_cmd[pg_dump_cmd.index('-f') + 1] == f'{saida}.tmp'
    assert saida.exists()
    assert not saida.with_name(f'{saida.name}.tmp').exists()


def test_pg_dump_falho_preserva_dump_anterior_e_limpa_o_tmp(execucao, tmp_path):
    saida = tmp_path / 'x.dump'
    saida.write_bytes(b'dump anterior bom')
    execucao.falhar.add('pg_dump')
    with pytest.raises(CommandError, match="etapa 'pg_dump' falhou"):
        call_command('gerar_banco_mock', saida=str(saida), modulos='saude', stdout=io.StringIO())
    assert saida.read_bytes() == b'dump anterior bom'
    assert not saida.with_name(f'{saida.name}.tmp').exists()


def test_modulo_sem_stub_e_recusado(execucao):
    with pytest.raises(CommandError, match='módulo sem stub'):
        call_command('gerar_banco_mock', modulos='nao_existe', stdout=io.StringIO())
    assert execucao.chamadas == []


def test_todos_os_stubs_por_padrao():
    # Cada módulo com suíte e2e (diretório com conftest.py) precisa do próprio stub de seed;
    # sem isso o módulo fica de fora do dump em silêncio.
    diretorios_com_e2e = {caminho.parent for caminho in Path(settings.BASE_DIR).glob('*/tests/e2e/conftest.py')}
    sem_stub = [str(diretorio) for diretorio in diretorios_com_e2e if not (diretorio / 'test_mock.py').exists()]
    assert not sem_stub, f'módulos com e2e mas sem stub de seed: {sorted(sem_stub)}'
    assert cmd.caminhos_dos_stubs('') == sorted(diretorio / 'test_mock.py' for diretorio in diretorios_com_e2e)


def test_etapa_volume_recusa_banco_que_nao_e_mock():
    with pytest.raises(CommandError, match='não é o banco mockado'):
        call_command('gerar_banco_mock', etapa='volume', stdout=io.StringIO())


@pytest.mark.django_db
def test_etapa_volume_sem_volume_so_redefine_senhas(monkeypatch):
    UserFactory()
    monkeypatch.setattr(banco_mock, 'exigir_banco_mock', lambda nome: None)

    def nao_chamar(*args, **kwargs):
        raise AssertionError('gerar_volume não deveria rodar com --sem-volume')

    monkeypatch.setattr(banco_mock, 'gerar_volume', nao_chamar)
    saida = io.StringIO()
    call_command('gerar_banco_mock', etapa='volume', sem_volume=True, stdout=saida)
    assert "Senha '123' definida para" in saida.getvalue()


@pytest.mark.django_db
def test_etapa_volume_recria_trigger_das_migrations(monkeypatch):
    """A etapa `volume` roda com o schema montado por models (`--no-migrations`), que não vê o
    `RunSQL` de `documento_eletronico`/0029; sem recriação, um restore do dump ficaria sem o
    trigger `check_identificador`. Derruba o trigger antes (DDL é transacional no Postgres; o
    `django_db` desfaz no fim, sem vazar para outros testes) para provar que quem o recria é a
    etapa, não um resquício de outro teste.
    """
    monkeypatch.setattr(banco_mock, 'exigir_banco_mock', lambda nome: None)
    with connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER IF EXISTS check_identificador ON documento_eletronico_documentotexto')
    call_command('gerar_banco_mock', etapa='volume', sem_volume=True, stdout=io.StringIO())
    with connection.cursor() as cursor:
        cursor.execute("select 1 from pg_trigger where tgname = 'check_identificador'")
        assert cursor.fetchone() is not None


def test_major_extrai_o_numero_maior_da_versao() -> None:
    assert cmd._major('pg_dump (PostgreSQL) 18.6 (Ubuntu 18.6-1.pgdg24.04+2)') == 18


def test_major_sem_numero_e_recusado() -> None:
    with pytest.raises(CommandError, match='versão ilegível'):
        cmd._major('sem número')


def test_checar_pg_dump_recusa_conexao_recusada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmd.shutil, 'which', lambda _: '/usr/bin/pg_dump')
    monkeypatch.setattr(cmd.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, stdout='pg_dump (PostgreSQL) 18.6'))

    def recusar(*args, **kwargs):
        raise psycopg.OperationalError('conexão recusada')

    monkeypatch.setattr(cmd.psycopg, 'connect', recusar)
    with pytest.raises(CommandError, match='não foi possível conectar'):
        cmd.checar_pg_dump()


def test_checar_pg_dump_recusa_cliente_mais_antigo_que_o_servidor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmd.shutil, 'which', lambda _: '/usr/bin/pg_dump')
    monkeypatch.setattr(cmd.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess([], 0, stdout='pg_dump (PostgreSQL) 16.3'))

    class _Info:
        server_version = 180000

    class _Conexao:
        info = _Info()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(cmd, '_conectar', _Conexao)
    with pytest.raises(CommandError, match='mais antigo'):
        cmd.checar_pg_dump()
