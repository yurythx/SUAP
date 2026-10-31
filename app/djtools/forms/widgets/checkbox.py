from django.forms.widgets import (
    CheckboxInput,
    CheckboxSelectMultiple,
)
from django.utils.encoding import force_str


class RenderableCheckboxSelect(CheckboxSelectMultiple):
    def __init__(self, template_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template_name = template_name

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        objects = []
        for object in self.choices.queryset.all():
            object.widget = CheckboxInput(attrs.copy()).render(name, object.id, attrs.copy())
            objects.append(object)
        context['objects'] = objects
        return context


class CheckboxTooltipSelectPlus(CheckboxSelectMultiple):
    template_name = 'widgets/checkbox_tooltip_select.html'

    def __init__(self, tooltip_field, attrs=None, choices=()):
        self.tooltip_field = tooltip_field
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        objects = []
        str_values = value and {force_str(v) for v in value} or set()
        for object in self.choices.queryset.all():
            object.widget = CheckboxInput(check_test=lambda v: force_str(v) in str_values).render(name, object.id, attrs.copy())
            object.title = getattr(object, self.tooltip_field)
            objects.append(object)
        context['objects'] = objects
        return context
