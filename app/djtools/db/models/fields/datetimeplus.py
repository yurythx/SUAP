from django.db import models

import djtools.forms.fields as formfields


class DateFieldPlus(models.DateField):
    def formfield(self, *args, **kwargs):
        kwargs.setdefault('form_class', formfields.DateFieldPlus)
        field = super().formfield(**kwargs)
        return field


class TimeFieldPlus(models.TimeField):
    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.TimeFieldPlus)
        return super().formfield(**kwargs)


class DateTimeFieldPlus(models.DateTimeField):
    def formfield(self, **kwargs):
        kwargs.setdefault('form_class', formfields.DateTimeFieldPlus)
        return super(self.__class__, self).formfield(**kwargs)


class LookupDateTimeToDate(models.Transform):
    """
    Uma implementação do SQL lookup quando usar '__date' com datetimes.
    Permite comparar DateTimeField com DateField.
    Exemplo de uso:
        Arquivo.objects.filter(data_geracao__date='2011-08-18')
        ou
        Arquivo.objects.filter(data_geracao__date=datetime.date(2011, 08, 18))
    """

    lookup_name = 'date'

    def as_sql(self, compiler, connection):
        lhs, params = compiler.compile(self.lhs)
        return f'DATE({lhs})', params

    @property
    def output_field(self):
        return models.DateField()


models.DateTimeField.register_lookup(LookupDateTimeToDate)
