from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin

from djtools.utils import get_remote_session


class UserRestrict(MiddlewareMixin):
    def process_request(self, request):
        """
        Checks if different session exists for user and deletes it.
        """
        if request.user.is_authenticated:
            cache_timeout = 86400
            cache_key = f'user_pk_{request.user.pk}_restrict'
            cache_value = cache.get(cache_key)

            if cache_value is not None:
                if request.session.session_key != cache_value:
                    get_remote_session(cache_value).delete()
                    cache.set(cache_key, request.session.session_key, cache_timeout)
            else:
                cache.set(cache_key, request.session.session_key, cache_timeout)
