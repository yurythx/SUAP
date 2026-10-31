###########################################################################
# ReadOnlyForm (Adaptado de http://www.djangosnippets.org/snippets/1340/) #
###########################################################################


from django import forms
from django.utils.html import escape
from django.utils.safestring import mark_safe


class SpanWidget(forms.Widget):
    """
    Renderiza um valor com a tag **<span>**.

    Note:
        Deve ser utilizado no ReadonlyForm ou ReadonlyModelForm)
    """

    def render(self, name, value, attrs=None, renderer=None):
        """
        Cria o código necessário para renderizar o **value**.

        Args:
            name (string): atributo name para o span;
            value (string): valor a ser apresentado;
            attrs (dict): dicionário com um conjunto de atributos;
            renderer (): .

        Returns:
            String com **HTML** **span**.
        """
        attrs['name'] = name
        final_attrs = self.build_attrs(attrs)
        label = self.original_value
        if hasattr(self, 'label_value'):
            label = self.label_value
        return mark_safe(f'<span{forms.utils.flatatt(final_attrs)} >{label}</span>')

    def value_from_datadict(self, data, files, name):
        return self.original_value


class ReadOnlyWidget(forms.Widget):
    """
    Renderiza um valor com a tag **<span>**.

    Note:
        Deve ser utilizado no ReadonlyForm ou ReadonlyModelForm)
    """

    def render(self, name, value, attrs=None, renderer=None):
        """
        Cria o código necessário para renderizar o **value**.

        Args:
            name (string): atributo name para o span;
            value (string): valor a ser apresentado;
            attrs (dict): dicionário com um conjunto de atributos;
            renderer (): .

        Returns:
            String com **HTML** **span**.
        """
        attrs['name'] = name
        final_attrs = self.build_attrs(attrs)
        if hasattr(self, 'display_value'):
            value = self.display_value
        return mark_safe(
            f'<input type="text" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false" {forms.utils.flatatt(final_attrs)} readonly value="{escape(value)}">'
        )
