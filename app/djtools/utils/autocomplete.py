"""Módulo de utilitários para buscas/autocomplete com comportamento defensivo.

Este arquivo contém implementações tolerantes para gerar resultados de
autocomplete sem quebrar quando modelos declaram hints inválidos ou quando
alguns objetos possuem descritores problemáticos.
"""

import difflib
import json
import string
import time
from collections.abc import Callable
from functools import reduce
from json import JSONDecodeError
from operator import or_

from django.core.exceptions import FieldDoesNotExist
from django.core.signals import request_started
from django.db import connection, models, reset_queries
from django.db.models import CharField
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .python import eval_attr
from .response import JsonResponse
from .serialization import timeless_load_qs_query


def _get_queryset(cls, manager_name=None, control=None):
    """Obter queryset seguro usado pelos helpers de autocomplete.

    Retorna manager.none() quando não for possível construir o queryset e
    ignora exceções para manter o autocomplete robusto.
    """
    try:
        manager = manager_name and getattr(cls, manager_name) or cls.objects
        if control:
            queryset = manager.all()
            queryset.query = timeless_load_qs_query(control)
            return queryset
        else:
            return manager.none()
    except Exception:
        return None


def _construct_search(field_name):
    return f'{field_name}__icontains'


def _is_valid_search_field(cls, field_name):
    """Indica se ``field_name`` resolve para um campo existente no modelo.

    Valida apenas o token raiz (antes do primeiro ``__``), evitando que nomes
    arbitrários vindos da requisição gerem ``FieldError`` no ``.filter()``.
    """
    root = str(field_name).split('__', 1)[0]
    try:
        cls._meta.get_field(root)
        return True
    except FieldDoesNotExist:
        return False


def _sanitize_search_fields(cls, search_fields):
    """Filtra ``search_fields`` mantendo só campos válidos do modelo.

    Descarta nomes inexistentes (potencialmente vindos de scanners/probes) e
    cai no padrão do modelo quando nada sobra.
    """
    if search_fields:
        search_fields = [f for f in search_fields if _is_valid_search_field(cls, f)]
    return search_fields or _get_search_fields_alternative(cls)


def _get_search_fields_alternative(cls):
    for f in cls._meta.fields:
        if f.__class__.__name__ == 'SearchField':
            return [f.name]
    if hasattr(cls, 'SEARCH_FIELDS'):
        return cls.SEARCH_FIELDS
    return [x.name for x in cls._meta.fields if isinstance(x, CharField)]


def _filtrar_por_pks(qs, filter_pks: dict | None):
    """Aplica os filtros de ``filter_pks``; chaves ``__in`` aceitam valores separados por ``;`` ou ``,``."""
    filters = {}
    for key, value in (filter_pks or {}).items():
        if not value:
            continue
        if key.endswith('__in'):
            separador = ';' if ';' in value else ','
            filters[key] = value.split(separador)
        else:
            filters[key] = value
    return qs.filter(**filters) if filters else qs


def _limiar_palavra(cls, min_chars: int | None) -> int:
    """Tamanho mínimo de palavra: ``min_chars`` da requisição, senão ``AUTOCOMPLETE_MIN_CHARS`` do model, senão 3."""
    try:
        if min_chars is not None:
            return int(min_chars)
        model_min = getattr(cls, 'AUTOCOMPLETE_MIN_CHARS', None)
        return int(model_min) if model_min is not None else 3
    except Exception:
        return 3


# Acima deste número de linhas na sonda a palavra é comum: o OR entre tabelas acha a página cedo pelo índice do ORDER BY.
LIMITE_SONDA = 1000


def _tabela_do_campo(cls: type[models.Model], campo: str) -> str:
    """Caminho da tabela onde ``campo`` mora: ``''`` no próprio model, o da relação quando o campo passa por uma."""
    raiz = campo.split('__', 1)[0]
    try:
        relacao = cls._meta.get_field(raiz).is_relation
    except FieldDoesNotExist:
        return ''
    return campo.rsplit('__', 1)[0] if relacao else ''


def _base_da_sonda(qs: models.QuerySet) -> models.QuerySet:
    """``qs`` (o queryset do widget) sem ordem nem ``DISTINCT``: a sonda só lê as linhas que o widget mostraria.

    Com ``DISTINCT ON`` o recorte é semântica do queryset; aí a sonda parte do manager base (superconjunto).
    """
    if qs.query.distinct_fields:
        return qs.model._base_manager.order_by()
    base = qs.order_by()
    base.query.distinct = False
    return base


def _ids_da_sonda(base: models.QuerySet, or_queries: list[models.Q]) -> list | None:
    """Ids de ``base`` que casam com algum dos ``or_queries``, ou ``None`` se passarem de ``LIMITE_SONDA`` (#17813).

    O OR entre campos de tabelas diferentes não usa o índice de nenhuma delas: o planejador percorre o índice do
    ``ORDER BY`` até completar a página, o que com palavra rara ou sem resultado varre a tabela inteira (``Aluno``: nome
    da pessoa ou matrícula). A sonda junta (``UNION ALL``) uma consulta por campo, cada uma com o índice da sua tabela:
    até ``LIMITE_SONDA`` linhas, os ids lidos são exatamente os que casam. Acima disso a palavra é comum e o OR, que
    acha a página cedo, continua valendo.
    """
    ramos = [base.filter(ramo).values_list('pk', flat=True) for ramo in or_queries]
    linhas = list(ramos[0].union(*ramos[1:], all=True)[: LIMITE_SONDA + 1])
    return sorted(set(linhas)) if len(linhas) <= LIMITE_SONDA else None


def _filtrar_por_palavras(
    qs: models.QuerySet, cls: type[models.Model], q: str, search_fields: list[str], split_q: bool, min_chars: int | None
) -> models.QuerySet:
    """Cada palavra de ``q`` precisa casar (``icontains``) com ao menos um dos ``search_fields``."""
    if not search_fields:
        return qs
    threshold = _limiar_palavra(cls, min_chars)
    words = split_q and q.split() or [q]
    words = list(dict.fromkeys([word.strip(string.punctuation) for word in words if len(word) >= threshold or word.isdigit()]).keys())[:10]
    cruza_tabelas = len({_tabela_do_campo(cls, str(campo)) for campo in search_fields}) > 1
    base = _base_da_sonda(qs)
    for word in filter(None, words):
        or_queries = [models.Q(**{_construct_search(str(field_name)): word}) for field_name in search_fields]
        ids = _ids_da_sonda(base, or_queries) if cruza_tabelas else None
        if ids is None:
            qs = qs.filter(reduce(or_, or_queries))
        else:
            # só os ids da palavra rara restringem as próximas sondas: herdar o OR de uma comum as deixaria lentas
            qs = qs.filter(pk__in=ids)
            base = base.filter(pk__in=ids)
    return qs


def generic_search_json(
    cls: type[models.Model],
    q: str,
    manager_name: str | None = None,
    label_value: str | None = None,
    search_fields: list[str] | None = None,
    qs_filter: str | None = None,
    split_q: bool = True,
    control: str | None = None,
    filter_pks: dict | None = None,
    ext_combo_template: Callable[[models.Model], str] | None = None,
    readonly: bool = False,
    page: int | None = None,
    form_filters: list[tuple[str, str]] | None = None,
    min_chars: int | None = 3,
) -> dict:
    """Versão JSON do generic_search para APIs de autocomplete.

    Retorna um dicionário com chaves compatíveis com widgets/consumidores JSON
    (por exemplo: {'total': n, 'items': [...] }).

    Os parâmetros seguem os mesmos significados de `generic_search`.
    """

    search_fields = search_fields or _get_search_fields_alternative(cls)

    if not search_fields and not readonly:
        raise Exception('No search fields defined and not readonly')

    qs = _get_queryset(cls, manager_name, control)
    if qs is None:
        return {'total': 0, 'items': []}

    qs = qs.all()

    qs = _filtrar_por_pks(qs, filter_pks)

    try:
        if not readonly:
            qs = _filtrar_por_palavras(qs, cls, q, search_fields, split_q, min_chars)

        if qs_filter:
            k, v = qs_filter.split('=')
            if k.endswith('__in'):
                v = v.split(',')
            qs = qs.filter(**{str(k): v})

    except ValueError:
        qs = qs.none()

    if form_filters:
        for k, v in form_filters:
            qs = qs.filter(**{k: v})

    return generate_autocomplete_dict(_distinct_so_se_duplica(qs), page, label_value, ext_combo_template)


def _distinct_so_se_duplica(qs: models.QuerySet) -> models.QuerySet:
    """``DISTINCT`` só com junção to-many, inclusive o que vier do queryset do widget (#17798).

    Sobre todas as colunas, o ``DISTINCT`` ordenava em disco toda a busca antes do ``LIMIT``. Junções
    to-one não duplicam linhas. ``DISTINCT ON`` (``distinct_fields``) é semântica do queryset: fica.
    """
    if _has_duplicating_join(qs):
        return qs.distinct()
    if qs.query.distinct and not qs.query.distinct_fields:
        qs = qs.all()
        qs.query.distinct = False
    return qs


def _has_duplicating_join(qs):
    """Indica se ``qs`` tem junção to-many (reverse FK / M2M) capaz de duplicar linhas.

    Junções to-one (FK direta, ``select_related``) nunca duplicam. Em qualquer falha
    de inspeção retorna ``True`` (conservador: preserva o ``DISTINCT``).

    Args:
        qs: QuerySet a inspecionar.

    Returns:
        bool: ``True`` se houver junção multivalorada (ou na dúvida).
    """
    try:
        return any(
            getattr(join.join_field, 'one_to_many', False) or getattr(join.join_field, 'many_to_many', False)
            for join in qs.query.alias_map.values()
            if getattr(join, 'join_field', None) is not None
        )
    except Exception:
        return True


def _ordem_deterministica(qs: models.QuerySet) -> models.QuerySet:
    """Acrescenta a pk como último critério do ``ORDER BY`` (#17798).

    O autocomplete ordena por campo não único (``Setor`` por ``sigla``, ``Aluno`` pelo nome). Sem o
    ``DISTINCT``, que ordenava por todas as colunas, os empates sairiam na ordem do plano (!18415):
    com a pk no fim, a mesma busca devolve sempre a mesma página. Na dúvida devolve ``qs`` intacto.
    """
    try:
        query = qs.query
        if query.combinator or query.extra_order_by:
            return qs
        ordem = list(query.order_by) or (list(qs.model._meta.ordering) if query.default_ordering else [])
        if any(isinstance(campo, str) and campo.lstrip('-') in ('pk', qs.model._meta.pk.name, '?') for campo in ordem):
            return qs
        return qs.order_by(*ordem, 'pk')
    except Exception:
        return qs


def _safe_str(val):
    """Converte ``val`` em texto seguro para o JSON do autocomplete (sem ``|``/``\\n``)."""
    try:
        if val is None:
            return ''
        return str(val).replace('|', '/').replace('\n', ' ')
    except Exception:
        return ''


def _group_ids_by_ctype(objs):
    """Agrupa ``id_relacionamento`` por ``tipo_relacionamento_id`` para pré-carga em lote."""
    ctype_to_ids = {}
    for o in objs:
        try:
            ctid = getattr(o, 'tipo_relacionamento_id', None) or getattr(o, 'tipo_relacionamento', None)
            rel_id = getattr(o, 'id_relacionamento', None)
            if ctid and rel_id:
                ctype_to_ids.setdefault(int(ctid), set()).add(int(rel_id))
        except Exception:
            continue
    return ctype_to_ids


def _load_targets(ctype_to_ids):
    """Carrega os alvos do GenericForeignKey em lote, indexados por ``(ctid, pk)``."""
    from django.contrib.contenttypes.models import ContentType

    prefetched = {}
    for ctid, ids in ctype_to_ids.items():
        try:
            ct = ContentType.objects.get_for_id(ctid)
            target_model = ct.model_class()
            if not target_model:
                continue
            target_qs = target_model.objects.filter(pk__in=list(ids))
            target_qs = _apply_autocomplete_related(target_qs, None, target_model)
            for inst in target_qs:
                prefetched[(ctid, inst.pk)] = inst
        except Exception:
            return {}
    return prefetched


def _build_prefetched_rel_map(model, objs):
    """Pré-carrega os alvos do GenericForeignKey dos ``objs`` evitando N+1 na renderização."""
    try:
        if model is None or not objs:
            return {}
        if not (hasattr(model, 'tipo_relacionamento') and hasattr(model, 'id_relacionamento')):
            return {}
        return _load_targets(_group_ids_by_ctype(objs))
    except Exception:
        return {}


def _preencher_cache_gfk(model: type[models.Model], objs: list[models.Model], prefetched_rel_map: dict) -> None:
    """Põe no cache de cada objeto o ContentType e o alvo do GenericForeignKey já carregados (#17694).

    Sem isso, ``__str__`` que lê o GFK (ex.: ``Vinculo``) recarrega o alvo e o ContentType item a item.
    O ContentType vem do cache global de ``get_for_id``; objeto sem alvo no mapa fica no carregamento preguiçoso.
    """
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType

    gfks = [
        f
        for f in model._meta.private_fields
        if isinstance(f, GenericForeignKey) and (f.ct_field, f.fk_field) == ('tipo_relacionamento', 'id_relacionamento')
    ]
    if not (prefetched_rel_map and gfks):  # sem GFK, ``tipo_relacionamento`` pode nem ser FK
        return
    for obj in objs:
        chave = (obj.tipo_relacionamento_id, obj.id_relacionamento)
        alvo = prefetched_rel_map.get(chave)
        if alvo is None:
            continue
        obj.tipo_relacionamento = ContentType.objects.get_for_id(chave[0])
        for gfk in gfks:
            gfk.set_cached_value(obj, alvo)


def _ext_combo_value(obj):
    """Resolve ``get_ext_combo_template`` (atributo ou método) do objeto como texto seguro."""
    val = obj.get_ext_combo_template() if callable(obj.get_ext_combo_template) else obj.get_ext_combo_template
    return _safe_str(val)


def _related_combo_html(obj, model, prefetched_rel_map):
    """HTML do alvo do GenericForeignKey pré-carregado; ``None`` se não aplicável."""
    if model is None or not (hasattr(model, 'tipo_relacionamento') and hasattr(model, 'id_relacionamento')):
        return None
    ctid = getattr(obj, 'tipo_relacionamento_id', None) or getattr(obj, 'tipo_relacionamento', None)
    rel_id = getattr(obj, 'id_relacionamento', None)
    if not (ctid and rel_id):
        return None
    target = prefetched_rel_map.get((int(ctid), int(rel_id)))
    if target and hasattr(target, 'get_ext_combo_template'):
        return _safe_str(target.get_ext_combo_template())
    return None


def _resolve_item_html(obj, model, prefetched_rel_map, ext_combo_template, default):
    """Determina o HTML do item priorizando ``ext_combo_template`` e o alvo pré-carregado."""
    if ext_combo_template:
        try:
            return _safe_str(ext_combo_template(obj))
        except Exception:
            return default
    if not hasattr(obj, 'get_ext_combo_template'):
        return default
    try:
        related = _related_combo_html(obj, model, prefetched_rel_map)
        return related if related is not None else _ext_combo_value(obj)
    except Exception:
        return default


def _resolve_item_text(obj, ext_combo_template_text, default):
    """Determina o texto do item via ``ext_combo_template_text``/``get_ext_combo_template_text``."""
    if ext_combo_template_text:
        try:
            return _safe_str(ext_combo_template_text(obj))
        except Exception:
            return default
    if hasattr(obj, 'get_ext_combo_template_text'):
        try:
            return _safe_str(obj.get_ext_combo_template_text())
        except Exception:
            return default
    return default


def _build_item_row(obj, model, prefetched_rel_map, label_value, ext_combo_template, ext_combo_template_text):
    """Monta a linha ``{'id', 'html', 'text'}`` de um objeto; ``None`` se houver falha."""
    try:
        row = {'id': getattr(obj, 'id', getattr(obj, 'pk', None))}
        try:
            raw_label = eval_attr(obj, label_value or '__str__')
        except Exception:
            raw_label = ''
        str_text = _safe_str(raw_label)
        row['html'] = _resolve_item_html(obj, model, prefetched_rel_map, ext_combo_template, str_text)
        row['text'] = _resolve_item_text(obj, ext_combo_template_text, str_text)
        return row
    except Exception:
        return None


def generate_autocomplete_dict(
    qs: models.QuerySet,
    page: int,
    label_value: str | None = None,
    ext_combo_template: Callable[[models.Model], str] | None = None,
    ext_combo_template_text: Callable[[models.Model], str] | None = None,
) -> dict:
    """Gera dicionário ``{'total': n, 'items': [...]}`` para autocomplete com tolerância a falhas.

    Aplica hints declarados em ``EXT_COMBO_RELATED`` e ignora silenciosamente
    objetos problemáticos para não quebrar o componente.

    ``total`` não é a contagem da busca: os widgets só o usam em ``more: page * 20 < total``.
    Busca-se uma linha além da página e ``total`` é ``início da página + linhas lidas``, o que
    acerta o ``more`` sem o ``COUNT`` da busca inteira (#17798).

    Args:
        qs: QuerySet de onde materializar a página de resultados.
        page: Número da página (1-indexed); página tem 20 itens.
        label_value: Expressão ou atributo para extrair o texto do item.
        ext_combo_template: Callable opcional para gerar o HTML do item.
        ext_combo_template_text: Callable opcional para gerar o texto do item.

    Returns:
        dict: ``{'total': int, 'items': [{'id', 'html', 'text'}, ...]}``.
    """
    items = []
    model = getattr(qs, 'model', None)
    qs = _ordem_deterministica(_apply_autocomplete_related(qs, ext_combo_template, model))

    start = 20 * page - 20
    end = 20 * page
    try:
        linhas = list(qs[start : end + 1])
    except Exception:
        return {'total': 0, 'items': []}
    slice_qs = linhas[:20]

    prefetched_rel_map = _build_prefetched_rel_map(model, slice_qs)
    _preencher_cache_gfk(model, slice_qs, prefetched_rel_map)

    for obj in slice_qs:
        row = _build_item_row(obj, model, prefetched_rel_map, label_value, ext_combo_template, ext_combo_template_text)
        if row is not None:
            items.append(row)

    return {'total': start + len(linhas), 'items': items}


def _apply_autocomplete_related(qs, ext_combo_template=None, model_cls=None):
    """Apply model-declared related loading and simple annotations to a queryset.

    This function is conservative: errors while applying declarations are ignored
    so autocompletes remain functional even with bad hints.
    """
    if qs is None:
        return qs

    model = model_cls or getattr(qs, 'model', None)
    if model is None:
        return qs

    related = getattr(model, 'EXT_COMBO_RELATED', {}) or {}
    try:
        select = related.get('select_related')
        if select:
            sel_list = select if isinstance(select, list | tuple) else [select]

            valid = []
            try:
                target_model = qs.model if hasattr(qs, 'model') and qs.model is not None else model
            except Exception:
                target_model = model

            deferred_roots = set()
            only_called = False
            try:
                if hasattr(qs, 'query'):
                    dl = getattr(qs.query, 'deferred_loading', None)
                    if dl:
                        if isinstance(dl, tuple):
                            fields_set, flag = dl
                            if flag:
                                deferred_fields = set(fields_set)
                            else:
                                deferred_fields = set()
                                only_called = True
                        else:
                            deferred_fields = set(dl)

                        if deferred_fields:
                            deferred_roots = {f.split('__', 1)[0] for f in deferred_fields}
            except Exception:
                deferred_roots = set()

            if only_called:
                valid = []
            else:
                for sel in sel_list:
                    root = sel.split('__', 1)[0]
                    try:
                        if target_model is None:
                            continue
                        if root in deferred_roots:
                            continue
                        field = target_model._meta.get_field(root)
                        if (
                            getattr(field, 'is_relation', False)
                            and not getattr(field, 'many_to_many', False)
                            and not getattr(field, 'one_to_many', False)
                        ):
                            valid.append(sel)
                    except Exception:
                        continue

            if valid:
                try:
                    if isinstance(select, list | tuple):
                        qs = qs.select_related(*valid)
                    else:
                        qs = qs.select_related(valid[0])
                except Exception:
                    pass
    except Exception:
        pass

    try:
        prefetch = related.get('prefetch_related')
        if prefetch:
            if not isinstance(prefetch, list | tuple):
                prefetch = [prefetch]

            prefetch_args = []
            for p in prefetch:
                try:
                    from django.db.models import Prefetch as _Prefetch

                    if isinstance(p, _Prefetch):
                        prefetch_args.append(p)
                    elif callable(p):
                        try:
                            res = p()
                            prefetch_args.append(res)
                        except Exception:
                            continue
                    else:
                        prefetch_args.append(p)
                except Exception:
                    continue

            if prefetch_args:
                try:
                    qs = qs.prefetch_related(*prefetch_args)
                except Exception:
                    pass
    except Exception:
        pass

    return qs


def autocomplete_full_diagnostics(search=None, only_errors=False, include_only_pk=True, page=1):
    """Executa diagnóstico de todos os autocompletes do projeto.

    Esta função percorre todos os modelos registrados em Django e tenta
    materializar um resultado de autocomplete usando `generate_autocomplete_dict`
    tanto para o queryset padrão (m.objects.all()) quanto para
    `m.objects.only('pk')` (se `include_only_pk` for True).

    Args:
        search: string opcional para filtrar modelos pelo nome ou mensagem de erro.
        only_errors: se True, retorna apenas entradas que falharam.
        include_only_pk: se True inclui a verificação contra queryset.only('pk').
        page: página a materializar (defaults to 1).

    Returns:
        dict com chaves:
            - total_checked: número de verificações realizadas.
            - errors: lista de dicts com os erros encontrados (cada dict contém
              'model', 'variant' ('full' ou 'only_pk'), 'error' (traceback)).
            - oks: lista de dicts com verificações que passaram (model, variant, total).

    Uso esperado:
        - Ferramenta de operação/diagnóstico para a tela `autocomplete_full_diagnostics`.
        - Permite buscar por modelos com erro via parâmetro `search`.
    """
    import traceback

    from django.apps import apps

    oks = []
    errors = []
    checked = 0

    for m in apps.get_models():
        name = f'{m._meta.app_label}.{m._meta.model_name}'
        variants = [('full', m.objects.all())]
        if include_only_pk:
            variants.append(('only_pk', m.objects.only('pk')))

        for variant_name, qs in variants:
            checked += 1
            try:
                res = generate_autocomplete_dict(qs, page=page)
                entry = {'model': name, 'variant': variant_name, 'ok': True, 'total': res.get('total')}
                if search:
                    if search.lower() in name.lower():
                        oks.append(entry)
                else:
                    oks.append(entry)
            except Exception:
                tb = traceback.format_exc()
                entry = {'model': name, 'variant': variant_name, 'ok': False, 'error': tb}
                if search:
                    if search.lower() in name.lower() or search.lower() in tb.lower():
                        errors.append(entry)
                else:
                    errors.append(entry)

    if only_errors:
        return {'total_checked': checked, 'errors': errors}
    return {'total_checked': checked, 'errors': errors, 'oks': oks}


class CaptureQueriesContext:
    def __init__(self, connection):
        self.connection = connection

    def __iter__(self):
        return iter(self.captured_queries)

    def __getitem__(self, index):
        return self.captured_queries[index]

    def __len__(self):
        return len(self.captured_queries)

    @property
    def captured_queries(self):
        return self.connection.queries[self.initial_queries : self.final_queries]

    def __enter__(self):
        self.force_debug_cursor = self.connection.force_debug_cursor
        self.connection.force_debug_cursor = True
        self.connection.ensure_connection()
        self.initial_queries = len(self.connection.queries_log)
        self.final_queries = None
        request_started.disconnect(reset_queries)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.force_debug_cursor = self.force_debug_cursor
        request_started.connect(reset_queries)
        if exc_type is None:
            self.final_queries = len(self.connection.queries_log)


def _parse_search_fields(cls, data):
    """Lê e sanitiza ``search_fields`` da requisição, descartando campos inexistentes."""
    try:
        search_fields = [search_field.strip() for search_field in data.get('search_fields').split(',')]
    except AttributeError:
        return None
    return _sanitize_search_fields(cls, search_fields)


def _parse_ext_combo_template(data):
    """Desserializa o callable de ``ext_combo_template`` informado na requisição."""
    ext_combo_template = data.get('ext_combo_template')
    if ext_combo_template:
        # http://stackoverflow.com/questions/1253528/is-there-an-easy-way-to-pickle-a-python-function-or-otherwise-serialize-its-cod#answers-header
        # deserializa a função
        try:
            m, name = timeless_load_qs_query(ext_combo_template).split(':')
            module = __import__(m, fromlist=[None])
            ext_combo_template = getattr(module, name)
        except JSONDecodeError:
            ext_combo_template = None
    return ext_combo_template


def _generic_search_json_response(cls, data):
    """Monta os argumentos a partir do request e delega ao ``generic_search_json``."""
    try:
        filter_pks = json.loads(data.get('filter_pks'))
    except JSONDecodeError, TypeError:
        filter_pks = None

    try:
        page = int(data.get('page', 1))
    except ValueError:
        page = 1

    form_filters = [(key[13:], data[key]) for key in data if key.startswith('form_filter__') and data[key]]

    args = {
        'q': data.get('q', ''),
        'control': data.get('control', None),
        'manager_name': data.get('manager_name', None),
        'label_value': data.get('label_value', None),
        'qs_filter': data.get('qs_filter', None),
        'search_fields': _parse_search_fields(cls, data),
        'filter_pks': filter_pks,
        'ext_combo_template': _parse_ext_combo_template(data),
        'readonly': 'readonly' in data,
        'page': page,
        'form_filters': form_filters,
        'min_chars': data.get('min_chars', None),
    }
    return JsonResponse(generic_search_json(cls, **args))


# ---------------------------------------------------------------------------
# Diagnóstico completo de autocompletes (helpers da view
# djtools.views.autocomplete_full_diagnostics). Reproduzem o N+1 que só ocorre
# durante a renderização do template de cada objeto.
# ---------------------------------------------------------------------------

DEFAULT_AUTOCOMPLETE_PAGE_SIZE = 20


def diagnostic_params_from_form(form, get_data):
    """Extrai ``(limit, app, declared, only_special)`` do form validado ou do GET cru.

    Args:
        form: ``AutocompleteDiagnosticsForm`` ligado ao ``request.GET``.
        get_data: ``request.GET`` (fallback quando o form é inválido).

    Returns:
        tuple: ``(limit:int, selected_app:str, declared_choice:str, only_special:bool)``.
    """
    if form.is_valid():
        cd = form.cleaned_data
        return int(cd.get('limit') or 1), cd.get('app'), cd.get('declared'), bool(cd.get('only_special'))
    return int(get_data.get('limit', 1)), get_data.get('app', ''), get_data.get('declared', 'all'), bool(get_data.get('only_special'))


def _is_special_diagnostic_model(model):
    """Indica se o modelo é um dos "grandes" usados no modo ``only_special``."""
    from comum.models import User

    especiais = {(User._meta.app_label, User.__name__), ('comum', 'Vinculo'), ('rh', 'Pessoa'), ('rh', 'PessoaFisica')}
    return (model._meta.app_label, model.__name__) in especiais


def should_skip_diagnostic_model(model, selected_app, only_special, declared_choice):
    """Aplica os filtros do loop de diagnóstico; ``True`` para pular o modelo.

    Pula modelos internos do Django, fora do app selecionado, fora do conjunto
    especial (quando ``only_special``) e em desacordo com o filtro ``declared``.
    """
    if model._meta.app_label.startswith('django'):
        return True
    if selected_app and model._meta.app_label != selected_app:
        return True
    if only_special and not _is_special_diagnostic_model(model):
        return True
    has_template = hasattr(model, 'get_ext_combo_template') or hasattr(model, 'EXT_COMBO_RELATED')
    if not has_template and declared_choice == 'declared':
        return True
    return has_template and declared_choice == 'not_declared' and hasattr(model, 'EXT_COMBO_RELATED')


def _render_combo(obj):
    """Renderiza um objeto como no autocomplete (``get_ext_combo_template`` ou ``str``)."""
    return obj.get_ext_combo_template() if hasattr(obj, 'get_ext_combo_template') else str(obj)


def _capture_render(qs, pks):
    """Executa ``qs`` capturando as queries e renderizando os objetos de ``pks``.

    Returns:
        tuple: ``(n_queries:int, sql_sample:list[str], rendered:list[str], elapsed:float)``.
    """
    with CaptureQueriesContext(connection) as ctx:
        t0 = time.perf_counter()
        objs = list(qs)
        elapsed = time.perf_counter() - t0
        obj_map = {o.pk: o for o in objs}
        rendered = [_render_combo(obj_map[pk]) for pk in pks if pk in obj_map]
    return len(ctx), [q['sql'] for q in ctx.captured_queries[:8]], rendered, elapsed


def _build_sql_diff_html(entry, raw_sql, opt_sql):
    """Preenche ``entry`` com os blocos HTML de SQL (raw/opt) e o diff unificado."""
    try:
        raw_text = '\n'.join(raw_sql or [])
        opt_text = '\n'.join(opt_sql or [])
        entry['raw_sql_html'] = mark_safe(f'<pre>{escape(raw_text)}</pre>') if raw_text else ''
        entry['opt_sql_html'] = mark_safe(f'<pre>{escape(opt_text)}</pre>') if opt_text else ''
        diff_lines = list(difflib.unified_diff(raw_sql or [], opt_sql or [], fromfile='raw_sql', tofile='opt_sql', lineterm=''))
        diff_text = '\n'.join(diff_lines) if diff_lines else ''
        entry['sql_diff'] = mark_safe(f'<pre>{escape(diff_text)}</pre>') if diff_text else ''
    except Exception:
        entry['raw_sql_html'] = ''
        entry['opt_sql_html'] = ''
        entry['sql_diff'] = ''


def _diagnostic_metrics(raw_q, raw_sql, opt_q, opt_sql, rendered, rendered_opt, has_declared, model_local):
    """Monta o dicionário de métricas (contagens, amostras e relateds declarados)."""
    declared = getattr(model_local, 'EXT_COMBO_RELATED', {}) if has_declared else {}
    return {
        'raw_queries': raw_q,
        'raw_sql_sample': raw_sql,
        'opt_queries': opt_q,
        'opt_sql_sample': opt_sql,
        'sample_rendered': rendered[:3],
        'sample_rendered_opt': rendered_opt[:3],
        'has_declared': has_declared,
        'declared_select': declared.get('select_related', []) if has_declared else [],
        'declared_prefetch': declared.get('prefetch_related', []) if has_declared else [],
    }


def _estimate_saved_seconds(raw_time, opt_time, pks):
    """Estima o tempo poupado por página de autocomplete, extrapolando a amostra."""
    if raw_time is None or opt_time is None:
        return None
    sample_count = len(pks) or 1
    return ((raw_time - opt_time) / sample_count) * DEFAULT_AUTOCOMPLETE_PAGE_SIZE


def _compute_diagnostic_deltas(entry, raw_q, opt_q, raw_time, opt_time, pks):
    """Preenche ``entry`` com ``delta``, ``delta_pct`` e ``estimated_saved_seconds``."""
    try:
        delta = raw_q - opt_q
        pct = (delta / raw_q) * 100 if raw_q else None
        entry['delta'] = delta
        entry['delta_pct'] = round(pct, 1) if pct is not None else None
        entry['estimated_saved_seconds'] = _estimate_saved_seconds(raw_time, opt_time, pks)
    except Exception:
        entry['delta'] = None
        entry['delta_pct'] = None


def run_autocomplete_diagnostic(model_local, base_qs, limit, meta=None):
    """Roda o diagnóstico (raw vs. relateds declarados) para uma queryset base.

    Renderiza uma amostra de ``limit`` objetos duas vezes — sem relateds (raw) e
    com os relateds declarados aplicados — capturando as queries de cada execução
    para evidenciar N+1s que só surgem na renderização do template.

    Args:
        model_local: Classe de modelo sob diagnóstico.
        base_qs: Queryset base (já filtrada por subtipo, quando aplicável).
        limit: Quantidade de PKs amostrados.
        meta: Campos extras a incluir na entrada (ex.: ``{'user_type': ...}``).

    Returns:
        dict: Entrada do relatório; em caso de falha, contém a chave ``error``.
    """
    meta = meta or {}
    entry = {'app': model_local._meta.app_label, 'model': model_local.__name__}
    entry.update(meta)
    try:
        pks = list(base_qs.values_list('pk', flat=True)[:limit])
        raw_q, raw_sql, rendered, raw_time = _capture_render(model_local.objects.filter(pk__in=pks), pks)
        qs_opt = _apply_autocomplete_related(base_qs.filter(pk__in=pks), ext_combo_template=None, model_cls=model_local)
        opt_q, opt_sql, rendered_opt, opt_time = _capture_render(qs_opt, pks)
        # Sem EXT_COMBO_RELATED, espelha as métricas raw para não reportar ganhos
        # espúrios vindos de cache do banco.
        has_declared = hasattr(model_local, 'EXT_COMBO_RELATED')
        if not has_declared:
            opt_q, opt_sql, rendered_opt = raw_q, raw_sql, rendered
        _build_sql_diff_html(entry, raw_sql, opt_sql)
        entry.update(_diagnostic_metrics(raw_q, raw_sql, opt_q, opt_sql, rendered, rendered_opt, has_declared, model_local))
        _compute_diagnostic_deltas(entry, raw_q, opt_q, raw_time, opt_time, pks)
    except Exception as e:
        entry['error'] = str(e)
    return entry


def _diagnostic_user_splits(model, User, Pessoa, PessoaFisica):
    """Retorna pares ``(queryset, user_type)`` para os modelos com subtipos, senão ``None``."""
    if model is User:
        return [
            (model.objects.filter(eh_servidor=True), 'servidor'),
            (model.objects.filter(eh_prestador=True), 'prestador'),
            (model.objects.filter(eh_aluno=True), 'aluno'),
        ]
    if model._meta.app_label == 'comum' and model.__name__ == 'Vinculo':
        return [
            (model.objects.filter(tipo_relacionamento__model='servidor'), 'servidor'),
            (model.objects.filter(tipo_relacionamento__model='prestadorservico'), 'prestador'),
            (model.objects.filter(tipo_relacionamento__model='aluno'), 'aluno'),
        ]
    if model is Pessoa:
        return [
            (model.objects.filter(pessoafisica__eh_servidor=True), 'servidor'),
            (model.objects.filter(pessoafisica__eh_prestador=True), 'prestador'),
            (model.objects.filter(pessoafisica__eh_aluno=True), 'aluno'),
        ]
    if model is PessoaFisica:
        return [
            (model.objects.filter(eh_servidor=True), 'servidor'),
            (model.objects.filter(eh_prestador=True), 'prestador'),
            (model.objects.filter(eh_aluno=True), 'aluno'),
        ]
    return None


def diagnostic_entries_for_model(model, limit):
    """Gera as entradas de relatório de um modelo (uma por subtipo, quando houver).

    Para ``User``/``Vinculo``/``Pessoa``/``PessoaFisica`` emite uma entrada por
    subtipo (servidor/prestador/aluno); para os demais, uma entrada única.
    """
    from comum.models import User
    from rh.models import Pessoa, PessoaFisica

    try:
        splits = _diagnostic_user_splits(model, User, Pessoa, PessoaFisica)
        if splits:
            return [run_autocomplete_diagnostic(model, qs, limit, {'user_type': tipo}) for qs, tipo in splits]
        return [run_autocomplete_diagnostic(model, model.objects.all(), limit)]
    except Exception as e:
        return [{'app': model._meta.app_label, 'model': model.__name__, 'error': str(e)}]


def filter_diagnostics_report(report, selected_app, declared_choice):
    """Filtra o relatório por app e pelo tri-estado ``declared`` (segurança extra)."""
    filtrado = []
    for e in report:
        if selected_app and selected_app != e.get('app', ''):
            continue
        if declared_choice == 'declared' and not e.get('has_declared'):
            continue
        if declared_choice == 'not_declared' and e.get('has_declared'):
            continue
        filtrado.append(e)
    return filtrado


def summarize_diagnostics_report(report_filtered):
    """Calcula as estatísticas-resumo (total, melhorados/piorados/iguais, média %)."""
    deltas = [e['delta'] for e in report_filtered if isinstance(e.get('delta'), int)]
    pct_list = [e['delta_pct'] for e in report_filtered if e.get('delta_pct') is not None]
    improved = worsened = unchanged = 0
    for d in deltas:
        if d > 0:
            improved += 1
        elif d < 0:
            worsened += 1
        else:
            unchanged += 1
    avg_pct = round(sum(pct_list) / len(pct_list), 1) if pct_list else None
    return {'total': len(report_filtered), 'improved': improved, 'worsened': worsened, 'unchanged': unchanged, 'average_pct': avg_pct}
