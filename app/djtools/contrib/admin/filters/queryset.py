from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import Field, Model, QuerySet
from django.http import HttpRequest
from django.utils.encoding import force_str
from django.utils.safestring import mark_safe

from djtools.utils import timeless_dump_qs

if TYPE_CHECKING:
    from django.contrib.admin.views.main import ChangeList

    from djtools.contrib.admin.options import ModelAdminPlus


class AutoCompleteListFilter(admin.FieldListFilter):
    queryset_limit: QuerySet
    module_name: str
    app_name: str
    template = 'admin/autocomplete.html'
    url_autocomplete: str
    filtered_lookups = []

    def __init__(
        self,
        field: Field,
        request: HttpRequest,
        params: dict[str, str | list[str] | tuple[str, ...]],
        model: type[Model],
        model_admin: ModelAdminPlus,
        **kwargs: Any,
    ) -> None:
        self.allow_multiple_choices = field.name in model_admin.list_filter_multiple_choices
        self.queryset_default = self.queryset_limit
        self.url = kwargs.pop('url', self.url_autocomplete)
        self.parameter_name = kwargs.get('field_path')
        if self.allow_multiple_choices:
            self.parameter_name = f'{field.name}__id__in'
        title = kwargs.pop('title', field)
        lookups = {}
        for lookup, value in params.items():
            if self.allow_multiple_choices:
                lookups[lookup] = value
            else:
                if isinstance(value, list | tuple):
                    value = value[0] if value else None
                lookups[lookup.replace('__id__exact', '')] = value
        super().__init__(field, request, params, model, model_admin, **kwargs)
        self.title = title
        self.filtered_lookups = lookups

        if model_admin.list_filter_autocomplete_form_filters and self.parameter_name in model_admin.list_filter_autocomplete_form_filters:
            self.form_filters = model_admin.list_filter_autocomplete_form_filters[self.parameter_name]
        else:
            self.form_filters = {}

        lookup_choices = self.lookups(request, model_admin)
        if lookup_choices is None:
            lookup_choices = ()
        self.lookup_choices = list(lookup_choices)

    def value(self) -> str | list[str] | None:
        value = self.filtered_lookups.get(self.parameter_name)
        if self.allow_multiple_choices:
            if value is None:
                value = []
            elif isinstance(value, str):
                value = value.split(',')
            elif isinstance(value, list):
                ids = []
                for pk in value:
                    [ids.append(split_pk) for split_pk in pk.split(',')]
                value = ids
            value = list(set(value))
        return value

    def lookups(self, request: HttpRequest, model_admin: ModelAdminPlus) -> list[tuple[str, str]]:
        return [('chave', 'valor')]

    # ADICIONAR OU REMOVER?
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet | None:
        if self.value() and not isinstance(self.value(), str):
            args = {self.parameter_name: self.value()}
            queryset = queryset.filter(**args)
            if hasattr(queryset, 'autocomplete'):
                queryset = queryset.autocomplete()
            return queryset

    def choices(self, changelist: ChangeList) -> Iterator[dict[str, Any]]:
        if self.allow_multiple_choices:
            yield from self._opcoes_multiplas(changelist)
        else:
            yield from self._opcoes_simples(changelist)

    def _opcoes_multiplas(self, changelist: ChangeList) -> Iterator[dict[str, Any]]:
        related_model = changelist.model
        for field_name in self.parameter_name.split('__'):
            if field_name != 'in':
                field_descriptor = related_model._meta.get_field(field_name)
                related_model = field_descriptor.related_model

        base_queryset = self.queryset_default.all()
        if hasattr(field_descriptor, 'get_queryset'):
            field_descriptor.get_queryset().all()

        if hasattr(base_queryset, 'autocomplete'):
            base_queryset = base_queryset.autocomplete()
        control = timeless_dump_qs(base_queryset.query)
        yield {
            'unicode': '',
            'value': '',
            'selected': False,
            'query_string': changelist.get_query_string({}, [self.parameter_name]),
            'display': 'All',
            'url': self.url,
            'parameter_name': self.parameter_name,
            'control': control,
            'form_filters': self.form_filters,
            'options_dafault': {'autoFill': 'true', 'minChars': '2', 'scroll': 'true', 'extraParams': {'control': mark_safe(control)}},
        }
        for value in self.value():
            texto = base_queryset.filter(id=value).first()
            yield {
                'unicode': texto,
                'value': value,
                'selected': True,
                'query_string': changelist.get_query_string({self.parameter_name: value}, []),
                'display': 'title',
                'url': self.url,
                'parameter_name': self.parameter_name,
                'form_filters': self.form_filters,
                'control': control,
                'options_dafault': {'autoFill': 'true', 'minChars': '2', 'scroll': 'true', 'extraParams': {'control': mark_safe(control)}},
            }

    def _opcoes_simples(self, changelist: ChangeList) -> Iterator[dict[str, Any]]:
        related_model = changelist.model
        if '__' in self.parameter_name:
            for field_name in self.parameter_name.split('__'):
                field_descriptor = related_model._meta.get_field(field_name)
                related_model = field_descriptor.related_model
        else:
            field_descriptor = related_model._meta.get_field(self.parameter_name)
            related_model = field_descriptor.related_model
        base_queryset = self.queryset_default.all()
        if hasattr(field_descriptor, 'get_queryset'):
            field_descriptor.get_queryset().all()

        texto = ''
        if self.value() and self.value().isdigit():
            texto = base_queryset.filter(id=self.value()).first()
        if hasattr(base_queryset, 'autocomplete'):
            base_queryset = base_queryset.autocomplete()
        control = timeless_dump_qs(base_queryset.query)
        yield {
            'unicode': texto,
            'value': self.value(),
            'selected': self.value() is not None,
            'query_string': changelist.get_query_string({}, [self.parameter_name]),
            'display': 'All',
            'url': self.url,
            'parameter_name': self.parameter_name,
            'control': control,
            'form_filters': self.form_filters,
            'options_dafault': {'autoFill': 'true', 'minChars': '2', 'scroll': 'true', 'extraParams': {'control': mark_safe(control)}},
        }
        for lookup, title in self.lookup_choices:
            yield {
                'unicode': texto,
                'value': self.value(),
                'selected': self.value() == force_str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}, []),
                'display': title,
                'url': self.url,
                'parameter_name': self.parameter_name,
                'form_filters': self.form_filters,
                'control': control,
                'options_dafault': {'autoFill': 'true', 'minChars': '2', 'scroll': 'true', 'extraParams': {'control': mark_safe(control)}},
            }

    def expected_parameters(self) -> dict[str, str | list[str] | None]:
        return self.filtered_lookups


def QuerysetACListFilter(queryset_limit: QuerySet) -> type[AutoCompleteListFilter]:
    class ConfiguredAutoCompleteListFilter(AutoCompleteListFilter):
        pass

    ConfiguredAutoCompleteListFilter.queryset_limit = queryset_limit
    module_name = queryset_limit.model._meta.app_label
    app_name = queryset_limit.model._meta.model_name
    ConfiguredAutoCompleteListFilter.module_name = module_name
    ConfiguredAutoCompleteListFilter.app_name = app_name
    ConfiguredAutoCompleteListFilter.url_autocomplete = f'/json/{module_name}/{app_name}/'
    return ConfiguredAutoCompleteListFilter
