from django.template import Library

from djtools import layout
from djtools.utils import get_session_cache, render_to_string

register = Library()


@register.simple_tag(takes_context=True)
def render_mensagens(context, messages, classe, id=''):
    """
    Renderiza o quadro de mensagens na index do SUAP.

    Args:
        context:
        messages (string): texto contendo a mensagem;
        classe (string): string com a classe **CSS**;
        id:

    Returns:
        String contendo o componente visual das mensagens.
    """
    if messages:
        return render_to_string(
            template_name='djtools/templates/components/messages.html',
            context={'messages': messages, 'classe': classe, 'id': id},
            request=context['request'],
        )
    return ''


@register.simple_tag(takes_context=True)
def render_quick_access(context, quick_access):
    """
    Renderiza o acesso rápido na index do SUAP.

    Args:
        context:
        quick_access ():

    Returns:
        String contendo o componente visual das mensagens.
    """
    timeout = 24 * 60 * 60
    request = context['request']

    def index_quick_access_sessao():
        retorno = []
        for _, data in layout.index_quick_access_data.send(sender=render_quick_access, request=request):
            retorno.extend(data)
        return retorno

    if request.user:
        quick_access = get_session_cache(request, 'index_quick_access_data', index_quick_access_sessao, timeout)
    else:
        quick_access = []
    return render_to_string(
        template_name='djtools/templates/components/quick_access.html', context={'quick_access': quick_access}, request=context['request']
    )


@register.simple_tag(takes_context=True)
def render_alert(context, titulo, icone, classe, objetos):
    """
    Renderiza os alertas na index do SUAP.

    Args:
        context:
        titulo:
        icone:
        classe:
        objetos:

    Returns:
        String contendo o componente visual das mensagens.
    """
    if objetos:
        return render_to_string(
            template_name='djtools/templates/components/alertas.html',
            context={'titulo': titulo, 'icone': icone, 'classe': classe, 'objetos': objetos},
            request=context['request'],
        )
    return ''
