"""Descoberta das referências a PessoaFisica/Pessoa, em tempo de execução (apps instalados na instituição)."""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import connection
from django.db.models import Model

# Apps de histórico/log: guardam o id antigo de propósito (o mapa antigo→novo fica em DeduplicacaoPessoa); só referência viva é reapontada.
# O LogEntry do admin não declara GenericForeignKey, então não precisa entrar aqui.
APPS_DE_HISTORICO = frozenset({'reversion'})

# Só entram índices únicos totais sobre colunas-chave: o índice parcial (indpred) e o de expressão (indexprs) não podem ser avaliados aqui, e as
# colunas INCLUDE (além de indnkeyatts) não participam da unicidade. Nenhuma linha é apagada de antemão por causa deles: uma colisão real falha no
# UPDATE, o lote dá rollback e o grupo fica `erro` no plano (falha segura, sem perda de dado).
SQL_UNICIDADES = """
    SELECT array_agg(a.attname::text ORDER BY k.ordem)
    FROM pg_index i
    CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ordem)
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
    WHERE i.indrelid = %s::regclass AND i.indisunique AND NOT i.indisprimary
      AND i.indpred IS NULL AND i.indexprs IS NULL AND k.ordem <= i.indnkeyatts
    GROUP BY i.indexrelid
"""
SQL_FKS = """
    SELECT c.conrelid::regclass::text, a.attname::text, quote_ident(c.conname)
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f' AND c.confrelid IN ('pessoa_fisica'::regclass, 'pessoa'::regclass)
"""


@dataclass(frozen=True)
class Referencia:
    tabela: str
    coluna: str
    alvo: str
    pk: str
    unicidades: tuple[tuple[str, ...], ...]

    @property
    def um_para_um(self) -> bool:
        return (self.coluna,) in self.unicidades

    @property
    def compostas(self) -> tuple[tuple[str, ...], ...]:
        return tuple(u for u in self.unicidades if u != (self.coluna,))


@dataclass(frozen=True)
class ReferenciaGenerica:
    tabela: str
    coluna_tipo: str
    coluna_id: str
    id_texto: bool


def _modelos(include_auto_created: bool = True) -> list[type[Model]]:
    return [m for m in apps.get_models(include_auto_created=include_auto_created) if m._meta.managed and not m._meta.proxy]


def _unicidades(tabela: str, coluna: str) -> tuple[tuple[str, ...], ...]:
    with connection.cursor() as cursor:
        cursor.execute(SQL_UNICIDADES, [tabela])
        return tuple(tuple(colunas) for (colunas,) in cursor.fetchall() if coluna in colunas)


def _alvos() -> dict[type[Model], str]:
    from rh.models import Pessoa, PessoaFisica

    return {PessoaFisica: PessoaFisica._meta.db_table, Pessoa: Pessoa._meta.db_table}


def referencias() -> list[Referencia]:
    alvos = _alvos()
    encontradas = []
    for modelo in _modelos():
        for campo in modelo._meta.local_fields:
            # concrete_model: uma FK para um proxy de PessoaFisica/Pessoa também é referência.
            alvo = alvos.get(campo.related_model._meta.concrete_model) if campo.is_relation and campo.related_model else None
            if alvo and not campo.remote_field.parent_link:
                tabela = modelo._meta.db_table
                encontradas.append(Referencia(tabela, campo.column, alvo, modelo._meta.pk.column, _unicidades(tabela, campo.column)))
    return encontradas


def _ponteiros_mti() -> set[tuple[str, str]]:
    """(tabela, coluna) dos parent links de models filhos de Pessoa/PessoaFisica (ex.: pessoa_fisica.pessoa_ptr_id)."""
    alvos = _alvos()
    return {
        (modelo._meta.db_table, campo.column)
        for modelo in _modelos()
        for campo in modelo._meta.local_fields
        if campo.is_relation and campo.remote_field.parent_link and campo.related_model._meta.concrete_model in alvos
    }


def referencias_genericas() -> list[ReferenciaGenerica]:
    encontradas = []
    for modelo in _modelos(include_auto_created=False):
        if modelo._meta.app_label in APPS_DE_HISTORICO:
            continue
        for campo in modelo._meta.private_fields:
            if isinstance(campo, GenericForeignKey):
                coluna_id = modelo._meta.get_field(campo.fk_field)
                texto = coluna_id.get_internal_type() in ('CharField', 'TextField')
                encontradas.append(ReferenciaGenerica(modelo._meta.db_table, modelo._meta.get_field(campo.ct_field).column, coluna_id.column, texto))
    return encontradas


def fks_desconhecidas(conhecidas: list[Referencia]) -> list[str]:
    """FKs do banco para pessoa/pessoa_fisica que o ORM não conhece: bloqueiam o DELETE da perdedora."""
    return [f'{tabela}.{coluna}' for tabela, coluna, _ in constraints_desconhecidas(conhecidas)]


def constraints_desconhecidas(conhecidas: list[Referencia]) -> list[tuple[str, str, str]]:
    """``(tabela, coluna, constraint)`` de cada FK desconhecida, com tabela e constraint já citadas para SQL."""
    sabidas = {(r.tabela, r.coluna) for r in conhecidas} | _ponteiros_mti()
    with connection.cursor() as cursor:
        cursor.execute(SQL_FKS)
        return sorted(linha for linha in cursor.fetchall() if (linha[0].strip('"'), linha[1]) not in sabidas)
