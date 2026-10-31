from decimal import Decimal

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.aggregates import Sum
from django.db.models.fields.related import ManyToManyField
from django.utils.safestring import mark_safe
from django_tables2 import RequestConfig, SingleTableView, Table
from django_tables2.tables import DeclarativeColumnsMetaclass

from djtools.utils import tl


class PagedFilteredTableView(SingleTableView):
    filter_class = None
    formhelper_class = None
    context_filter_name = 'filter'

    def get_queryset(self, **kwargs):
        qs = super().get_queryset()
        self.filter = self.filter_class(self.request.GET, queryset=qs.filter(**kwargs))
        self.filter.form.helper = self.formhelper_class()
        self.filter.form.helper.form_method = 'post'
        self.filter.form.helper.form_tag = False
        return self.filter.qs

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        page = self.kwargs.get('page') or self.request.GET.get('page') or 1
        RequestConfig(self.request, paginate={'page': page, 'per_page': self.paginate_by}).configure(table)
        return table

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context[self.context_filter_name] = self.filter
        return context


class TableReportPlus(Table):
    tfoot_sum = {}

    class Meta:
        template_name = 'comum/templates/table_plus.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_report = 'relatorio'

    def add_sum_table_foot(self, collumn, conditions=None):
        self.tfoot_sum[collumn] = conditions

    def get_sum_foot(self, column):
        if column in self.tfoot_sum:
            if self.tfoot_sum[column] is not None:
                return (self.data.data.filter(**self.tfoot_sum[column]['+']).aggregate(Sum(column))[f'{column}__sum'] or Decimal('0.0')) - (
                    self.data.data.filter(**self.tfoot_sum[column]['-']).aggregate(Sum(column))[f'{column}__sum'] or Decimal('0.0')
                )

            return self.data.data.aggregate(Sum(column))[f'{column}__sum']

    def get_foot_collumns(self):
        foot_collumns = []
        for column in self._sequence:
            if column in self.tfoot_sum:
                foot_collumns.append(self.get_sum_foot(column))
            else:
                foot_collumns.append('')
        return foot_collumns

    def get_params(self):
        dicionario = {}
        for coluna in self.columns.names():
            dicionario[coluna.upper().replace('_', ' ').split('.')[-1]] = self.columns.columns[coluna].accessor
        return self.data.data, dicionario


def get_table(**kwargs):
    if 'request' in kwargs:
        request = kwargs.pop('request')
    else:
        request = tl.get_request()

    if 'queryset' not in kwargs:
        raise ValueError('Não há queryset definida.')

    queryset = kwargs.pop('queryset')
    table_fields = ()
    if 'fields' in kwargs:
        table_fields = kwargs.pop('fields')

    exclude_fields = ()
    if 'exclude_fields' in kwargs:
        exclude_fields = kwargs.pop('exclude_fields')

    custom_fields = {}
    if 'custom_fields' in kwargs:
        custom_fields = kwargs.pop('custom_fields')

    if 'per_page_field' not in kwargs:
        kwargs['per_page_field'] = 20

    to_export = True
    if 'to_export' in kwargs:
        to_export = kwargs.pop('to_export')

    base_class = kwargs.pop('table_class', TableReportPlus)

    class OnTheFlyTable(base_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        class Meta:
            model = queryset.model
            fields = table_fields
            exclude = exclude_fields

    CustomOnTheFlyTable = DeclarativeColumnsMetaclass('CustomOnTheFlyTable', (OnTheFlyTable,), custom_fields)

    def eh_many2many(modelo, caminho):
        _caminho = caminho.split('.')
        try:
            campo = modelo._meta.get_field(_caminho[0])
        except FieldDoesNotExist:
            return False

        if isinstance(campo, ManyToManyField):
            return True

        if len(_caminho) == 1:
            return False

        if isinstance(campo, models.ForeignKey):
            return eh_many2many(campo.remote_field.model, '.'.join(_caminho[1:]))
        else:
            return eh_many2many(campo.model, '.'.join(_caminho[1:]))

    def my_render(self, value):
        if value.all().exists():
            unicode_list = []
            for objeto in value.all():
                unicode_list.append(str(objeto))
            return mark_safe(', '.join(unicode_list))
        return '-'

    for table_field in table_fields:
        if eh_many2many(queryset.model, table_field):
            name = 'render_' + table_field
            method = my_render
            method.__name__ = name
            setattr(CustomOnTheFlyTable, name, method)

    tabela = CustomOnTheFlyTable(queryset, **kwargs)
    RequestConfig(request, paginate=kwargs['per_page_field']).configure(tabela)
    tabela.to_export = to_export
    return tabela
