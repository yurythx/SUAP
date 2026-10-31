import json

from django.forms.widgets import (
    TextInput,
)


class MaskedInputWidget(TextInput):
    template_name = 'widgets/masked_input.html'

    # máscara de entrada
    # https://igorescobar.github.io/jQuery-Mask-Plugin/docs.html#basic-usage
    mask = ''

    # valida as posições da máscara usando expressões regulares
    # https://igorescobar.github.io/jQuery-Mask-Plugin/docs.html#translation
    patterns = {}

    # gera o valor final que será renderizado (opcional)
    # é uma função com a seguinte assinatura: (value: Any) -> Any
    """
        Problemática:

            class form:
                field_a = ...

                def __init__(...):
                    super()...
                    ...
                    self.fields['field_a'].initial = value

                -> value será considerado o valor FINAL a ser renderizado (já vai direto para o widget)
                -> exceção: o Admin, ao usar o form, processa novamente o value no contexto do field,
                chamado o método prepare_value e somente depois vai para o widget

        Portanto, para inputs mascarados, é interessante que o widget possa re-processar o value antes de renderizar.
    """
    fn_render_value = None

    def __init__(self, attrs=None, fn_render_value=None):
        if not attrs:
            attrs = {}

        attrs.update(
            {
                'data-mask': attrs.get('mask', self.mask),
                'data-patterns': attrs.get('patterns', self.patterns),
                'style': 'max-width: 130px; min-width: 130px;',  # TODO: faltou uma classe css para "estreitar" o input text
            }
        )

        attrs.pop('mask')
        attrs.pop('patterns')

        self.mask = attrs['data-mask']
        self.patterns = attrs['data-patterns']

        if not isinstance(attrs['data-patterns'], dict):
            attrs['data-patterns'] = {}

        attrs['data-patterns'] = json.dumps(attrs['data-patterns'])

        self.fn_render_value = fn_render_value or self.fn_render_value

        super(self.__class__, self).__init__(attrs=attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if self.fn_render_value:
            try:
                value = self.fn_render_value(value)
            except Exception:
                pass
        return super().render(name, value, attrs, renderer)


class IntegerWidget(TextInput):
    input_type = 'number'

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'integer-widget'})
        super().__init__(attrs=attrs)


class AlphaNumericWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'alpha-widget'})
        super().__init__(attrs=attrs)


class AlphaNumericUpperCaseWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'upper-text-widget'})
        super().__init__(attrs=attrs)


class CapitalizeTextWidget(TextInput):
    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        attrs.update({'class': 'capitalize-text-widget'})
        super().__init__(attrs=attrs)
