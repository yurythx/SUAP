from django.forms.widgets import SelectMultiple
from django.utils.safestring import mark_safe

from djtools.utils import render_to_string


class BaseConhecimentoSelectMultiple(SelectMultiple):
    def __init__(self, request, *args, **kwargs):
        assert request is not None
        self.request = request
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        ctx = self.get_context(name, value, attrs)
        choices = [[base_conhecimento, f'{base_conhecimento.id}' in (value or [])] for base_conhecimento in self.choices.queryset]
        ctx.update(
            {
                'request': self.request,
                'choices': choices,
            }
        )
        output = render_to_string('widgets/base_conhecimento_select.html', ctx)
        return mark_safe(output)


class ChamadoSelectMultiple(SelectMultiple):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        ctx = self.get_context(name, value, attrs)
        choices = [[chamado, f'{chamado.id}' in (value or [])] for chamado in self.choices.queryset]
        ctx.update(
            {
                'choices': choices,
            }
        )
        output = render_to_string('widgets/chamado_select.html', ctx)
        return mark_safe(output)
