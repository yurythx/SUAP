from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from djtools.contrib.admin.filters.queryset import QuerysetACListFilter
from processo_eletronico.models import Processo, TipoProcesso


@pytest.mark.parametrize('valor', ['', [''], [], (), ('',)])
def test_filtro_autocomplete_vazio_nao_restringe_consulta(valor: str | list[str] | tuple[str, ...]) -> None:
    request = RequestFactory().get('/admin/processo_eletronico/processo/', {'tipo_processo__id__exact': ''})
    model_admin = SimpleNamespace(list_filter_multiple_choices=[], list_filter_autocomplete_form_filters={})
    filtro = QuerysetACListFilter(TipoProcesso.objects.all())(
        Processo._meta.get_field('tipo_processo'),
        request,
        {'tipo_processo__id__exact': valor},
        Processo,
        model_admin,
        field_path='tipo_processo',
    )

    assert filtro.queryset(request, Processo.objects.all()) is None


@pytest.mark.parametrize('valor', ['1,2', ['1', '2'], ['1,2']])
def test_filtro_autocomplete_multiplo_preserva_ids_selecionados(valor: str | list[str]) -> None:
    request = RequestFactory().get('/admin/processo_eletronico/processo/')
    model_admin = SimpleNamespace(list_filter_multiple_choices=['tipo_processo'], list_filter_autocomplete_form_filters={})
    filtro = QuerysetACListFilter(TipoProcesso.objects.all())(
        Processo._meta.get_field('tipo_processo'),
        request,
        {'tipo_processo__id__in': valor},
        Processo,
        model_admin,
        field_path='tipo_processo',
    )

    consulta = filtro.queryset(request, Processo.objects.all())

    assert consulta is not None
    sql, parametros = consulta.query.sql_with_params()
    assert ' IN (' in sql
    assert set(parametros) == {1, 2}


@pytest.mark.parametrize('valor', ['1', ['1'], ('1',)])
def test_filtro_autocomplete_simples_preserva_selecao(valor: str | list[str] | tuple[str, ...]) -> None:
    request = RequestFactory().get('/admin/processo_eletronico/processo/')
    model_admin = SimpleNamespace(list_filter_multiple_choices=[], list_filter_autocomplete_form_filters={})
    filtro = QuerysetACListFilter(TipoProcesso.objects.all())(
        Processo._meta.get_field('tipo_processo'),
        request,
        {'tipo_processo__id__exact': valor},
        Processo,
        model_admin,
        field_path='tipo_processo',
    )

    assert filtro.value() == '1'
