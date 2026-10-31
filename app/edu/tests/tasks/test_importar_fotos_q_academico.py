"""Importação de fotos do Q-Acadêmico (``edu_importar_fotos`` → ``DAO.atualizar_fotos``).

A fronteira externa é o SQL Server do Q-Acadêmico (``pymssql``): no lugar dele entra um SQLite em
memória com a mesma tabela ``FW_CONTEUDOS_BINARIOS``, então o laço roda contra um cursor DB-API de verdade.
"""

from __future__ import annotations

import io
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from PIL import Image

from edu import q_academico_fotos
from edu.models import Aluno
from edu.q_academico_fotos import DAO
from edu.tests.factories import AlunoFactory

pytestmark = pytest.mark.django_db

# Códigos altos, longe de qualquer aluno de dado legado commitado no banco do worker.
BASE = 9179900


def jpeg(cor: str) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (30, 40), cor).save(buffer, 'JPEG')
    return buffer.getvalue()


@pytest.fixture
def q_academico(monkeypatch):
    """Troca o ``pymssql`` por um SQLite em memória; devolve a função que carrega as fotos."""
    banco = sqlite3.connect(':memory:')
    banco.row_factory = lambda cursor, row: {col[0]: valor for col, valor in zip(cursor.description, row, strict=True)}
    banco.execute('CREATE TABLE FW_CONTEUDOS_BINARIOS (cod_conteudo_binario INTEGER, conteudo_binario BLOB, tipo_conteudo_binario INTEGER)')
    monkeypatch.setitem(sys.modules, 'pymssql', SimpleNamespace(connect=lambda **kwargs: banco))
    return lambda fotos: banco.executemany('INSERT INTO FW_CONTEUDOS_BINARIOS VALUES (?, ?, 0)', fotos)


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def test_cada_foto_chega_aos_alunos_do_seu_codigo(media, q_academico, monkeypatch, capsys):
    monkeypatch.setattr(q_academico_fotos, 'LOTE', 2)
    irmao_1 = AlunoFactory(codigo_academico_pf=BASE + 1)
    irmao_2 = AlunoFactory(codigo_academico_pf=BASE + 1)
    ja_tinha_foto = AlunoFactory(codigo_academico_pf=BASE + 3, foto='alunos/antiga.jpg')
    unico = AlunoFactory(codigo_academico_pf=BASE + 4)
    outro_codigo = AlunoFactory(codigo_academico_pf=BASE + 99)
    vermelha, azul, verde = jpeg('red'), jpeg('blue'), jpeg('green')
    # Lotes de 2: [+1, +2] [+3, +4] [+4]; o +2 não tem aluno e o +4 repete no lote seguinte.
    q_academico([(BASE + 1, vermelha), (BASE + 2, azul), (BASE + 3, azul), (BASE + 4, verde), (BASE + 4, azul)])

    with CaptureQueriesContext(connection) as contexto:
        call_command('edu_importar_fotos')

    assert '3' in capsys.readouterr().out.splitlines()  # o comando imprime o total de importados
    # Só a coluna foto é gravada: não sobrescreve edição concorrente feita depois da busca do lote.
    updates = [q['sql'] for q in contexto.captured_queries if q['sql'].startswith('UPDATE "edu_aluno"')]
    assert len(updates) == 3
    assert all(sql.startswith('UPDATE "edu_aluno" SET "foto" = ') and ', "' not in sql.split(' WHERE ')[0] for sql in updates)
    for aluno in (irmao_1, irmao_2):
        aluno.refresh_from_db()
        assert (media / aluno.foto.name).read_bytes() == vermelha
    unico.refresh_from_db()
    assert (media / unico.foto.name).read_bytes() == verde  # a 2ª foto do +4 não sobrescreve a 1ª
    assert Aluno.objects.get(pk=ja_tinha_foto.pk).foto.name == 'alunos/antiga.jpg'
    assert not Aluno.objects.get(pk=outro_codigo.pk).foto.name


@pytest.mark.parametrize('qtd_fotos', [3, 30])
def test_busca_de_alunos_nao_cresce_com_o_numero_de_fotos(media, q_academico, qtd_fotos):
    AlunoFactory(codigo_academico_pf=BASE + 1)
    q_academico([(BASE + i, jpeg('red')) for i in range(1, qtd_fotos + 1)])

    with CaptureQueriesContext(connection) as contexto:
        assert DAO().atualizar_fotos() == 1

    buscas = [q for q in contexto.captured_queries if 'WHERE "edu_aluno"."codigo_academico_pf"' in q['sql']]
    assert len(buscas) == 1
