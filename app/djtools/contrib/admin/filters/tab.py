from django.contrib import admin
from django.utils.encoding import force_str

from djtools.contrib.admin.views import ChangeListPlus


class TabListFilter(admin.SimpleListFilter):
    title = 'tab'
    parameter_name = 'tab'
    template = 'admin/tablistfilter.html'

    def __init__(self, *args, **kwargs):
        self.model_admin = args[3]
        super().__init__(*args, **kwargs)

    def choices(self, cl):
        queryset = self.model_admin.model.objects.none()
        contador_nas_abas = bool(hasattr(self.model_admin, 'show_count_on_tabs') and self.model_admin.show_count_on_tabs)

        hide_empty_tabs = bool(hasattr(self.model_admin, 'hide_empty_tabs') and self.model_admin.hide_empty_tabs)
        if contador_nas_abas:
            # dicionario que guarda os parametros passados no request
            filtros = {}
            IGNORAR = (*ChangeListPlus.IGNORED_PARAMS, 'tab', 'p', 'e', '_popup')
            search_term = ''
            if self.request.GET.urlencode():
                for key, value in list(self.request.GET.items()):
                    if key not in IGNORAR:
                        if '__in' in key and key[-4:] == '__in':
                            filtros[key] = value.split(',')
                        else:
                            filtros[key] = value == 'True' if value in ['True', 'False'] else value
                    elif key == 'q':
                        search_term = value
            queryset = self.model_admin.get_queryset(self.request)
            filter_simple = []
            filter_listfilter = {}
            filter_fieldlistfilter = {}

            for filter in self.model_admin.get_list_filter(self.request):
                if type(filter) in [str, str]:
                    filter_simple.append(filter)
                elif isinstance(filter, tuple):
                    filter_fieldlistfilter[filter[0]] = filter[1]
                else:
                    filter_listfilter[filter.parameter_name] = filter

            for key, value in list(filtros.items()):
                filtro = (
                    key.replace('__exact', '')
                    .replace('__id', '')
                    .replace('__isnull', '')
                    .replace('drf__', '')
                    .replace('__lte', '')
                    .replace('__gte', '')
                )
                if filtro in filter_simple or filtro in list(filter_fieldlistfilter.keys()):
                    # DateRangeFilter
                    if key.startswith('drf__'):
                        if '/' in value:
                            tokens = value.split('/')
                            queryset = queryset.filter(**{key.replace('drf__', ''): f'{tokens[2]}-{tokens[1]}-{tokens[0]}'})
                        else:
                            queryset = queryset.filter(**{key.replace('drf__', ''): value})
                    else:
                        queryset = queryset.filter(**{key: value})
                elif filtro in list(filter_listfilter.keys()):
                    filtrar = filter_listfilter[key]
                    queryset = filtrar(self.request, {key: [value]}, self.model_admin.model, self.model_admin).queryset(self.request, queryset)
                elif key in filtros:
                    queryset = queryset.filter(**{key: value})
            if search_term:
                queryset = self.model_admin.get_search_results(self.request, queryset, search_term)[0]
        tabs_to_show = self.lookup_choices

        first = self.value() is None
        for lookup, title in tabs_to_show:
            yield {
                'selected': self.value() == force_str(lookup) or first,
                'query_string': cl.get_query_string({self.parameter_name: lookup}, []),
                'display': title,
                'pode_mostrar_contador': contador_nas_abas and title != 'Todos',
                'hide_empty_tabs': hide_empty_tabs,
                'contador': self.queryset_from_tab(self.request, queryset, lookup).distinct().count()
                if contador_nas_abas and title != 'Todos'
                else 0,
            }
            first = False


def GetTabFromFieldValue(from_field_values):
    class TabFromFieldValueListFilter(TabListFilter):
        def __init__(self, *args, **kwargs):
            self.field = from_field_values
            super().__init__(*args, **kwargs)

        def lookups(self, request, model_admin):
            self.request = request
            return [(value, value) for value in model_admin.get_queryset(request).order_by(self.field).values_list(self.field, flat=True).distinct()]

        def queryset(self, request, queryset):
            if self.value():
                return queryset.filter(**{self.field: self.value()})

        def queryset_from_tab(self, request, queryset, tab):
            return queryset.filter(**{self.field: tab})

    return TabFromFieldValueListFilter


class CustomTabListFilter(TabListFilter):
    def lookups(self, request, model_admin):
        self.model_admin = model_admin
        self.request = request
        return [
            [aba, getattr(model_admin, aba).short_description] if hasattr(getattr(model_admin, aba), 'short_description') else [aba, aba]
            for aba in model_admin.get_all_tabs(request)
        ]

    def queryset(self, request, queryset):
        if self.value() is None:
            tab_name = self.model_admin.get_all_tabs(request)[0]
            tab_func = getattr(self.model_admin, tab_name)
            return tab_func(request, queryset)

        if self.value():
            try:
                return getattr(self.model_admin, self.value())(request, queryset)
            except AttributeError:
                return None

    def queryset_from_tab(self, request, queryset, tab):
        return getattr(self.model_admin, tab)(request, queryset)
