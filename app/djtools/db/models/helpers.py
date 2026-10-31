from functools import reduce
from operator import or_

from django.db import models

from djtools.db.models.fields.search import SearchField


def get_search_field(model_class):
    """
    Obtem o campo do tipo *SearchField* contida no modelo passado.

    Args:
        model_class (Model): classe do modelo.

    Returns:
        ModelField se foi definido um campo SearchField no modelo, caso contrário *None* é retornado.
    """
    for f in model_class._meta.fields:
        if f.__class__.__name__ == 'SearchField':
            return f
    return None


def _get_str_fields(cls):
    """Retorna lista de campos (string) cujo tipo é CharField ou TextField"""
    fields = []
    for f in cls._meta.fields:
        if f.get_internal_type() in ['CharField', 'TextField']:
            fields.append(f.name)
    if not fields:
        raise ValueError(f"Class {cls.__name__} don't have CharField or TextField.")
    return fields


def _search(cls, q, fields=None, max_fields=5):
    """
    Busca genérica para models.

    q         : string a ser buscada
    fields    : define os campos que se quer filtrar
    max_fields: usado quando não é passado o fields e define os N primeiros campos
                charfield do modelo que serão incluídos na busca
    """

    search_field = get_search_field(cls)

    if search_field and not fields:
        use_fields = False
        use_search_field = True
    else:
        use_fields = True
        use_search_field = False

    qs = cls.objects.all()

    if use_fields:
        fields = fields or _get_str_fields(cls)[:max_fields]
        for word in q.split(' '):
            or_queries = [models.Q(**{f'{field_name}__icontains': word}) for field_name in fields]
            qs = qs.filter(reduce(or_, or_queries))
    elif use_search_field:
        q = SearchField.prepare_string(q)
        for word in q.split(' '):
            or_queries = [models.Q(**{f'{search_field.name}__contains': word})]
            qs = qs.filter(reduce(or_, or_queries))

    return qs
