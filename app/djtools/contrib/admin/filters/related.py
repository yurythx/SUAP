from django.contrib import admin


class RelatedOnlyFieldListFilterPlus(admin.RelatedOnlyFieldListFilter):
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.allow_multiple_choices = field.name in model_admin.list_filter_multiple_choices
        self.lookup_vals = self.allow_multiple_choices and request.GET.getlist(self.lookup_kwarg) or []

    def field_choices(self, field, request, model_admin):
        pk_qs = model_admin.get_queryset(request).distinct().values_list(f'{self.field_path}__pk', flat=True)
        try:
            return field.get_choices(include_blank=False, limit_choices_to={'pk__in': pk_qs})
        except Exception:
            return [x for x in field.get_choices(include_blank=False) if x[0] in pk_qs and True or False]

    def queryset(self, request, queryset):
        if self.allow_multiple_choices and self.lookup_vals:
            self.used_parameters.pop(self.lookup_kwarg, None)
            self.used_parameters[self.lookup_kwarg.replace('exact', 'in')] = self.lookup_vals
        return super().queryset(request, queryset)

    def choices(self, changelist):
        if not self.allow_multiple_choices:
            yield {
                'selected': self.lookup_val is None and not self.lookup_val_isnull,
                'query_string': changelist.get_query_string(remove=[self.lookup_kwarg, self.lookup_kwarg_isnull]),
                'display': 'Todos',
            }
        for pk_val, val in self.lookup_choices:
            yield {
                'selected': self.lookup_val == str(pk_val) or (self.allow_multiple_choices and str(pk_val) in self.lookup_vals),
                'query_string': changelist.get_query_string({self.lookup_kwarg: pk_val}, [self.lookup_kwarg_isnull]),
                'display': val,
            }
        if not self.allow_multiple_choices:
            if self.include_empty_choice:
                yield {
                    'selected': bool(self.lookup_val_isnull),
                    'query_string': changelist.get_query_string({self.lookup_kwarg_isnull: 'True'}, [self.lookup_kwarg]),
                    'display': self.empty_value_display,
                }
