"""
In settings.py, MIDDLEWARE_CLASSES:
'<project_name>.djtools.middleware.threadlocals.ThreadLocals'

To import:
from <project_name>.djtools.middelware import threadlocals as tl
"""

from threading import local
from urllib.parse import urlparse

from django.utils.deprecation import MiddlewareMixin

from djtools.utils.http import get_client_ip

context = local()


def get_request():
    return getattr(context, 'request', None)


def get_app_context():
    app = ''

    try:
        request = getattr(context, 'request', None)
        url_origem = request.META.get('HTTP_REFERER', '')
        path = urlparse(url_origem).path
        if '/' in path:
            app = path.split('/')[1]
    except Exception:
        pass
    return app


def get_user():
    return getattr(context, 'user', None)


def get_profile():
    try:
        return get_user().get_profile()
    except Exception:
        return None


def get_vinculo():
    try:
        return get_user().get_vinculo()
    except Exception:
        return None


def get_remote_addr():
    request = get_request()
    if request:
        return get_client_ip(request)
    return None


def get_ano_letivo():
    return getattr(context, 'ano_letivo', None)


def set_ano_letivo(ano_letivo):
    context.ano_letivo = ano_letivo


class ThreadLocals(MiddlewareMixin):
    def process_request(self, request):
        context.user = getattr(request, 'user', None)
        context.request = request
