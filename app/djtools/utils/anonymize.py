import hashlib
import inspect
import logging

from django.conf import settings
from django.template import VariableDoesNotExist
from django.template.base import Variable
from django.template.context import BaseContext
from django.utils.safestring import mark_safe

logger = logging.getLogger('django.template')


def anonymize(obj, params, request, html=False):
    """
    Anonimiza dados caso seja necessário.

    Args:
        obj (object): objeto base;
        params (string): nome do atributo separado por ponto.
        request (HttpRequest): requisição realizada por usuário, se tiver;

    Returns:
        (string|object): Atributo solicitado ou string anonimizada.
        bool: Atributo foi anonimizado
        string: Justificativa anonimização
    """
    return _anonymize(obj, obj, params, request, html)


def _anonymize(obj, current, params, request, html=False):
    """
    Anonimiza dados caso seja necessário.

    Args:
        obj (object): objeto base;
        current (object): objeto do contexto atual;
        params (string): nome do atributo separado por ponto.
        request (HttpRequest): requisição realizada por usuário, se tiver;
    Returns:
        (string|object): Atributo solicitado ou string anonimizada.
        bool: Atributo foi anonimizado
        string: Justificativa da anonimização
    """
    changed = False
    justification = ''
    if obj:
        try:
            if 'force_anonymize' in getattr(request, 'GET', {}) or 'force_anonymize' in getattr(request, 'POST', {}):
                justification = 'Este campo foi forçadamente anonimizado.'
            else:
                function = getattr(obj.Anonymize, 'can_view_data', 'can_view_data')
                can_view_data = getattr(obj, function)
                result, justification = can_view_data(request, params)
                if result:
                    return current, changed, justification
        except Exception as e:
            if settings.DEBUG:
                raise e
            return current, False, ''

        try:
            for field in obj.Anonymize.suppress:
                if field == params:
                    current = '-'
                    changed = True
        except Exception:
            pass

        try:
            for field in obj.Anonymize.cover:
                if field == params:
                    current = '*' * len(str(current))
                    changed = True
        except Exception:
            pass

        try:
            for field in obj.Anonymize.default_cover:
                if field == params:
                    current = '****'
                    changed = True
        except Exception:
            pass

        try:
            for field in obj.Anonymize.hash:
                if field == params:
                    current = hashlib.sha256(str(current).encode('UTF-8')).hexdigest()
                    changed = True
        except Exception:
            pass

        try:
            for field, hidden_func in obj.Anonymize.other.items():
                if field == params:
                    current = getattr(obj, hidden_func)()
                    changed = True
        except Exception:
            pass

        if changed and html and justification:
            current = str(current) + f' <span class="hint" aria-label="{justification}"><i class="fas fa-question-circle"></i></span>'
            current = mark_safe(current)
    return current, changed, justification


def _resolve_lookup(self, context):
    """
    Perform resolution of a real variable (i.e. not a literal) against the
    given context.

    As indicated by the method's name, this method is an implementation
    detail and shouldn't be called by external code. Use Variable.resolve()
    instead.
    """
    from comum.utils import tl

    current = context
    father = None
    children = []
    try:  # catch-all for silent variable failures
        for bit in self.lookups:
            try:  # dictionary lookup
                current = current[bit]
                # ValueError/IndexError are for numpy.array lookup on
                # numpy < 1.9 and 1.9+ respectively
            except TypeError, AttributeError, KeyError, ValueError, IndexError:
                try:  # attribute lookup
                    # Don't return class attributes if the class is the context:
                    if isinstance(current, BaseContext) and getattr(type(current), bit):
                        raise AttributeError
                    current = getattr(current, bit)
                except TypeError, AttributeError:
                    # Reraise if the exception was raised by a @property
                    if not isinstance(current, BaseContext) and bit in dir(current):
                        raise
                    try:  # list-index lookup
                        current = current[int(bit)]
                    except (
                        IndexError,  # list index out of range
                        ValueError,  # invalid literal for int()
                        KeyError,  # current is a dict without `int(bit)` key
                        TypeError,
                    ):  # unsubscriptable object
                        raise VariableDoesNotExist(
                            'Failed lookup for key [%s] in %r',
                            (bit, current),
                        )  # missing attribute
            if callable(current):
                if getattr(current, 'do_not_call_in_templates', False):
                    pass
                elif getattr(current, 'alters_data', False):
                    current = context.template.engine.string_if_invalid
                else:
                    try:  # method call (assuming no args required)
                        current = current()
                    except TypeError:
                        try:
                            signature = inspect.signature(current)
                        except ValueError:  # No signature found.
                            current = context.template.engine.string_if_invalid
                        else:
                            try:
                                signature.bind()
                            except TypeError:  # Arguments *were* required.
                                # Invalid method call.
                                current = context.template.engine.string_if_invalid
                            else:
                                raise
            children.append(bit)
            if not father and hasattr(current, 'Anonymize'):
                father = current
                children = []
    except Exception as e:
        template_name = getattr(context, 'template_name', None) or 'unknown'
        logger.debug(
            "Exception while resolving variable '%s' in template '%s'.",
            bit,
            template_name,
            exc_info=True,
        )

        if getattr(e, 'silent_variable_failure', False):
            current = context.template.engine.string_if_invalid
        else:
            raise

    current, _changed, _justify = _anonymize(father, current, '.'.join(children), tl.get_request(), html=True)

    return current


Variable._resolve_lookup = _resolve_lookup
