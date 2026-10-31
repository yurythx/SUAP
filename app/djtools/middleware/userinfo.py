from django.utils.deprecation import MiddlewareMixin


class UserInfoMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if hasattr(request, 'user') and request.user and request.user.is_authenticated:
            request.META['USER_USERNAME'] = str(request.user.username)
            request.META['USER_EMAIL'] = str(request.user.email)

        if hasattr(request, 'auth') and hasattr(request.auth, 'application'):
            request.META['USER_ACCESS_TOKEN'] = str(request.auth.token)
            request.META['USER_APPLICATION_CLIENT_API'] = str(request.auth.application.client_id)
            if hasattr(request.auth.application, 'user'):
                request.META['USER_APPLICATION_OWNER'] = str(request.auth.application.user.username)
            else:
                request.META['USER_APPLICATION_OWNER'] = ''

        # Tenta mascarar senhas
        if request.method == 'POST':
            keys = list(request.POST.keys())
            key_senhas = [k for k in keys if 'senha' in k or 'password' in k]
            request.POST._mutable = True
            for key_senha in key_senhas:
                request.POST[key_senha] = '*****'

    def process_response(self, request, response):
        if request.user:
            response['user'] = hasattr(request, 'user') and request.user.id and request.user.username or 'anonymous'
        if hasattr(request, 'auth') and hasattr(request.auth, 'application'):
            response['user'] = request.auth.token
            response['application'] = request.auth.application.client_id
            if request.auth.application.user:
                response['application_owner'] = request.auth.application.user.username
            else:
                response['application_owner'] = ''
        return response
