from django.contrib.postgres.forms import SimpleArrayField

from djtools.forms.widgets import TagsWidget


class TagsFieldPlus(SimpleArrayField):
    def __init__(self, *args, **kwargs):
        help_text = kwargs.pop('help_text', None) or 'Escreva uma palavra ou frase e aperte Enter para adicionar.'
        readonly = kwargs.pop('readonly', False)
        super().__init__(*args, **kwargs)
        self.widget = TagsWidget(attrs={'readonly': readonly}, help_text=help_text)

    def prepare_value(self, value):
        if value in self.empty_values:
            return []
        if isinstance(value, list):
            return value
        return super().prepare_value(value)
