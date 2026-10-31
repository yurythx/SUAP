from django import template

register = template.Library()


@register.filter(name='is_ajax')
def ajax(request):
    from djtools.utils import is_ajax

    return is_ajax(request)
