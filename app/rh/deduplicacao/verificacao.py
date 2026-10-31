"""Pré-verificação da Release 2 (constraints de documento). SQL puro: é importada pela migration rh/0111."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.backends.utils import CursorWrapper

CONSULTAS = {
    'cpf_repetido': 'SELECT count(*) FROM (SELECT cpf FROM pessoa_fisica WHERE cpf IS NOT NULL GROUP BY cpf HAVING count(*) > 1) g',
    'passaporte_repetido': (
        'SELECT count(*) FROM (SELECT pais_origem_id, passaporte FROM pessoa_fisica '
        'WHERE passaporte IS NOT NULL AND pais_origem_id IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1) g'
    ),
    'sem_cpf_sem_pais': (
        'SELECT count(*) FROM pessoa_fisica WHERE cpf IS NULL AND pais_origem_id IS NULL '
        "AND documento_identificador !~ '^(SEMDOC|SEMPAIS|CONFLITO|INVALIDO)-'"
    ),
    'documento_repetido': (
        'SELECT count(*) FROM (SELECT documento_identificador FROM pessoa_fisica '
        'WHERE documento_identificador IS NOT NULL GROUP BY documento_identificador HAVING count(*) > 1) g'
    ),
    'cpf_ou_passaporte_vazio': "SELECT count(*) FROM pessoa_fisica WHERE cpf = '' OR passaporte = ''",
    'sem_documento': "SELECT count(*) FROM pessoa_fisica WHERE documento_identificador IS NULL OR documento_identificador = ''",
    'info_complementar_repetida': (
        'SELECT count(*) FROM (SELECT pessoa_id, api_origem_id FROM rh_pessoainfocomplementar GROUP BY 1, 2 HAVING count(*) > 1) g'
    ),
    'deduplicacao_pendente': "SELECT count(*) FROM rh_deduplicacaopessoa WHERE aplicado_em IS NULL AND acao <> 'campo_descartado'",
}


def pendencias(cursor: CursorWrapper) -> dict[str, int]:
    totais = {}
    for chave, sql in CONSULTAS.items():
        cursor.execute(sql)
        totais[chave] = cursor.fetchone()[0]
    return totais
