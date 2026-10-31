import json

from django.db.models.query import QuerySet
from django.forms.widgets import (
    Select,
    Widget,
)
from django.utils.datastructures import MultiValueDict
from django.utils.safestring import mark_safe

from djtools.contrib.auth.helpers import has_add_permission, has_change_permission
from djtools.utils import (
    encrypt,
    randomic,
    render_to_string,
    timeless_dump_qs,
)


def get_change_list_url(cls):
    return f'/admin/{cls._meta.app_label}/{cls.__name__.lower()}/'


def get_add_another_url(cls):
    return f'/admin/{cls._meta.app_label}/{cls.__name__.lower()}/add/'


class AutocompleteWidget(Select):
    def __init__(
        self,
        url=None,
        id_=None,
        attrs=None,
        show=True,
        help_text=None,
        readonly=False,
        side_html=None,
        label_value=None,
        form_filters=None,
        search_fields=None,
        manager_name=None,
        qs_filter=None,
        can_add_related=True,
        submit_on_select=False,
        multiple=False,
        ext_combo_template=None,
        readonly_no_value_text='Nenhuma seleção foi feita.',
        min=None,
        **options,
    ):
        self.can_add_related = can_add_related
        self.help_text = help_text
        self.show = show
        self.attrs = attrs and attrs.copy() or {}
        self.id_ = id_ or randomic()
        self.url = url
        self.readonly = readonly
        self.readonly_no_value_text = readonly_no_value_text
        self.side_html = side_html
        self.form_filters = form_filters
        self.submit_on_select = submit_on_select
        self.allow_multiple_selected = multiple
        self.ext_combo_template = ext_combo_template or str

        options['extraParams'] = options.get('extraParams', {})
        min_chars = min if min is not None else options.pop('min_chars', None)
        if min_chars is not None:
            options['extraParams']['min_chars'] = min_chars

        if readonly:
            options['extraParams']['readonly'] = 1

        if label_value:
            options['extraParams']['label_value'] = label_value
        if form_filters:
            if not isinstance(form_filters, tuple | list):
                raise ValueError('`form_filters` deve ser lista ou tupla')
            options['extraParams']['form_parameter_names'] = json.dumps(form_filters)

        if search_fields:
            if not isinstance(search_fields, tuple | list):
                raise ValueError('`search_fields` deve ser lista ou tupla')
            options['extraParams']['search_fields'] = ','.join(search_fields)
        if manager_name:
            if not isinstance(manager_name, str):
                raise ValueError('`manager_name` deve ser basestring')
            options['extraParams']['manager_name'] = manager_name
        if qs_filter:
            if not isinstance(qs_filter, str):
                raise ValueError('`qs_filter` deve ser basestring')
            options['extraParams']['qs_filter'] = qs_filter
        if 'ext_combo_template' in options['extraParams']:
            # http://stackoverflow.com/questions/1253528/is-there-an-easy-way-to-pickle-a-python-function-or-otherwise-serialize-its-cod#answers-header
            # serializa a função
            template = options['extraParams'].pop('ext_combo_template')
            code_string = f'{template.__module__}:{template.__name__}'
            code_string = timeless_dump_qs(code_string)
            options['extraParams']['ext_combo_template'] = code_string

        self.options = options
        super().__init__(self.attrs)

    def render(self, name, value=None, attrs=None, renderer=None):
        if not hasattr(self.choices, 'queryset'):
            if isinstance(value, str):
                value = [value]
            context = {
                'id': self.id_,
                'values': value,
                'options': self.options,
                'form_filters': self.form_filters,
                'name': name,
                'side_html': self.side_html,
                'readonly': self.readonly,
                'readonly_no_value_text': self.readonly_no_value_text,
                'attrs': self.attrs,
                'show': self.show,
                'help_text': self.help_text,
                'submit_on_select': self.submit_on_select,
                'can_add_related': self.can_add_related,
                'allow_multiple_selected': self.allow_multiple_selected,
                'static': True,
                'choices': self.choices,
            }
            output = render_to_string('djtools/templates/widgets/select2.html', context)
            return mark_safe(output)

        model_cls = self.choices.queryset.model
        if self.readonly and hasattr(self.readonly, 'pk'):
            return mark_safe(f'{self.readonly} <input type="hidden" name="{name}" value="{self.readonly.pk}">')
        values = value or []
        if not isinstance(values, str | int | model_cls | list | QuerySet):
            raise ValueError(f'value must be basestring, int or a models.Model instance. Got {value}.')
        if isinstance(values, model_cls):
            values = [[value.pk, self.ext_combo_template(value)]]
        elif isinstance(values, int) or (isinstance(values, str) and values.isdigit()):
            values = [[values, self.ext_combo_template(model_cls.objects.filter(pk=values).first())]]
        elif isinstance(values, QuerySet):
            values = []
            for obj in value:
                if isinstance(obj, int):
                    values.append([obj, self.ext_combo_template(model_cls.objects.filter(pk=obj).first())])
                else:
                    values.append([obj.pk, self.ext_combo_template(obj)])
        elif values:
            qs = model_cls.objects.none()
            try:
                qs = model_cls.objects.filter(pk__in=values)
            except TypeError:
                pks = [i.pk for i in values]
                qs = model_cls.objects.filter(pk__in=pks)
            except ValueError:
                # values is not int
                pass
            values = []
            for obj in qs:
                values.append([obj.pk, self.ext_combo_template(obj)])

        self.url = self.url or f'/json/{model_cls._meta.app_label}/{model_cls.__name__.lower()}/'
        context = {
            'id': self.id_,
            'values': values,
            'options': self.options,
            'form_filters': self.form_filters,
            'name': name,
            'url': self.url,
            'change_list_url': get_change_list_url(model_cls),
            'add_another_url': get_add_another_url(model_cls),
            'has_change_permission': has_change_permission(model_cls),
            'has_add_permission': has_add_permission(model_cls),
            'side_html': self.side_html,
            'readonly': self.readonly,
            'readonly_no_value_text': self.readonly_no_value_text,
            'attrs': self.attrs,
            'show': self.show,
            'control': timeless_dump_qs(self.choices.queryset.all().query),
            'help_text': self.help_text,
            'submit_on_select': self.submit_on_select,
            'can_add_related': self.can_add_related,
            'allow_multiple_selected': self.allow_multiple_selected,
        }
        output = render_to_string('djtools/templates/widgets/select2.html', context)
        return mark_safe(output)


class AjaxSelectMultiplePopup(Widget):
    def __init__(self, form_filters=None, required_form_filters=False, **options):
        self.required_form_filters = required_form_filters
        self.list_template = options.pop('list_template', 'popup_multiple_choices.html')

        options['extraParams'] = options.get('extraParams', {})

        if form_filters:
            if not isinstance(form_filters, tuple | list):
                raise ValueError('`form_filters` deve ser lista ou tupla')
            options['extraParams']['form_parameter_names'] = ','.join([i[0] for i in form_filters])
            options['extraParams']['django_filter_names'] = ','.join([i[1] for i in form_filters])
            options['extraParams']['required_form_filters'] = required_form_filters

        self.options = json.dumps(options)
        super(self.__class__, self).__init__(None)

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        s = ''
        ss = ''
        items = []

        if value and value != ['']:
            if isinstance(value, tuple | list | QuerySet):
                value = [item.pk if hasattr(item, 'pk') else item for item in value]
            else:
                value = [value.pk] if hasattr(value, 'pk') else [value]
            items = self.choices.queryset.filter(id__in=value)

            for obj in items:
                if not s:
                    s = obj.pk
                    ss = str(obj)
                else:
                    s = f'{s};{obj.pk}'
                    ss = f'{ss}, {obj!s}'

        context = {
            'name': name,
            's': s,
            'ss': ss,
            'options': self.options,
            'control': timeless_dump_qs(self.choices.queryset.all().query),
            'list_template': encrypt(self.list_template),
        }

        output = render_to_string('djtools/templates/ajax_selectmultiple_popup_widget.html', context)

        return mark_safe(output)

    def value_from_datadict(self, data, files, name):
        if isinstance(data, MultiValueDict):
            return name in data and data[name] and data[name].split(';') or []
        return data.get(name, None)
