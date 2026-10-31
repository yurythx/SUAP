from itertools import chain

from django.contrib.admin.utils import NestedObjects
from django.db import connection, router

from .python import sub_instances


def related_objects(obj):
    """
    Obtem os objetos relacionados a um objeto de modelo.

    Args:
        obj (Model): objeto de modelo.

    Returns:
        Objeto de modelo relacionado com **obj**.
    """
    collector = NestedObjects(using=router.db_for_write(obj))
    collector.collect([obj])

    def flatten(elem):
        if isinstance(elem, list):
            return chain.from_iterable(list(map(flatten, elem)))
        elif obj != elem:
            return (elem,)
        return ()

    result = flatten(collector.nested())
    return result


def can_hard_delete(obj):
    """
    Verifica se é possível apagar um objeto de modelo.

    Args:
        obj (Model): objeto de modelo.

    Returns:
         True se for possível apagar o objeto de modelo.
    """
    return all(item in sub_instances(obj) for item in related_objects(obj))


def can_hard_delete_fast(obj):
    """
    Verifica se é possível apagar um objeto de forma segura. Para tal, é verificado se existe alguma relação com o objeto.

    Args:
        obj (Model): objeto de modelo.

    Returns:
         True se for possível apagar o objeto de modelo.
    """
    heirs = sub_instances(obj)
    for heir in heirs:
        fields = [f for f in heir._meta.get_fields() if (f.one_to_many) and f.auto_created] + [
            f for f in heir._meta.get_fields(include_hidden=True) if f.many_to_many
        ]
        for field in fields:
            rel_obj = hasattr(field, 'get_accessor_name') and getattr(heir, field.get_accessor_name()) or getattr(heir, field.name)
            if rel_obj.exists():
                return False
    return True


def cache_queryset(queryset, keys, value=None):
    """
    Cria cache da queryset, com isso, consultas repetidas podem ser evitadas.

    Args:
        queryset (Queryset): queryset que deve ser usado na geração da cache;
        keys (list): lista com as chaves para armazenamento da cache, podendo ser 1 ou 2 itens;
        value (bool): indica se deve-se colocar em cache o objeto ou seu valor.

    Raises:
        ValueError caso a lista *keys* conter mais que 2 itens.

    Returns:
        Dict contendo o cache do queryset.
    """

    if isinstance(keys, str):
        keys = [keys]
    if len(keys) > 2:
        raise ValueError('``keys`` size limit is 2.')

    cache = {}

    if len(keys) == 1:
        key = keys[0]
        queryset = queryset.only(key)
        for obj in queryset:
            key_val = str(getattr(obj, key))
            cache[key_val] = value and getattr(obj, value) or obj

    elif len(keys) == 2:
        key1, key2 = keys
        queryset = queryset.only(key1, key2)
        for obj in queryset:
            key_val1 = str(getattr(obj, key1))
            if key_val1 not in cache:
                cache[key_val1] = {}
            key_val2 = str(getattr(obj, key2))
            cache[key_val1][key_val2] = value and getattr(obj, value) or obj

    return cache


def get_real_sql(queryset, remove_order_by=False):
    """
    Obtem a consulta (**SQL**) a partir de um queryset.

    Args:
        queryset (Queryset): queryset com os filtros;
        remove_order_by (bool): indica que deve-se retirar a cláusula order by do queryset.

    Returns:
        String com a pesquisa (**SQL**) realizada pelo queryset.
    """
    if remove_order_by:
        queryset.query.clear_ordering(force=True)
    sql, params = queryset.query.sql_with_params()
    cursor = connection.cursor()
    cursor.execute(sql, params)
    return str(cursor.db.ops.last_executed_query(cursor, sql, params))
