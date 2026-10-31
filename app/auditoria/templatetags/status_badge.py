from django import template
from auditoria.models import StatusAfastamento

register = template.Library()


@register.filter
def status_badge(status_value):
    try:
        status_value = int(status_value)
    except ValueError, TypeError:
        return ''

    label = StatusAfastamento(status_value).label
    color_classes = {
        StatusAfastamento.PENDENTE: 'badge warning',
        StatusAfastamento.HOMOLOGADO: 'badge success',
        StatusAfastamento.REJEITADO: 'badge danger',
    }
    css = color_classes.get(status_value, 'badge badge-secondary')

    return f'<span class="{css}">{label}</span>'
