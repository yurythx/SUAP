from datetime import datetime

import setproctitle
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from djtools.utils import ignore_request_for_tests

proctitle_prefix = getattr(settings, 'PROCTITLE_PREFIX', '[django]')


class ChangeProcessNameMiddleware(MiddlewareMixin):
    def _get_username_from_request(self, request):
        if not ignore_request_for_tests(request):
            if request.user:
                return hasattr(request, 'user') and request.user.id and request.user.username or 'anonymous'
            elif hasattr(request, 'auth') and request.auth and request.auth.application:
                return f'{request.auth.token or request.auth.application.client_id}' or request.auth.application.user.username
        return 'anonymous'

    def process_request(self, request):
        username = self._get_username_from_request(request)
        request.start_time = datetime.now()
        setproctitle.setproctitle(f'RUNNING {proctitle_prefix} {request.get_full_path()} (since {request.start_time}) USER: {username}')

    def process_response(self, request, response):
        username = self._get_username_from_request(request)
        if hasattr(request, 'start_time'):  # HttpResponseRedirect does not have `start_time` attr
            response_time = (datetime.now() - request.start_time).total_seconds()
        else:
            response_time = 0
        setproctitle.setproctitle(f'FINISHED {proctitle_prefix} {request.get_full_path()} (in {response_time}s) LAST USER: {username}')
        return response
