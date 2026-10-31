import re

from django.contrib import admin


class PassThroughFilter(admin.SimpleListFilter):
    title = ''
    parameter_name = 'pt'
    template = 'admin/hidden_filter.html'

    def lookups(self, request, model_admin):
        return ((request.GET.get(self.parameter_name), ''),)

    def queryset(self, request, queryset):
        return queryset


class SimpleListModelFilter(admin.SimpleListFilter):
    def value(self):
        value = super().value()
        if value:
            value = re.search(r'\d+', value).group()
        return value
