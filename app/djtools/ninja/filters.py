from functools import reduce
from operator import or_

from django.db.models import Q


def filter_by_integer_or_text_fields(
    value: str | None,
    integer_lookups: list[str],
    text_lookups: list[str],
) -> Q:
    """
    Cria um objeto Q para filtrar por ID (se o valor for numérico)
    ou por uma lista de campos de texto (usando OR).

    Args:
        value: O valor do filtro recebido.
        integer_lookups: O prefixo do campo relacionado (ex: 'uo_id', 'autor_id').
        text_lookups: Lista de lookups de texto (ex: ['sigla', 'nome__icontains']).

    Returns:
        Um objeto Q para ser usado em um .filter().
    """
    if not value:
        return Q()

    if value.isdigit():
        q_conditions = [Q(**{lookup: int(value)}) for lookup in integer_lookups]
    else:
        q_conditions = [Q(**{lookup: value}) for lookup in text_lookups]

    if not q_conditions:
        return Q()

    return reduce(or_, q_conditions)
