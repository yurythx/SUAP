import json

from django.forms.widgets import (
    HiddenInput,
    TextInput,
    Widget,
)
from django.utils.safestring import mark_safe

from djtools.utils import (
    render_to_string,
)


class DictInputWidget(HiddenInput):
    def __init__(self, *args, items=None, widget=None, initial=None, verbose_name=None, **kwargs):
        self.items = items
        self.initial = initial
        self.widget = widget() if widget else TextInput()
        self.verbose_name = verbose_name or ''
        super().__init__(*args, **kwargs)
        self.error_message = None

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        if value is None and self.initial:
            value = '|'.join([str(self.initial.get(k, '')) for k in self.initial])
        elif isinstance(value, dict):
            value = '|'.join([str(value.get(k, '')) for k in self.items])
        else:
            value = value or ''
        if len(value.split('|')) == len(self.items):
            values = value.split('|')
        else:
            values = ['' for k in self.items]
        for i, k in enumerate(self.items.keys()):
            self.items[k][self.verbose_name] = self.widget.render(f'{k}_item', values[i])
        header = []
        for v in self.items.values():
            header = list(v.keys())
            break
        context = {'items': self.items.values(), 'name': name, 'header': header, 'value': value, 'error_message': self.error_message}
        output = render_to_string('widgets/template_dict_widget.html', context)
        return mark_safe(output)


class JSONEditorWidget(Widget):
    template_name = 'widgets/jsoneditor.html'

    class Media:
        js = ('/static/djtools/jsoneditor.js', '/static/djtools/jsoneditor_init.js')

    def __init__(self, schema, options, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schema = schema
        self.options = options

    def get_json_url(self, value, name):
        if isinstance(value, dict):
            return {name: json.dumps(value)}
        else:
            urlname = name + '_url'
            return {urlname: value}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        update = self.get_json_url(self.schema, 'schema')
        context.update(update)
        update = self.get_json_url(self.options, 'options')
        context.update(update)

        context['widget']['type'] = 'hidden'
        return context
