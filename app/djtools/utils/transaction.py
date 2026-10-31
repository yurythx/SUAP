import warnings
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .test import running_tests


@contextmanager
def atomic(key: str = '', timeout: float | None = None):
    """
    Gerencia um bloco de código dentro de uma transação atômica e um bloqueio de cache opcional.
    Obs: Para que o bloqueio de cache opcional funcione, além de informar "key", o Redis tem que estar sendo utilizado
    como gestor de cache do Django. Caso o Redis não esteja sendo utilizado, ambiente de desenvolvimento apenas um alerta
    será exibido e a transação realizada sem bloqueio de cache, já em ambiente de produção, como
    o Redis é obrigatório, será lançado uma exceção.

    Args:
        key (str): A chave para o bloqueio de cache. Se vazio, o bloqueio não será utilizado.
        timeout (Optional[float]): O tempo limite para o bloqueio de cache.

    Yields:
        tuple: Um tupla contendo o bloqueio de cache (ou None) e a transação atômica.
    """
    if key:
        if hasattr(cache, 'lock'):
            with cache.lock(key, timeout=timeout) as a, transaction.atomic() as b:
                yield (a, b)
        else:
            if settings.DEBUG or running_tests():
                warnings.warn('\033[93mWARNING: Lock do Redis não está disponível. Usando atomic sem cache lock.\033[0m', stacklevel=2)
                with transaction.atomic() as b:
                    yield (None, b)
            else:
                raise Exception('Lock do Redis não está disponível. Seu uso é obrigatorio em ambiente de produção.')
    else:
        with transaction.atomic() as b:
            yield (None, b)
