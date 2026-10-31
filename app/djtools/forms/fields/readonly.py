from django import forms

from djtools.forms.widgets import ReadOnlyWidget, SpanWidget


class ReadOnlyField(forms.Field):
    """
    Um campo de formulário que utiliza o widget ReadOnlyWidget para apresentar o valor.
    """

    def __init__(self, *args, **kwargs):
        """
        Construtor.

        Args:
            label (string): rótulo para a **tag**;
            args (list): lista de argumentos;
            kwargs (dict): dicionário de argumentos nomeados.
        """
        kwargs['widget'] = kwargs.get('widget', ReadOnlyWidget)
        super().__init__(*args, **kwargs)
        self.required = kwargs.get('required', False)
        self.disabled = kwargs.get('disabled', True)

    def to_python(self, value):
        return self.initial or value


class SpanField(forms.Field):
    """
    Um campo de formulário que utiliza o widget SpanWidget para apresentar o valor.
    """

    def __init__(self, label, *args, **kwargs):
        """
        Construtor.

        Args:
            label (string): rótulo para a **tag**;
            args (list): lista de argumentos;
            kwargs (dict): dicionário de argumentos nomeados.
        """
        kwargs['label'] = label
        kwargs['widget'] = kwargs.get('widget', SpanWidget)
        super().__init__(*args, **kwargs)
        self.required = kwargs.get('required', False)
