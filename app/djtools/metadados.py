"""Coletor de metadados dos models Django.

Transforma um model em instâncias **não salvas** de `MetadadoTabela`, `MetadadoCampo`, `MetadadoChoice`
e `MetadadoTransicao`. Não consulta o banco e não força tradução: quem chama aplica `translation.override`.
"""

import enum
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import DEFAULT_DB_ALIAS, router
from django.db.models import Field, Model

from djtools.models import MetadadoCampo, MetadadoChoice, MetadadoTabela, MetadadoTransicao


@dataclass
class Metadados:
    """Metadados coletados de um model, ainda não persistidos."""

    tabela: MetadadoTabela
    campos: list[MetadadoCampo] = field(default_factory=list)
    choices: list[MetadadoChoice] = field(default_factory=list)
    transicoes: list[MetadadoTransicao] = field(default_factory=list)


def models_no_escopo() -> list[type[Model]]:
    """Models com tabela própria e gerenciada pelo banco padrão (sem proxy, `managed=False` ou `ldapdb`)."""
    # o roteador não olha `managed`/`proxy` (quem olha é o executor de migrations), por isso o filtro explícito
    return [
        m
        for m in apps.get_models(include_auto_created=True)
        if m._meta.managed and not m._meta.proxy and router.allow_migrate_model(DEFAULT_DB_ALIAS, m)
    ]


def valor_choice(valor: object) -> str | None:
    """Texto do valor de um choice, igual ao que o Postgres devolve em `coluna::text`."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return 'true' if valor else 'false'
    if isinstance(valor, enum.Enum):
        return valor_choice(valor.value)
    return str(valor)


def deduplicar[T](objetos: list[T], chave: Callable[[T], tuple]) -> tuple[list[T], list[str]]:
    """Mantém o primeiro objeto de cada chave (`None` conta como valor) e avisa sobre os repetidos."""
    vistas: set[tuple] = set()
    mantidos: list[T] = []
    avisos: list[str] = []
    for objeto in objetos:
        k = chave(objeto)
        if k in vistas:
            avisos.append(f'{getattr(objeto, "tabela", "?")}.{getattr(objeto, "coluna", "?")}: chave repetida {k}')
        else:
            vistas.add(k)
            mantidos.append(objeto)
    return mantidos, avisos


def _caminho(objeto: object) -> str:
    nome = getattr(objeto, '__qualname__', None)
    return f'{objeto.__module__}.{nome}' if nome else repr(objeto)


def _docstring(model: type[Model]) -> str:
    doc = inspect.cleandoc(model.__doc__ or '')
    return '' if doc.startswith(f'{model.__name__}(') else doc


def _default(f: Field) -> tuple[str | None, bool]:
    if not f.has_default():
        return None, False
    if callable(f.default):
        return _caminho(f.default), True
    return repr(f.default), False


def _limit_choices_to(f: Field) -> str | None:
    limite = f.remote_field.limit_choices_to if f.remote_field else None
    if not limite:
        return None
    return _caminho(limite) if callable(limite) else repr(limite)


def _gfks(model: type[Model]) -> dict[str, str]:
    """Nome da coluna de cada par (`ct_field`, `fk_field`) -> nome do GenericForeignKey."""
    mapa: dict[str, str] = {}
    for gfk in model._meta.private_fields:
        if isinstance(gfk, GenericForeignKey):
            mapa[gfk.ct_field] = mapa[gfk.fk_field] = gfk.name
    return mapa


def _campo(model: type[Model], f: Field, gfks: dict[str, str]) -> MetadadoCampo:
    padrao, chamavel = _default(f)
    return MetadadoCampo(
        tabela=model._meta.db_table,
        coluna=f.column,
        app=model._meta.app_label,
        model=model._meta.label,
        campo=f.name,
        tipo=type(f).__name__,
        verbose_name=str(f.verbose_name),
        help_text=str(f.help_text),
        default=padrao,
        default_callable=chamavel,
        editable=f.editable,
        # alguns models declaram auto_now/auto_now_add=datetime.now() (valor truthy, tratado pelo Django como True); a coluna é booleana
        auto_now=bool(getattr(f, 'auto_now', False)),
        auto_now_add=bool(getattr(f, 'auto_now_add', False)),
        tabela_relacionada=f.related_model._meta.db_table if f.is_relation and f.related_model else None,
        limit_choices_to=_limit_choices_to(f),
        generic_foreign_key=gfks.get(f.name),
    )


def _opcoes(f: Field) -> list[tuple[object, object]]:
    return list(f.choices or getattr(getattr(f, 'base_field', None), 'choices', None) or [])


def _choices(model: type[Model], f: Field) -> list[MetadadoChoice]:
    linhas: list[MetadadoChoice] = []

    def adicionar(valor: object, rotulo: object, grupo: str | None) -> None:
        linhas.append(
            MetadadoChoice(
                tabela=model._meta.db_table, coluna=f.column, valor=valor_choice(valor), rotulo=str(rotulo), ordem=len(linhas), grupo=grupo
            )
        )

    for valor, rotulo in _opcoes(f):
        if isinstance(rotulo, list | tuple):
            for v, r in rotulo:
                adicionar(v, r, str(valor))
        else:
            adicionar(valor, rotulo, None)
    return linhas


def _transicoes(model: type[Model], f: Field) -> list[MetadadoTransicao]:
    if not hasattr(f, 'get_all_transitions'):
        return []
    return [
        MetadadoTransicao(
            tabela=model._meta.db_table,
            coluna=f.column,
            nome=t.name,
            origem=str(t.source),
            destino=None if t.target is None else str(t.target),
        )
        for t in f.get_all_transitions(model)
    ]


def coletar(model: type[Model]) -> Metadados:
    """Coleta tabela, colunas, choices e transições de FSM de um model, sem tocar o banco."""
    opts = model._meta
    resultado = Metadados(
        tabela=MetadadoTabela(
            tabela=opts.db_table,
            app=opts.app_label,
            model=opts.label,
            verbose_name=str(opts.verbose_name),
            verbose_name_plural=str(opts.verbose_name_plural),
            docstring=_docstring(model),
        )
    )
    gfks = _gfks(model)
    for f in opts.local_concrete_fields:
        resultado.campos.append(_campo(model, f, gfks))
        resultado.choices += _choices(model, f)
        resultado.transicoes += _transicoes(model, f)
    return resultado
