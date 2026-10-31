import datetime

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect


class SessionLock:
    """
    Evita duplo clique de usuários em formulários com csrf
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.session_locked = getattr(settings, 'SESSION_LOCK', False)

    def __call__(self, request):
        if not self.session_locked or request.method == 'GET':
            return self.get_response(request)
        self.process_request(request)
        return self.process_response(request)

    def process_request(self, request):
        request.ignore = False
        for key in request.POST:
            if 'current_step' in key:
                return  # ignorando caso seja um Wizard.
        if request.POST.get('csrfmiddlewaretoken', None) and request.user.is_authenticated:
            now = datetime.datetime.now()
            last_csrf_post = request.session.get('_last_csrf_post', None)
            if last_csrf_post and not isinstance(last_csrf_post, datetime.datetime):
                last_csrf_post = datetime.datetime.fromisoformat(last_csrf_post)
            last_path = request.session.get('_last_url_path', None)
            if last_csrf_post and last_path and last_path == request.path and now - last_csrf_post < datetime.timedelta(seconds=1):
                request.ignore = True
            request.session['_last_csrf_post'] = now.isoformat()
            request.session['_last_url_path'] = request.path

    def process_response(self, request):
        if request.ignore:
            messages.error(
                request,
                'Atenção: clicar mais de uma vez no botão acarretará problemas de perfomance no SUAP, assim como o registro duplicado de informações.',
            )
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
        return self.get_response(request)
