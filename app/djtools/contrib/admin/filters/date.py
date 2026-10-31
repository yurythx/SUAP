from datetime import datetime

from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters

FILTER_PREFIX = 'drf__'


class DateRangeListFilter(admin.FieldListFilter):
    template = 'admin/daterangefilter.html'

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.lookup_kwarg_since = f'{FILTER_PREFIX}{field_path}__gte'
        self.lookup_kwarg_until = f'{FILTER_PREFIX}{field_path}__lte'
        super().__init__(field, request, params, model, model_admin, field_path)

    def expected_parameters(self):
        return [self.lookup_kwarg_since, self.lookup_kwarg_until]

    def choices(self, changelist):
        return (
            {'field_path': self.field_path, 'value': changelist.params.get(self.lookup_kwarg_since, '')},
            {'field_path': self.field_path, 'value': changelist.params.get(self.lookup_kwarg_until, '')},
        )

    def _clean_input_prefix(self, input_):
        return {key.split(FILTER_PREFIX)[1] if key.startswith(FILTER_PREFIX) else key: val for (key, val) in list(input_.items())}

    def _get_value(self, name, request):
        value = request.GET.get(name)
        if value:
            try:
                date_ok = False
                for date_f_str in ['%d/%m/%Y', '%Y-%m-%d']:
                    try:
                        value = datetime.strptime(value, date_f_str).date()
                        date_ok = True
                    except Exception:
                        continue
                if not date_ok:
                    raise ValueError
            except ValueError as erro:
                raise IncorrectLookupParameters(erro)
        return value

    def queryset(self, request, queryset):
        lookup_kwarg_since_value = self._get_value(self.lookup_kwarg_since, request)
        lookup_kwarg_until_value = self._get_value(self.lookup_kwarg_until, request)
        filter_params = {}
        if lookup_kwarg_since_value or lookup_kwarg_until_value:
            if lookup_kwarg_since_value:
                filter_params[self.lookup_kwarg_since] = lookup_kwarg_since_value
            if lookup_kwarg_until_value:
                filter_params[self.lookup_kwarg_until] = lookup_kwarg_until_value

            filter_params = self._clean_input_prefix(filter_params)
            return queryset.filter(**filter_params)
        else:
            return queryset
