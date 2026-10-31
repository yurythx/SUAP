"""Garante que as migrations de remoção de fantasmas só apagam o que nenhum model conhece."""

import importlib

import pytest
from django.apps import apps

MIGRACOES = [
    'ae.migrations.0047_remover_fantasmas_pessoa',
    'cnpq.migrations.0010_remover_fantasmas_pessoa',
    'convenios.migrations.0007_remover_fantasmas_pessoa',
    'documento_eletronico.migrations.0041_remover_fantasmas_pessoa',
    'edu.migrations.0330_remover_fantasmas_pessoa',
    'estacionamento.migrations.0003_remover_fantasmas_pessoa',
    'frota.migrations.0008_remover_fantasmas_pessoa',
    'pesquisa.migrations.0089_remover_fantasmas_pessoa',
    'ponto.migrations.0026_remover_fantasmas_pessoa',
    'processo_eletronico.migrations.0050_remover_fantasmas_pessoa',
    'projetos.migrations.0075_remover_fantasmas_pessoa',
    'saude.migrations.0039_remover_fantasmas_pessoa',
]


def _colunas_e_tabelas_vivas() -> tuple[set[tuple[str, str]], set[str]]:
    colunas, tabelas = set(), set()
    for model in apps.get_models(include_auto_created=True):
        tabelas.add(model._meta.db_table)
        for campo in model._meta.local_fields:
            colunas.add((model._meta.db_table, campo.column))
    return colunas, tabelas


@pytest.mark.parametrize('caminho', MIGRACOES)
def test_fantasma_nao_e_coluna_nem_tabela_viva(caminho: str) -> None:
    migracao = importlib.import_module(caminho)
    colunas_vivas, tabelas_vivas = _colunas_e_tabelas_vivas()

    assert not set(migracao.COLUNAS) & colunas_vivas
    assert not set(migracao.TABELAS) & tabelas_vivas
