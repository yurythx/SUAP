from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class LocaleMiddlewarePlus(LocaleMiddleware):
    def process_request(self, request):
        if request.path.startswith('/eventos/inscricao/'):
            super().process_request(request)
        else:
            translation.activate(settings.LANGUAGE_CODE)
            request.LANGUAGE_CODE = translation.get_language()
