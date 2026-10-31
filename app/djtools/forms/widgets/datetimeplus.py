import datetime
import re

from django.forms.widgets import (
    DateInput,
    DateTimeInput,
    MultiWidget,
    TimeInput,
    Widget,
)
from django.utils import formats
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from djtools.utils import (
    render_to_string,
)


class BrDataWidget(DateTimeInput):
    """
    Define o ``format`` e aplica a máscara javascript a partir da classe.
    """

    format = '%d/%m/%Y'

    def __init__(self, attrs=None, format=None, show_label=True):
        attrs = attrs or {}
        if show_label:
            attrs.update({'class': 'br-data-widget', 'size': '10', 'maxlength': '10'})
        else:
            attrs.update({'class': 'br-data-widget labeless', 'size': '10', 'maxlength': '10'})
        super(DateTimeInput, self).__init__(attrs)
        if format:
            self.format = format


class RegionalDateWidget(DateInput):
    input_type = 'date'
    template_name = 'widgets/date.html'

    def _strptime(self, value: str):
        """
        Varre os formatos de data definidos no settings e tenta converter a ``string`` para ``datetime.date``.

        :param value: data em formato ``string``.
        :return: data em formato ``datetime.date``.
        :raises ValueError: se ``value`` não for compatível com nenhum formato.
        """
        for fmt in formats.get_format(self.format_key):
            try:
                return datetime.date.strptime(value, fmt)
            except ValueError:
                pass
        raise ValueError(_('Invalid date format'))

    def render(self, name, value, attrs=None, renderer=None):
        if isinstance(value, str):
            # Trata a data em formato de string (ignora se não conseguir converter).
            # O widget pode recebê-la como string quando ela não for informada pela interface web (p.ex: via parâmetro GET).
            try:
                value = self._strptime(value)
            except ValueError:
                pass
        if isinstance(value, datetime.date):
            value = value.isoformat()
        attrs = attrs or {}
        attrs.update({'autocomplete': 'off'})
        html = super().render(name, value, attrs)
        return mark_safe(html)


def _tem_segundos(value: str | datetime.time | datetime.datetime | None) -> bool:
    if isinstance(value, str):
        # Valor submetido que volta ao formulário depois de um erro de validação.
        segundos = re.search(r'\d:\d\d:(\d\d)', value)
        return bool(segundos) and segundos.group(1) != '00'
    return isinstance(value, (datetime.time, datetime.datetime)) and bool(value.second)


class RegionalTimeWidget(TimeInput):
    """
    Sem ``step`` o navegador usa o passo padrão de 60 s e não oferece os segundos. O valor já gravado com segundos
    ganha ``step=1`` mesmo assim: com o passo de 60 s o navegador recusaria submeter o formulário (``stepMismatch``).
    """

    input_type = 'time'

    def __init__(self, *args, show_seconds: bool = False, **kwargs):
        self.show_seconds = show_seconds
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        if self.show_seconds or _tem_segundos(value):
            attrs.update({'step': '1'})
        return super().render(name, self.format_value(value), attrs)


class RegionalDateTimeWidget(DateTimeInput):
    """Mesma regra de segundos do ``RegionalTimeWidget``."""

    input_type = 'datetime-local'

    def __init__(self, *args, show_seconds: bool = False, **kwargs):
        self.show_seconds = show_seconds
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        if self.show_seconds or _tem_segundos(value):
            attrs.update({'step': '1'})
        if isinstance(value, datetime.datetime):
            value = value.isoformat().split('.')[0]
        html = super().render(name, value, attrs)
        return mark_safe(html)


class BRDateRangeWidget(MultiWidget):
    def __init__(self, widgets=(RegionalDateWidget, RegionalDateWidget), attrs=None):
        if attrs is None:
            attrs = {}
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ['', '']
        return value

    def render(self, name, value, attrs=None, renderer=None):
        # value is a list of values, each corresponding to a widget
        # in self.widgets.
        if not isinstance(value, list):
            value = self.decompress(value)
        output = []
        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id', None)
        output.append("<div class='br-date-range-container'>")
        for i, widget in enumerate(self.widgets):
            try:
                widget_value = value[i]
            except IndexError:
                widget_value = None
            if id_:
                final_attrs = dict(final_attrs, id=f'{id_}_{i}')
            output.append(widget.render(f'{name}_{i}', widget_value, final_attrs))
            if i == 0:
                output.append('<span style="padding: 0px 10px 0px 4px">até</span>')
        output.append('</div>')
        return mark_safe(''.join(output))


class SelectDaysWidget(Widget):
    """
    value = {
        'all_selected': True/False/None,
        'days_selected': [date, date, date, date, ...]/[]/None
    }
    """

    def render(self, name, value, attrs=None, renderer=None):
        ctx = self.attrs or attrs or {}
        value = value or {'all_selected': False, 'days_selected': []}
        ctx.update(
            {
                'name': name,
                'value': value,
                'days_choices': dict([[day, day in value.get('days_selected', [])] for day in self.days_choices]),
                'can_select_all': self.can_select_all,
                'all_selected': value.get('all_selected', False) and not value.get('days_selected', []),
                'any_day_selected': bool(value.get('days_selected', [])),
                'label_empty_select': self.label_empty_select,
                'label_all_select': self.label_all_select,
                'label_custom_select': self.label_custom_select,
                'label_day_prefix': self.label_day_prefix,
            }
        )
        output = render_to_string('djtools/templates/select_days_widget.html', ctx)
        return mark_safe(output)

    def value_from_datadict(self, data, files, name):
        field_all_selected_value = data.get(f'{name}_all', 'off')
        all_selected = field_all_selected_value == 'on'
        days_selected = []
        if not all_selected:
            for day_fieldname in data:
                # day_fieldname = 'fieldname_day_DDMMYYYY'
                if f'{name}_day_' in day_fieldname:
                    field_day_selected_value = data.get(day_fieldname, 'off')
                    day_str = None
                    try:
                        day_selected = field_day_selected_value == 'on'
                        if day_selected:
                            day_str = day_fieldname.split('_day_')[1]
                    except Exception:
                        pass
                    if day_str:
                        days_selected.append(datetime.datetime.strptime(day_str, '%d%m%Y').date())
        return {'all_selected': all_selected, 'days_selected': days_selected}
