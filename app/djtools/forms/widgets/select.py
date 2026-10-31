import itertools

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models.query import QuerySet
from django.forms.utils import flatatt
from django.forms.widgets import (
    CheckboxInput,
    Select,
    SelectMultiple,
)
from django.utils.encoding import force_str
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from djtools.utils import encrypt, randomic, render_to_string, timeless_dump_qs


class ChainedSelectWidget(Select):
    def render(self, name, value, attrs=None, choices=(), renderer=None):
        id_ = attrs['id']
        if not value:
            value = self.initial

        data = ''
        if self.qs_filter:
            data += f", qs_filter: '{self.qs_filter}'"

        options = {}
        attrs['name'] = name
        if self.form_filters:
            if not isinstance(self.form_filters, tuple | list):
                raise ValueError('`form_filters` deve ser lista ou tupla')
            options['form_parameter_names'] = ','.join([i[0] for i in self.form_filters])
            options['django_filter_names'] = ','.join([i[1] for i in self.form_filters])

        options['is_required'] = 'true' if self.is_required else 'false'
        context = {
            'id': id_,
            'url': self.url,
            'initial': value,
            'obj_value': 'id',
            'obj_label': self.obj_label,
            'empty_label': self.empty_label,
            'data': data,
            'options': options,
            'qs_filter_params_map': self.qs_filter_params_map,
        }
        if self.queryset:
            context['control'] = timeless_dump_qs(self.queryset.all().query)

        final_attrs = self.build_attrs(attrs)
        output = [format_html('<select{0}>', flatatt(final_attrs))]
        output.append('</select>')
        output.append(render_to_string('djtools/templates/chainedselect_widget.html', context))
        return mark_safe('\n'.join(output))


class CheckboxSelectMultiplePlus(SelectMultiple):
    def __init__(self, disable_mark_all=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disable_mark_all = disable_mark_all

    class Media:
        extend = False
        js = ('djtools/widgets/js/marcar_todos_checkbox.js',)

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        mark_all = ''
        if value is None:
            value = []
            mark_all = 'markall'
        has_id = attrs and 'id' in attrs
        attrs['name'] = name
        final_attrs = self.build_attrs(self.attrs, attrs)
        output = ['<ul class="checkboxes">']
        # Normalize to strings
        str_values = {force_str(v) for v in value}
        for i, (option_value, option_label) in enumerate(itertools.chain(self.choices, choices)):
            # If an ID attribute was given, add a numeric index as a suffix,
            # so that the checkboxes don't all have the same ID attribute.
            if has_id:
                final_attrs = dict(final_attrs, id='{}_{}'.format(attrs['id'], i))
                label_for = format_html(' for="{0}"', final_attrs['id'])
            else:
                label_for = ''

            cb = CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
            option_value = force_str(option_value)
            rendered_cb = cb.render(name, option_value)
            option_label = force_str(option_label)
            output.append(format_html('<li><label{0}>{1} {2}</label></li>', label_for, rendered_cb, option_label))
        output.append('</ul>')
        if str_values:
            label = 'Desmarcar todos'
        else:
            label = 'Marcar todos'
            mark_all = 'markall'
        if self.disable_mark_all:
            button = ''
        else:
            button = format_html('<button type="button" data-elemento="{0}" class="btn {1}">{2}</button>', name, mark_all, label)
        output.append(format_html('<div class="checkbutton">{0}</div>', button))
        return mark_safe('\n'.join(output))

    def id_for_label(self, id_):
        # See the comment for RadioSelect.id_for_label()
        if id_:
            id_ += '_0'
        return id_


class SelectPopup(Select):
    allow_multiple_selected = False
    template = 'djtools/templates/popup_choice_field_widget.html'

    def __init__(self, *args, **kwargs):
        self.form_filters = kwargs.pop('form_filters', None)
        self.list_template = kwargs.pop('list_template', 'popup_choices.html')
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        options = {}
        if self.form_filters:
            if not isinstance(self.form_filters, tuple | list):
                raise ValueError('`form_filters` deve ser lista ou tupla')
            options['form_parameter_names'] = ','.join([i[0] for i in self.form_filters])
            options['django_filter_names'] = ','.join([i[1] for i in self.form_filters])

        s = ''
        ss = ''
        if value:
            if isinstance(value, tuple | list | QuerySet):
                value = [item.pk if hasattr(item, 'pk') else item for item in value]
            else:
                value = [value.pk] if hasattr(value, 'pk') else [value]
            try:
                for obj in self.choices.queryset.filter(id__in=value):
                    if not s:
                        s = obj.pk
                        ss = str(obj)
                    else:
                        s = f'{s};{obj.pk}'
                        ss = f'{ss}, {obj!s}'
            except Exception:
                pass

        qs = self.choices.queryset.all() if hasattr(self.choices.queryset, 'all') else self.choices.queryset
        qs = timeless_dump_qs(list(qs))
        disabled = False
        if attrs and type(attrs) is dict:
            disabled = attrs.get('disabled', False)

        context = {
            'name': name,
            'qs': qs,
            's': s,
            'ss': ss,
            'options': options,
            'disabled': disabled,
            'list_template': encrypt(self.list_template),
            'multiple': self.allow_multiple_selected,
        }
        output = render_to_string(self.template, context)
        return mark_safe(output)


class SelectMultiplePopup(SelectPopup):
    allow_multiple_selected = True
    template = 'djtools/templates/popup_multiple_choice_field_widget.html'

    def __init__(self, *args, **kwargs):
        self.list_template = kwargs.pop('list_template', 'popup_multiple_choices.html')
        super().__init__(*args, **kwargs)

    def value_from_datadict(self, data, files, name):
        return name in data and data[name] and data[name].split(';') or []


class RenderableSelectMultiple(SelectMultiple):
    def __init__(self, template_name=None, max_result=400, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template_name = template_name
        self.max_result = max_result

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        pks = []
        if value is None:
            value = []
        if hasattr(value, '__iter__') and value and hasattr(value[0], 'pk'):
            pks = [obj.pk for obj in value]

        has_id = attrs and 'id' in attrs
        attrs['name'] = name
        str_values = {force_str(v) for v in value}
        i = 0
        objects = []

        qs = hasattr(self.choices.queryset, 'all') and self.choices.queryset.all() or self.choices.queryset
        for obj in qs[0 : self.max_result]:  # querysets maiores que 200 não deveriam ser utilizados nesse tipo de widget
            option_value = obj.pk
            final_attrs = self.build_attrs(attrs)
            if has_id:
                final_attrs = dict(final_attrs, id='{}_{}'.format(attrs['id'], i))
            if option_value in pks:
                final_attrs.update(checked='checked')
            cb = CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
            option_value = force_str(option_value)
            rendered_cb = cb.render(name, option_value)
            obj.widget = rendered_cb
            i += 1
            objects.append(obj)

        template = render_to_string(self.template_name, {'objects': objects, 'attrs': attrs})

        return mark_safe(f'<div class="renderable_select_multiple">{template}</div>')


class FilteredSelectMultiplePlus(FilteredSelectMultiple):
    @property
    def media(self) -> forms.Media:
        # Caminhos-fonte, resolvidos pelo storage: `js/admin_i18n.js` é a saída do bundle `jsi18n` do pipeline e só existe após o
        # `collectstatic` — sem ela o SelectFilter2 aborta no `interpolate` e o widget degrada para um select simples (#17425).
        js = ['djtools/js/admin_i18n.js', 'admin/js/core.js', 'admin/js/SelectBox.js', 'admin/js/SelectFilter2.js']

        return forms.Media(js=js)


class NullBooleanSelect(Select):
    """
    A Select Widget intended to be used with NullBooleanField.
    """

    def __init__(self, attrs=None):
        choices = (
            ('unknown', _('---------')),
            ('true', _('Yes')),
            ('false', _('No')),
        )
        super().__init__(attrs, choices)

    def format_value(self, value):
        try:
            return {
                True: 'true',
                False: 'false',
                'true': 'true',
                'false': 'false',
                # For backwards compatibility with Django < 2.2.
                '2': 'true',
                '3': 'false',
            }[value]
        except KeyError:
            return 'unknown'

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        return {
            True: True,
            'True': True,
            'False': False,
            False: False,
            'true': True,
            'false': False,
            # For backwards compatibility with Django < 2.2.
            '2': True,
            '3': False,
        }.get(value)


class TagsWidget(forms.SelectMultiple):
    template_name = 'widgets/tags.html'

    def __init__(self, attrs=None, help_text=None, id_=None, **kwargs):
        super().__init__(attrs, **kwargs)
        self.id_ = id_ or randomic()
        self.help_text = help_text

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['name'] = name
        context['values'] = value
        context['help_text'] = self.help_text
        context['id'] = self.id_
        return context

    def format_value(self, value):
        if value == '' or value is None:
            return None
        return str(value)
