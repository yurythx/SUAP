from django import forms
from django.utils.encoding import force_str
from django.utils.safestring import mark_safe


class SubmitButton(forms.Widget):
    """
    A widget that handles a submit button.
    """

    def __init__(self, name, value, label, attrs):
        self.name, self.value, self.label = name, value, label
        self.attrs = attrs

    def __str__(self):
        final_attrs = self.build_attrs(self.attrs, type='submit', name=self.name, value=self.value)
        return mark_safe(f'<button{forms.widgets.flatatt(final_attrs)}>{self.label}</button>')


class MultipleSubmitButton(forms.Select):
    """
    A widget that handles a list of submit buttons.
    """

    def __init__(self, attrs=None, choices=()):
        if not attrs:
            attrs = {'class': 'btn default'}
        self.attrs = attrs
        self.choices = choices

    def __iter__(self):
        for value, label in self.choices:
            yield SubmitButton(self.name, value, label, self.attrs.copy())

    def __str__(self):
        return '<button type="submit" />'

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        """Outputs a <ul> for this set of submit buttons."""
        self.name = name
        return mark_safe(f'<ul>\n{"\n".join([f"<li>{force_str(w)}</li>" for w in self])}\n</ul>')

    def value_from_datadict(self, data, files, name):
        """
        returns the value of the widget: IE posts inner HTML of the button
        instead of the value.
        """
        value = data.get(name, None)
        if value in dict(self.choices):
            return value
        else:
            inside_out_choices = {v: k for (k, v) in self.choices}
            if value in inside_out_choices:
                return inside_out_choices[value]
        return None
