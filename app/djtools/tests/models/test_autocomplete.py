"""Testes dos helpers de autocomplete (``djtools.utils.autocomplete``).

Foco na paginação sem ``COUNT``, no ``DISTINCT`` condicional e na ordem determinística (#17798) e nos helpers extraídos de
``generate_autocomplete_dict`` (montagem de linha/HTML/texto e pré-carga de
alvos do GenericForeignKey).
"""

from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models import Value
from django.db.models.functions import Concat

from djtools.utils import autocomplete
from djtools.utils.autocomplete import (
    CaptureQueriesContext,
    _build_item_row,
    _build_prefetched_rel_map,
    _ext_combo_value,
    _group_ids_by_ctype,
    _has_duplicating_join,
    _load_targets,
    _related_combo_html,
    _resolve_item_html,
    _resolve_item_text,
    _safe_str,
    generate_autocomplete_dict,
    generic_search_json,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Objetos de apoio (sem DB)
# ---------------------------------------------------------------------------
class _Plain:
    pk = 1
    id = 1

    def __str__(self):
        return 'PLAIN|str\nx'


class _WithCombo:
    pk = 2
    id = 2
    tipo_relacionamento_id = 7
    id_relacionamento = 99

    def __str__(self):
        return 'wc'

    def get_ext_combo_template(self):
        return 'COMBO_HTML'

    def get_ext_combo_template_text(self):
        return 'COMBO_TXT'


class _ComboAttr:
    pk = 3
    id = 3
    get_ext_combo_template = 'ATTR_HTML'  # forma não-callable


class _Raises:
    pk = 4
    id = 4

    def __str__(self):
        return 'rr'

    def get_ext_combo_template(self):
        raise ValueError('boom')

    def get_ext_combo_template_text(self):
        raise ValueError('boom')


class _GFKModel:
    """Modelo com marcadores de GenericForeignKey (apenas para ``hasattr``)."""

    tipo_relacionamento = None
    id_relacionamento = None


class _Target:
    def get_ext_combo_template(self):
        return 'TARGET_HTML'


# ---------------------------------------------------------------------------
# _safe_str
# ---------------------------------------------------------------------------
class TestSafeStr:
    def test_none_vira_vazio(self):
        assert _safe_str(None) == ''

    def test_remove_pipe_e_quebra_de_linha(self):
        assert _safe_str('a|b\nc') == 'a/b c'

    def test_exception_no_str_vira_vazio(self):
        class Boom:
            def __str__(self):
                raise RuntimeError('x')

        assert _safe_str(Boom()) == ''


# ---------------------------------------------------------------------------
# _group_ids_by_ctype
# ---------------------------------------------------------------------------
class TestGroupIdsByCtype:
    def test_agrupa_e_deduplica(self):
        objs = [
            mock.Mock(tipo_relacionamento_id=1, id_relacionamento=10),
            mock.Mock(tipo_relacionamento_id=1, id_relacionamento=10),
            mock.Mock(tipo_relacionamento_id=1, id_relacionamento=11),
            mock.Mock(tipo_relacionamento_id=2, id_relacionamento=20),
        ]
        assert _group_ids_by_ctype(objs) == {1: {10, 11}, 2: {20}}

    def test_ignora_sem_marcadores(self):
        objs = [mock.Mock(tipo_relacionamento_id=None, id_relacionamento=None)]
        assert _group_ids_by_ctype(objs) == {}


# ---------------------------------------------------------------------------
# _ext_combo_value
# ---------------------------------------------------------------------------
class TestExtComboValue:
    def test_metodo_callable(self):
        assert _ext_combo_value(_WithCombo()) == 'COMBO_HTML'

    def test_atributo_nao_callable(self):
        assert _ext_combo_value(_ComboAttr()) == 'ATTR_HTML'


# ---------------------------------------------------------------------------
# _related_combo_html
# ---------------------------------------------------------------------------
class TestRelatedComboHtml:
    def test_model_sem_marcadores_gfk(self):
        assert _related_combo_html(_WithCombo(), object, {}) is None

    def test_sem_ctid_ou_relid(self):
        obj = mock.Mock(tipo_relacionamento_id=None, id_relacionamento=None)
        assert _related_combo_html(obj, _GFKModel, {}) is None

    def test_target_presente_usa_template_do_alvo(self):
        out = _related_combo_html(_WithCombo(), _GFKModel, {(7, 99): _Target()})
        assert out == 'TARGET_HTML'

    def test_target_ausente_retorna_none(self):
        assert _related_combo_html(_WithCombo(), _GFKModel, {}) is None


# ---------------------------------------------------------------------------
# _resolve_item_html
# ---------------------------------------------------------------------------
class TestResolveItemHtml:
    def test_ext_template_ok(self):
        assert _resolve_item_html(_Plain(), None, {}, lambda o: 'X|Y', 'def') == 'X/Y'

    def test_ext_template_levanta_usa_default(self):
        assert _resolve_item_html(_Plain(), None, {}, lambda o: 1 / 0, 'def') == 'def'

    def test_sem_combo_usa_default(self):
        assert _resolve_item_html(_Plain(), None, {}, None, 'def') == 'def'

    def test_combo_metodo_sem_model(self):
        assert _resolve_item_html(_WithCombo(), None, {}, None, 'def') == 'COMBO_HTML'

    def test_combo_levanta_usa_default(self):
        assert _resolve_item_html(_Raises(), None, {}, None, 'def') == 'def'

    def test_target_prefetched(self):
        out = _resolve_item_html(_WithCombo(), _GFKModel, {(7, 99): _Target()}, None, 'def')
        assert out == 'TARGET_HTML'

    def test_target_ausente_cai_no_combo_do_obj(self):
        assert _resolve_item_html(_WithCombo(), _GFKModel, {}, None, 'def') == 'COMBO_HTML'


# ---------------------------------------------------------------------------
# _resolve_item_text
# ---------------------------------------------------------------------------
class TestResolveItemText:
    def test_ext_template_text_ok(self):
        assert _resolve_item_text(_Plain(), lambda o: 'T|t', 'def') == 'T/t'

    def test_ext_template_text_levanta_usa_default(self):
        assert _resolve_item_text(_Plain(), lambda o: 1 / 0, 'def') == 'def'

    def test_metodo_do_obj(self):
        assert _resolve_item_text(_WithCombo(), None, 'def') == 'COMBO_TXT'

    def test_metodo_levanta_usa_default(self):
        assert _resolve_item_text(_Raises(), None, 'def') == 'def'

    def test_sem_metodo_usa_default(self):
        assert _resolve_item_text(_Plain(), None, 'def') == 'def'


# ---------------------------------------------------------------------------
# _build_item_row
# ---------------------------------------------------------------------------
class TestBuildItemRow:
    def test_objeto_simples(self):
        row = _build_item_row(_Plain(), None, {}, None, None, None)
        assert row == {'id': 1, 'html': 'PLAIN/str x', 'text': 'PLAIN/str x'}

    def test_com_combo_e_target(self):
        row = _build_item_row(_WithCombo(), _GFKModel, {(7, 99): _Target()}, None, None, None)
        assert row['id'] == 2
        assert row['html'] == 'TARGET_HTML'
        assert row['text'] == 'COMBO_TXT'

    def test_falha_total_retorna_none(self):
        class Boom:
            @property
            def id(self):
                raise RuntimeError('x')

            @property
            def pk(self):
                raise RuntimeError('x')

        assert _build_item_row(Boom(), None, {}, None, None, None) is None


# ---------------------------------------------------------------------------
# _build_prefetched_rel_map (guardas)
# ---------------------------------------------------------------------------
class TestBuildPrefetchedRelMapGuards:
    def test_model_none(self):
        assert _build_prefetched_rel_map(None, [object()]) == {}

    def test_objs_vazio(self):
        assert _build_prefetched_rel_map(_GFKModel, []) == {}

    def test_model_sem_marcadores(self):
        assert _build_prefetched_rel_map(object, [object()]) == {}


# ---------------------------------------------------------------------------
# _load_targets / _build_prefetched_rel_map (com DB)
# ---------------------------------------------------------------------------
def _make_permission():
    ct = ContentType.objects.get_for_model(Permission)
    return ct, Permission.objects.create(content_type=ct, codename='perm_teste_v9v', name='Perm Teste V9V')


class TestLoadTargets:
    def test_carrega_alvos_por_ctid_pk(self):
        ct, perm = _make_permission()
        out = _load_targets({ct.id: {perm.id}})
        assert out == {(ct.id, perm.id): perm}

    def test_ctid_invalido_retorna_vazio(self):
        assert _load_targets({99999999: {1}}) == {}

    def test_build_prefetched_rel_map_caminho_feliz(self):
        ct, perm = _make_permission()
        obj = mock.Mock(tipo_relacionamento_id=ct.id, id_relacionamento=perm.id)
        out = _build_prefetched_rel_map(_GFKModel, [obj])
        assert out == {(ct.id, perm.id): perm}


# ---------------------------------------------------------------------------
# generate_autocomplete_dict (integração)
# ---------------------------------------------------------------------------
class TestGenerateAutocompleteDict:
    def test_retorna_total_e_itens(self):
        for i in range(3):
            ContentType.objects.create(app_label='v9v_gen', model=f'm{i}')
        qs = ContentType.objects.filter(app_label='v9v_gen').order_by('model')

        res = generate_autocomplete_dict(qs, page=1)

        assert res['total'] == 3
        assert len(res['items']) == 3
        assert all({'id', 'html', 'text'} <= set(item) for item in res['items'])
        assert all(item['text'] for item in res['items'])

    @pytest.mark.parametrize(('quantidade', 'paginas'), [(20, [(1, 20, False), (2, 0, False)]), (21, [(1, 20, True), (2, 1, False)])])
    def test_paginacao_sabe_se_ha_mais_sem_count(self, quantidade, paginas):
        # O select2 dos widgets só lê ``more: page * 20 < total`` (#17798): basta uma linha além da página.
        for i in range(quantidade):
            ContentType.objects.create(app_label='v9v_pag', model=f'm{i:02d}')
        qs = ContentType.objects.filter(app_label='v9v_pag').order_by('model')
        vistos = []

        for page, itens, ha_mais in paginas:
            with CaptureQueriesContext(connection) as ctx:
                res = generate_autocomplete_dict(qs, page=page)

            assert len(res['items']) == itens
            assert (page * 20 < res['total']) is ha_mais
            assert not any('COUNT(' in q['sql'] for q in ctx.captured_queries)
            vistos += [item['id'] for item in res['items']]
        assert vistos == list(qs.values_list('pk', flat=True))


# ---------------------------------------------------------------------------
# generic_search_json: DISTINCT condicional e ordem determinística (#17798)
# ---------------------------------------------------------------------------
def _busca_com_sql(control_qs, q, search_fields):
    from djtools.utils.serialization import timeless_dump_qs

    with CaptureQueriesContext(connection) as ctx:
        res = generic_search_json(ContentType, q=q, search_fields=search_fields, control=timeless_dump_qs(control_qs.query), page=1)
    slice_sql = next(sql for sql in (cq['sql'] for cq in ctx.captured_queries) if 'LIMIT' in sql and 'django_content_type' in sql)
    return [item['id'] for item in res['items']], slice_sql


@pytest.mark.parametrize('distinct_do_widget', [False, True])
def test_empates_na_ordenacao_saem_por_pk_e_sem_distinct(distinct_do_widget):
    # Ordenação por campo não único, como /json/rh/setor/ por 'sigla' (!18415): 'model' empata nos 5.
    criados = [ContentType.objects.create(app_label=f'v9v_ord{i}', model='v9vdup').pk for i in range(5)]
    # o UPDATE regrava as 2 primeiras no fim da tabela: a ordem física deixa de ser a da pk
    ContentType.objects.filter(pk__in=criados[:2]).update(app_label=Concat('app_label', Value('x')))
    control = ContentType.objects.order_by('model')
    if distinct_do_widget:  # sem junção to-many, o DISTINCT do queryset do widget também é redundante
        control = control.distinct()

    primeira, slice_sql = _busca_com_sql(control, 'v9vdup', ['model'])
    segunda, _ = _busca_com_sql(control, 'v9vdup', ['model'])

    assert primeira == segunda == sorted(criados)
    assert 'DISTINCT' not in slice_sql


def test_juncao_to_many_mantem_distinct():
    ct = ContentType.objects.create(app_label='v9v_dup', model='m')
    for code in ('perm_a', 'perm_b', 'perm_c'):
        Permission.objects.create(content_type=ct, codename=code, name=code)
    # filtro via reverse FK (to-many): 3 linhas para 1 ContentType
    control = ContentType.objects.filter(permission__codename__startswith='perm_')

    ids, slice_sql = _busca_com_sql(control, 'v9v_dup', ['app_label'])

    assert ids == [ct.pk]
    assert 'DISTINCT' in slice_sql


# ---------------------------------------------------------------------------
# _has_duplicating_join
# ---------------------------------------------------------------------------
class TestHasDuplicatingJoin:
    def test_sem_join(self):
        assert _has_duplicating_join(ContentType.objects.all()) is False

    def test_join_to_one_nao_duplica(self):
        # Permission.content_type é FK to-one
        assert _has_duplicating_join(Permission.objects.filter(content_type__app_label='auth')) is False

    def test_join_to_many_duplica(self):
        # filtro via reverse FK (ContentType -> Permission) é to-many
        assert _has_duplicating_join(ContentType.objects.filter(permission__codename__startswith='x')) is True

    def test_falha_na_inspecao_assume_true(self):
        class FakeQS:
            @property
            def query(self):
                raise RuntimeError('boom')

        assert _has_duplicating_join(FakeQS()) is True


# ---------------------------------------------------------------------------
# generic_search_json: filtros por palavra e por filter_pks
# ---------------------------------------------------------------------------
def _busca_content_type(**kwargs):
    from djtools.utils.serialization import timeless_dump_qs

    res = generic_search_json(
        ContentType, search_fields=['app_label', 'model'], control=timeless_dump_qs(ContentType.objects.all().query), page=1, **kwargs
    )
    return {ContentType.objects.get(pk=item['id']).natural_key() for item in res['items']}


def test_cada_palavra_precisa_casar_com_algum_campo():
    # "auth" casa com app_label e "permission" com model: só auth.permission tem as duas
    assert _busca_content_type(q='auth permission') == {('auth', 'permission')}


@pytest.mark.parametrize('limite', [None, 1], ids=['ids_da_sonda', 'or_entre_tabelas'])
def test_campo_to_many_entre_os_campos_nao_duplica(monkeypatch, limite):
    # Campos em tabelas diferentes, um deles to-many: o ContentType casado por duas permissões sai uma vez só (#17813).
    if limite is not None:
        monkeypatch.setattr(autocomplete, 'LIMITE_SONDA', limite)
    pelo_app_label = ContentType.objects.create(app_label='v17813', model='m')
    pelas_permissoes = ContentType.objects.create(app_label='outro', model='v17813x')
    for code in ('v17813_a', 'v17813_b'):
        Permission.objects.create(content_type=pelas_permissoes, codename=code, name=code)
    ContentType.objects.create(app_label='nada', model='v1781')

    ids, _ = _busca_com_sql(ContentType.objects.all(), 'v17813', ['app_label', 'permission__codename'])

    assert ids == [pelo_app_label.pk, pelas_permissoes.pk]


@pytest.mark.parametrize('separador', [';', ','])
def test_filter_pks_in_aceita_ponto_e_virgula_e_virgula(separador):
    ids = [ContentType.objects.get_by_natural_key(*chave).pk for chave in (('auth', 'permission'), ('auth', 'group'))]

    assert _busca_content_type(q='auth', filter_pks={'id__in': separador.join(map(str, ids))}) == {('auth', 'permission'), ('auth', 'group')}


def test_palavra_curta_e_ignorada_e_min_chars_invalido_cai_no_padrao():
    # "pe" tem menos de 3 letras: some da busca e sobra só "auth"
    assert _busca_content_type(q='auth pe', min_chars='x') == _busca_content_type(q='auth')
