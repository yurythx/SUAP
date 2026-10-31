import datetime
from collections import OrderedDict

from django import forms

from djtools.forms.widgets import (
    BRDateRangeWidget,
    MaskedInputWidget,
    RegionalDateTimeWidget,
    RegionalDateWidget,
    RegionalTimeWidget,
    SelectDaysWidget,
)
from djtools.utils import formata_timedelta


class DateFieldPlus(forms.DateField):
    widget = RegionalDateWidget

    def clean(self, value):
        if value:
            for format in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    data = datetime.datetime.strptime(value, format)
                    if data.year < 1900:
                        raise forms.ValidationError('O ano precisa ser maior do que 1900.')
                    return data.date()
                except ValueError, TypeError:
                    data = None
                    continue
        return super().clean(value)


class TimeFieldPlus(forms.TimeField):
    def __init__(self, *args, show_seconds: bool = False, **kwargs):
        self.widget = RegionalTimeWidget(show_seconds=show_seconds)
        super().__init__(*args, **kwargs)


class TimeDeltaFieldPlus(forms.CharField):
    """
    Entradas possíveis:
        - Dias: 0 a 99999
        - Horas: 0 a 99999
        - Minutos: 0 a 99999
        - Segundos: 0 a 99999
        - Milissegundos: 0 a 99999

    Caracteres para a máscara de entrada:
        - 0: 0 a 9
        - A: 0 a 5

    Máscara de entrada padrão:
        - Horas: 000 (com 3 dígitos de 000 a 999)
        - Minutos: A0 (com 2 dígitos de 00 a 59)
        - Segundos: A0 (com 2 dígitos de 00 a 59)
    """

    def __init__(
        self,
        mask_days: str = '',
        mask_hours: str = '000',
        mask_minutes: str = 'A0',
        mask_seconds: str = 'A0',
        mask_milliseconds: str = '',
        mask_sep: str = ':',
        min_value: datetime.timedelta | None = datetime.timedelta(seconds=0),
        initial: datetime.timedelta | None = None,
        *args,
        **kwargs,
    ):
        self.mask_days = kwargs.pop('mask_days', mask_days)
        self.mask_hours = kwargs.pop('mask_hours', mask_hours)
        self.mask_minutes = kwargs.pop('mask_minutes', mask_minutes)
        self.mask_seconds = kwargs.pop('mask_seconds', mask_seconds)
        self.mask_milliseconds = kwargs.pop('mask_milliseconds', mask_milliseconds)
        self.mask_sep = kwargs.pop('mask_sep', mask_sep)
        self.min_value = kwargs.pop('min_value', min_value)

        self.masks_positions = OrderedDict()
        position: int = 0  # 1, 2, 3, ...

        if self.mask_days:
            position += 1
            self.masks_positions['d'] = [position, ''.join(['d' for _ in range(len(self.mask_days))])]
        if self.mask_hours:
            position += 1
            self.masks_positions['h'] = [position, ''.join(['h' for _ in range(len(self.mask_hours))])]
        if self.mask_minutes:
            position += 1
            self.masks_positions['m'] = [position, ''.join(['m' for _ in range(len(self.mask_minutes))])]
        if self.mask_seconds:
            position += 1
            self.masks_positions['s'] = [position, ''.join(['s' for _ in range(len(self.mask_seconds))])]
        if self.mask_milliseconds:
            position += 1
            self.masks_positions['z'] = [position, ''.join(['z' for _ in range(len(self.mask_milliseconds))])]

        placeholder = kwargs.pop('placeholder', f'{self.mask_sep}'.join([f'{_[1]}' for _ in self.masks_positions.values()]))

        masks_order = OrderedDict(
            {
                'mask_days': self.mask_days,
                'mask_hours': self.mask_hours,
                'mask_minutes': self.mask_minutes,
                'mask_seconds': self.mask_seconds,
                'mask_milliseconds': self.mask_milliseconds,
            }
        )

        widget_attrs = {
            'mask': f'{self.mask_sep}'.join([mask for mask in masks_order.values() if mask]),
            'patterns': {
                '0': {'regexp': '[0-9]', 'optional': True},
                'A': {'regexp': '[0-5]', 'optional': True},
            },
            'placeholder': placeholder if placeholder is not None else '',
        }

        initial_value = self.prepare_value(initial)

        if initial_value:
            widget_attrs.update({'value': initial_value})

        self.widget = MaskedInputWidget(attrs=widget_attrs, fn_render_value=self.prepare_value)

        super().__init__(*args, **kwargs)

    def clean(self, value):
        value_clean_1 = f'{value}'.strip()
        if value_clean_1 and (len(value_clean_1) != len(self.widget.mask)):
            raise forms.ValidationError('Informe um valor válido.')

        value_clean_2 = self.to_python(value)
        if value_clean_2 is not None and self.min_value and isinstance(value_clean_2, datetime.timedelta) and value_clean_2 < self.min_value:
            raise forms.ValidationError(f'O valor deve ser maior ou igual a {self.format_value(self.min_value)}.')

        return super().clean(value)

    def to_python(self, value) -> datetime.timedelta:
        if value:
            value = f'{value}'.strip()
            values = value.split(f'{self.mask_sep}')
            try:
                days_idx = self.masks_positions.get('d', [0, ''])[0] - 1
                hours_idx = self.masks_positions.get('h', [0, ''])[0] - 1
                minutes_idx = self.masks_positions.get('m', [0, ''])[0] - 1
                seconds_idx = self.masks_positions.get('s', [0, ''])[0] - 1
                milliseconds_idx = self.masks_positions.get('z', [0, ''])[0] - 1
                return datetime.timedelta(
                    days=int(values[days_idx]) if days_idx >= 0 else 0,
                    hours=int(values[hours_idx]) if hours_idx >= 0 else 0,
                    minutes=int(values[minutes_idx]) if minutes_idx >= 0 else 0,
                    seconds=int(values[seconds_idx]) if seconds_idx >= 0 else 0,
                    milliseconds=int(values[milliseconds_idx]) if milliseconds_idx >= 0 else 0,
                )
            except Exception:
                raise forms.ValidationError('Informe um valor válido.')
        return value

    def format_value(self, value: datetime.timedelta) -> str:
        return formata_timedelta(
            value,
            format_start=next(iter(self.masks_positions.keys())),
            format_days='{' + 'd:0{}'.format(f'{len(self.mask_days)}') + '}',
            format_hours='{' + 'h:0{}'.format(f'{len(self.mask_hours)}') + '}',
            format_minutes='{' + 'm:0{}'.format(f'{len(self.mask_minutes)}') + '}',
            format_seconds='{' + 's:0{}'.format(f'{len(self.mask_seconds)}') + '}',
            format_milliseconds='{' + 'z:0{}'.format(f'{len(self.mask_milliseconds)}') + '}',
            format_sep=self.mask_sep,
            hide_milliseconds=bool(not self.mask_milliseconds),
        )

    def prepare_value(self, value) -> str:
        if isinstance(value, datetime.timedelta):
            return self.format_value(value)
        return super().prepare_value(value)


class DateTimeFieldPlus(forms.DateTimeField):
    def __init__(self, *args, show_seconds: bool = False, **kwargs):
        self.widget = RegionalDateTimeWidget(show_seconds=show_seconds)
        super().__init__(*args, **kwargs)


class BRDateRangeField(forms.MultiValueField):
    widget = BRDateRangeWidget

    def __init__(self, fields=None, sum_end_date=False, *args, **kwargs):
        if not fields:
            fields = (DateFieldPlus(), DateFieldPlus())
        super(forms.MultiValueField, self).__init__(*args, **kwargs)
        # Set 'required' to False on the individual fields, because the
        # required validation will be handled by MultiValueField, not by those
        # individual fields.
        for f in fields:
            f.required = False
        self.fields = fields

    def clean(self, value):
        """
        Retorna [(data), (data+1 dia)], pois o formato facilita as pesquisas
        em banco de dados: .filter(date__gt=start_date, date__lt=end_date)
        """
        datefield = DateFieldPlus()
        start_date = value[0]
        end_date = value[1]
        if not self.required and not start_date and not end_date:
            return [start_date, end_date]
        else:
            try:
                start_date = datefield.clean(start_date)
                end_date = datefield.clean(end_date)
            except Exception:
                raise forms.ValidationError('A faixa de datas está inválida.')

        if start_date > end_date:
            raise forms.ValidationError('A data final é menor que a inicial.')
        return [start_date, end_date]


class SelectDaysField(forms.Field):
    """
    value = {
        'all_selected': True/False/None,
        'days_selected': [date, date, date, date, ...]/[]/None
    }
    """

    widget = SelectDaysWidget

    def __init__(
        self,
        days_choices,
        can_select_all=False,
        label_empty_select='---------',
        label_all_select='Todos os dias',
        label_custom_select='Personalizado',
        label_day_prefix='Dia',
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.widget.days_choices = days_choices
        self.widget.can_select_all = can_select_all
        self.widget.label_empty_select = label_empty_select
        self.widget.label_all_select = label_all_select
        self.widget.label_custom_select = label_custom_select
        self.widget.label_day_prefix = label_day_prefix

    def to_python(self, value):
        return value

    def clean(self, value):
        value = value or {}
        all_selected = value.get('all_selected', False)
        days_selected = value.get('days_selected', [])
        if self.required and not all_selected and not days_selected:
            raise forms.ValidationError('Este campo é obrigatório.')
        for day_selected in days_selected:
            if day_selected not in self.widget.days_choices:
                raise forms.ValidationError(f'{day_selected.strftime("%d/%m/%Y")} não é uma opção válida.')
        return value
