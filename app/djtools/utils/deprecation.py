"""
Classic deprecation warning
===========================
Classic ``@deprecated`` decorator to deprecate old python classes, functions or methods.
.. _The Warnings Filter: https://docs.python.org/3/library/warnings.html#the-warnings-filter
"""

import datetime
import functools
import inspect
import warnings

import wrapt

# Adicionado 'expire_date' para refletir o novo requisito de argumento
__all__ = ['deprecated', 'unused']


def unused(func_or_class):
    # ... (código do decorador unused)
    """
    Decorador de marcação para sinalizar que uma função ou classe
    não deve mais ser utilizada.

    Esta é apenas uma marcação estática e não interfere no comportamento
    ou emite avisos (warnings) em tempo de execução.
    """
    # Retorna o objeto (função ou classe) sem alteração.
    return func_or_class


class ClassicAdapter(wrapt.AdapterFactory):
    def __init__(self, reason='', version='', action='always', category=DeprecationWarning, expire_date=''):
        """
        Construct a wrapper adapter.
        ...
        """
        self.reason = reason or ''
        self.version = version or ''
        self.action = action
        self.category = category
        self.expire_date = expire_date
        super().__init__()

    def get_deprecated_msg(self, wrapped, instance):
        """
        Get the deprecation warning message for the user.
        ...
        """
        if instance is None:
            if inspect.isclass(wrapped):
                fmt = 'Call to deprecated class {name}.'
            else:
                fmt = 'Call to deprecated function (or staticmethod) {name}.'
        else:
            if inspect.isclass(instance):
                fmt = 'Call to deprecated class method {name}.'
            else:
                fmt = 'Call to deprecated method {name}.'

        if self.reason:
            fmt += ' ({reason})'
        if self.version:
            fmt += ' -- Deprecated since version {version}.'
        if self.expire_date:
            fmt += ' **Remove after: {expire_date}**.'

        return fmt.format(name=wrapped.__name__, reason=self.reason or '', version=self.version or '', expire_date=self.expire_date or '')

    def __call__(self, wrapped):
        if inspect.isclass(wrapped):
            old_new1 = wrapped.__new__

            def wrapped_cls(cls, *args, **kwargs):
                msg = self.get_deprecated_msg(wrapped, None)
                if self.action:
                    with warnings.catch_warnings():
                        warnings.simplefilter(self.action, self.category)
                        warnings.warn(msg, category=self.category, stacklevel=3)
                else:
                    warnings.warn(msg, category=self.category, stacklevel=3)
                if old_new1 is object.__new__:
                    return old_new1(cls)
                return old_new1(cls, *args, **kwargs)

            wrapped.__new__ = staticmethod(wrapped_cls)

        return wrapped


def deprecated(*args, **kwargs):
    if args and isinstance(args[0], str):
        kwargs['reason'] = args[0]
        args = args[1:]

    reason = kwargs.get('reason')
    expire_date = kwargs.get('expire_date')

    if not reason:
        raise TypeError("O decorador @deprecated requer o argumento de palavra-chave 'reason' (razão para descontinuação).")

    if not expire_date or not isinstance(expire_date, str):
        raise TypeError("O decorador @deprecated requer o argumento de palavra-chave 'expire_date' (data de remoção, formato YYYY-MM-DD).")

    if args and not callable(args[0]):
        raise TypeError(repr(type(args[0])))

    if args:
        action = kwargs.get('action', 'always')
        category = kwargs.get('category', DeprecationWarning)

        adapter_cls = kwargs.pop('adapter_cls', ClassicAdapter)
        adapter = adapter_cls(**kwargs)

        wrapped = args[0]

        try:
            # Convertendo a string YYYY-MM-DD em objeto date para comparação
            date_to_remove = datetime.datetime.strptime(expire_date, '%Y-%m-%d').date()
            today = datetime.date.today()
            if today > date_to_remove:
                log_msg = f"CRITICO: '{wrapped.__qualname__}' deveria ter sido removida em {expire_date}. Razão: {reason or 'Não fornecida'}."
                warnings.warn(log_msg, stacklevel=2)
        except ValueError:
            # Lidar com formato de data inválido, se necessário
            warnings.warn(f'Formato de expire_date inválido para {wrapped.__qualname__}: {expire_date}', stacklevel=2)

        if inspect.isclass(wrapped):
            wrapped = adapter(wrapped)
            return wrapped

        elif inspect.isroutine(wrapped):

            @wrapt.decorator(adapter=adapter)
            def wrapper_function(wrapped_, instance_, args_, kwargs_):
                msg = adapter.get_deprecated_msg(wrapped_, instance_)
                if action:
                    with warnings.catch_warnings():
                        warnings.simplefilter(action, category)
                        warnings.warn(msg, category=category, stacklevel=3)
                else:
                    warnings.warn(msg, category=category, stacklevel=3)
                return wrapped_(*args_, **kwargs_)

            return wrapper_function(wrapped)

        else:
            raise TypeError(repr(type(wrapped)))

    return functools.partial(deprecated, **kwargs)
