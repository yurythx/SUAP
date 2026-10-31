from importlib import import_module

from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from django.template import TemplateDoesNotExist, loader
from django.views.defaults import ERROR_PAGE_TEMPLATE

from comum.exceptions import BusinessRuleFailure
from djtools import layout
from djtools.utils import HttpResponseConflict


class HttpResponseConflictMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        template_name = 'comum/templates/409.html'

        if not isinstance(exception, BusinessRuleFailure):
            return None

        try:
            # Handle import error but allow any type error from view
            callback = import_module(settings.ROOT_URLCONF).handler409
            return callback(request, exception)
        except ImportError, AttributeError:
            try:
                template = loader.get_template(template_name)
            except TemplateDoesNotExist:
                if template_name != 'comum/templates/409.html':
                    # Reraise if it's a missing custom template.
                    raise Http404
                return HttpResponseForbidden(
                    ERROR_PAGE_TEMPLATE % {'title': '403 Forbidden', 'details': ''},
                    content_type='text/html',
                )

            context = {'exception': str(exception), 'servicos_anonimos': layout.gerar_servicos_anonimos(request)}
            return HttpResponseConflict(template.render(request=request, context=context))
