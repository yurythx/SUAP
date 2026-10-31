import codecs
import pickle
from importlib import import_module

from django.conf import settings
from django.core.cache import cache
from django.utils.text import slugify

from .test import running_tests


def get_remote_session(key):
    return import_module(settings.SESSION_ENGINE).SessionStore(session_key=key)


def get_session_cache(request, key, func, timeout):
    """
    Obtem o resultado de uma função com base no cache, caso não tenha esteja em cache, o resultado é colocado em cache.

    Args:
        key (string): chave utilizada para indexar o resultado no cache;
        func (Function): função a ser invocada caso não esteja em cache seu resultado;
        timeoout (int): tempo máximo de vida para o cache.

    Returns:
        Resultado da função passada.
    """
    if running_tests() or not settings.USE_REDIS:
        return func()
    session_key = f'_cache_{request.user.username}_{key}'
    data = cache.get(session_key)
    if data:
        retorno = pickle.loads(codecs.decode(data.encode(), 'base64'))
        return retorno
    else:
        retorno = func()
        pickled = codecs.encode(pickle.dumps(retorno), 'base64').decode()
        cache.set(session_key, pickled, timeout)
        return retorno


def _chaves_dos_quadros(username: str) -> list[str]:
    """Chaves de cache dos quadros do index registrados, para o usuário.

    Mesma fonte (receivers de ``index_quadros_data``) e mesmo formato usados na leitura,
    em ``comum.views._carregar_caches_quadros``: uma chave só existe no cache se o seu
    receiver foi registrado, logo enumerar por aqui cobre tudo que é legível.
    """
    from djtools import layout

    return [f'_cache_{username}_quadro_{slugify(chave)}' for chave in layout.chaves_de_quadros_visiveis()]


def limpar_cache_dos_quadros(username: str) -> None:
    """Invalida o cache dos quadros do index do usuário, sem varrer o keyspace do Redis.

    Args:
        username (str): username do dono dos quadros.
    """
    if not settings.USE_REDIS:
        return
    cache.delete_many(_chaves_dos_quadros(username))


def limpar_cache_do_usuario(username: str) -> None:
    """Invalida o cache de sessão de longa duração do usuário: quadros do index e acesso rápido.

    As demais chaves gravadas por ``get_session_cache`` (``index_infos_data`` e as do ponto)
    têm TTL de 5 minutos e expiram sozinhas, por isso não são enumeradas.

    Args:
        username (str): username do dono do cache.
    """
    if not settings.USE_REDIS:
        return
    # ponytail: enumeração das chaves de TTL longo. Chave nova de TTL longo entra aqui;
    # se a lista crescer, trocar por um índice das chaves por usuário (SET no Redis).
    cache.delete_many([*_chaves_dos_quadros(username), f'_cache_{username}_index_quick_access_data'])


def get_cache(key, func, timeout):
    """
    Obtem o resultado de uma função com base no cache, caso não tenha esteja em cache, o resultado é colocado em cache.

    Args:
        key (string): chave utilizada para indexar o resultado no cache;
        func (Function): função a ser invocada caso não esteja em cache seu resultado;
        timeoout (int): tempo máximo de vida para o cache.

    Returns:
        Resultado da função passada.
    """
    if running_tests() or not settings.USE_REDIS:
        return func()
    key = '_cache_' + key
    data = cache.get(key)
    if data:
        retorno = pickle.loads(codecs.decode(data.encode(), 'base64'))
        return retorno
    else:
        retorno = func()
        pickled = codecs.encode(pickle.dumps(retorno), 'base64').decode()
        cache.set(key, pickled, timeout)
        return retorno
