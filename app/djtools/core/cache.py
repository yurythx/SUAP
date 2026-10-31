import logging
import threading
import time

from django.core.cache.backends.locmem import LocMemCache
from django_redis.cache import RedisCache

# Configura o logger
logger = logging.getLogger(__name__)


class CustomRedisCache(RedisCache):
    _local_cache_store = {}
    _local_cache_lock = threading.Lock()

    def get(self, key, default=None, version=None, client=None, local_ttl=None):
        """
        Função de 'get' modificada que checa um cache local em memória primeiro.
        """

        # === Lógica de Cache Local (Se local_ttl for fornecido) ===
        if local_ttl is not None:
            with self._local_cache_lock:
                cache_hit, expiration_time = self._local_cache_store.get(key, (None, 0))
            current_time = time.time()

            # 1. Verificação de Cache Local
            if cache_hit is not None and expiration_time > current_time:
                # Acerto! Retorna o valor do cache local.
                logger.debug(f'Cache Local HIT para chave: {key}')
                return cache_hit

            # 2. Miss (Erro) no Cache Local ou Expirado
            logger.debug(f'Cache Local MISS ou Expirado para chave: {key}')

        # === Consulta ao Cache Original Remoto (ou cache padrão) ===
        # Chama a função 'get' original do Django (que consulta o Redis/Memcached, etc.)
        value = super().get(key, default=default, version=version, client=client)

        # === Armazenamento no Cache Local (Se local_ttl for fornecido) ===
        if local_ttl is not None:
            if value is not None:
                new_expiration_time = time.time() + local_ttl
                with self._local_cache_lock:
                    self._local_cache_store[key] = (value, new_expiration_time)
                logger.debug(f'Cache Local Armazenado com TTL de {local_ttl}s para chave: {key}')
            elif key in self._local_cache_store:
                with self._local_cache_lock:
                    del self._local_cache_store[key]
        return value

    def clear_local_cache(self):
        with self._local_cache_lock:
            self._local_cache_store.clear()

    def _invalidate_local_cache_key(self, key):
        with self._local_cache_lock:
            if key in self._local_cache_store:
                del self._local_cache_store[key]
                logger.debug(f'Cache Local Deletado para chave: {key}')

    def delete(self, key, version=None, client=None):
        self._invalidate_local_cache_key(key)
        return super().delete(key, version=version, client=client)

    def set(self, key, value, timeout=None, version=None, client=None):
        self._invalidate_local_cache_key(key)
        return super().set(key, value, timeout=timeout, version=version, client=client)


class CustomLocMemCache(LocMemCache):
    def get(self, key, default=None, version=None, client=None, local_ttl=None):
        return super().get(key, default=default, version=version)
