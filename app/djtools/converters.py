import datetime


class DateDMYConverter:
    regex = '[0-9]{4}[0-9]{2}[0-9]{2}'

    def to_python(self, value):
        return datetime.datetime.strptime(value, '%d%m%Y').date()

    def to_url(self, value):
        return value.strftime('%d%m%Y')
