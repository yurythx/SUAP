import logging
import time

import requests as original_requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def create_session(
    max_retries=settings.REQUESTS_MAX_RETRIES, backoff_factor=settings.REQUESTS_BACKOFF_FACTOR, status_forcelist=settings.REQUESTS_STATUS_FORCELIST
):
    """
    Cria um objeto de sessão do requests configurado com:
    1. Uma estratégia de repetição (retry).
    2. Um timeout padrão para todas as requisições.

    Args:
        max_retries (int): O número total de tentativas de repetição para requisições falhas.
        backoff_factor (float): Um fator para calcular o tempo de espera entre as tentativas de repetição.
        status_forcelist (tuple): Um conjunto de códigos de status HTTP que devem acionar uma nova tentativa.
    """
    session = original_requests.Session()

    # Define a estratégia de repetição
    retry_strategy = Retry(total=max_retries, status_forcelist=status_forcelist, backoff_factor=backoff_factor)

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    return session


def _request(method, *args, **kwargs):
    """Função auxiliar para executar requisições HTTP."""
    max_retries = kwargs.pop('max_retries', settings.REQUESTS_MAX_RETRIES)
    status_forcelist = kwargs.pop('status_forcelist', settings.REQUESTS_STATUS_FORCELIST)
    backoff_factor = kwargs.pop('backoff_factor', settings.REQUESTS_BACKOFF_FACTOR)
    session = create_session(max_retries=max_retries, status_forcelist=status_forcelist, backoff_factor=backoff_factor)
    kwargs.setdefault('timeout', settings.REQUESTS_TIMEOUT)
    verbosity = kwargs.pop('verbosity', False)
    api = kwargs.pop('API', 'Unknown API')
    start_time = time.perf_counter()
    if verbosity:
        logger.info(f'API {api} Request: {method.upper()}\nARGS:{args}\nKWARGS: {kwargs}')
    response = getattr(session, method)(*args, **kwargs)
    end_time = time.perf_counter()
    if verbosity:
        logger.info(
            f'API {api} Response Status: {response.status_code}\nResponse Body: {response.text}\nDuration: {end_time - start_time:.2f} seconds\n\n'
        )
    return response


def connect(*args, **kwargs):
    return _request('connect', *args, **kwargs)


def delete(*args, **kwargs):
    return _request('delete', *args, **kwargs)


def get(*args, **kwargs):
    return _request('get', *args, **kwargs)


def head(*args, **kwargs):
    return _request('head', *args, **kwargs)


def options(*args, **kwargs):
    return _request('options', *args, **kwargs)


def patch(*args, **kwargs):
    return _request('patch', *args, **kwargs)


def post(*args, **kwargs):
    return _request('post', *args, **kwargs)


def put(*args, **kwargs):
    return _request('put', *args, **kwargs)


def trace(*args, **kwargs):
    return _request('trace', *args, **kwargs)
