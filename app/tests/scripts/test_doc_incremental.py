"""Checagem da seleção incremental do ``gerar-doc`` (``bin/scripts/doc_incremental.py``), sem git e sem rede."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import doc_incremental

ATUAIS = {'ae': 'a2', 'edu': 'e2', 'saude': 's1'}
ANTERIORES = {'ae': 'a1', 'edu': 'e1', 'saude': 's1', 'removido': 'r1'}


def test_sem_pedido_regera_so_quem_mudou_ou_nao_tem_registro() -> None:
    assert doc_incremental.selecionar('', ATUAIS, ANTERIORES) == ['ae', 'edu']
    assert doc_incremental.selecionar('', ATUAIS, {}) == ['ae', 'edu', 'saude']


def test_pedido_explicito_ignora_a_impressao() -> None:
    assert doc_incremental.selecionar('todos', ATUAIS, ANTERIORES) == ['ae', 'edu', 'saude']
    assert doc_incremental.selecionar(' saude , saude', ATUAIS, ANTERIORES) == ['saude']


def test_pedido_com_modulo_sem_doc_aborta() -> None:
    with pytest.raises(SystemExit, match='sadue'):
        doc_incremental.selecionar('edu,sadue', ATUAIS, ANTERIORES)


def test_manifesto_so_atualiza_quem_rodou() -> None:
    # `ae` mudou mas ficou fora do pedido: mantém a impressão antiga e volta na próxima rodada.
    novo = doc_incremental.manifesto_novo(ATUAIS, ANTERIORES, ['edu'])
    assert novo == {'ae': 'a1', 'edu': 'e2', 'saude': 's1'}
    assert doc_incremental.selecionar('', ATUAIS, novo) == ['ae']
