from functools import wraps
from typing import Any

from django.core.exceptions import SuspiciousOperation
from django.http import HttpRequest
from ninja.errors import HttpError
from ninja.security import HttpBearer
from ninja.security import SessionAuth as NinjaSessionAuth
from ninja_jwt.authentication import JWTAuth as NinjaJWTAuth
from ninja_jwt.exceptions import InvalidToken
from oauth2_provider.oauth2_backends import get_oauthlib_core

from djtools.middleware import threadlocals as tl


class SessionAuth(NinjaSessionAuth):
    """
    Classe de autenticação de sessão personalizada.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> Any | None:
        """
        Autentica o usuário com base na sessão.

        Args:
            request: Objeto de requisição HTTP.
            key: Chave de autenticação opcional.

        Returns:
            Optional[Any]: Usuário autenticado ou None.
        """
        if request.user and request.user.is_authenticated:
            return request.user

        return None


class JWTAuth(NinjaJWTAuth):
    """
    Classe de autenticação JWT personalizada.
    """

    def authenticate(self, request: HttpRequest, token: str) -> Any:
        """
        Autentica o usuário com base no token JWT.

        Args:
            request: Objeto de requisição HTTP.
            token: Token JWT.

        Returns:
            Any: Usuário autenticado ou None.
        """
        try:
            tl.context.request = request
            tl.context.user = request.user
            return self.jwt_authenticate(request, token)
        except InvalidToken:
            return None


class OAuth2TokenAuth(HttpBearer):
    """
    Classe de autenticação baseada em token OAuth2.
    """

    from comum.models import User

    param_name: str = 'auth-token'

    def authenticate(self, request: HttpRequest, key: str | None) -> User | None:
        """
        Autentica o usuário com base no token OAuth2.

        Args:
            request: Objeto de requisição HTTP.
            key: Chave do token.

        Returns:
            Optional[User]: Usuário autenticado ou None.
        """
        if request is None:
            return None
        oauthlib_core = get_oauthlib_core()
        try:
            valid, r = oauthlib_core.verify_request(request, scopes=[])
        except ValueError as error:
            if str(error) == 'Invalid hex encoding in query string.':
                raise SuspiciousOperation(error)
            raise
        else:
            if valid:
                request.application = r.client  # apenas oauth tem este atributo
                request.user = r.user or (r.client and r.client.user) or None
                if not request.user:
                    return None
                tl.context.request = request
                tl.context.user = request.user
                return r.access_token
        request.oauth2_error = getattr(r, 'oauth2_error', {})
        return None


class TrustedAppAuth(HttpBearer):
    """
    Classe de autenticação para aplicativos confiáveis.
    """

    from comum.models import User

    param_name: str = 'app-token'

    def authenticate(self, request: HttpRequest, key: str | None) -> User | None:
        """
        Autentica o usuário com base no token de aplicativo confiável.

        Args:
            request: Objeto de requisição HTTP.
            key: Chave do token.

        Returns:
            Optional[User]: Usuário autenticado ou None.
        """
        if request is None:
            return None
        oauthlib_core = get_oauthlib_core()
        try:
            valid, r = oauthlib_core.verify_request(request, scopes=[])
        except ValueError as error:
            if str(error) == 'Invalid hex encoding in query string.':
                raise SuspiciousOperation(error)
            raise
        else:
            if valid:
                request.application = r.client  # apenas oauth tem este atributo
                request.user = r.client and r.client.skip_authorization and r.client.user or None
                if not request.user:
                    return None
                tl.context.request = request
                tl.context.user = request.user
                return r.client and r.client.skip_authorization and r.access_token
        request.oauth2_error = getattr(r, 'oauth2_error', {})
        return None


def permission_required(perm):
    """
    Decorator for views that checks whether a user has a particular permission enabled.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.has_perm(perm):
                raise HttpError(403, 'Permission denied')
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def require_scopes(scopes: list[str]):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Lógica para verificar se request.auth.allow_scopes(scopes) é verdadeiro
            # Se não for, levanta uma exceção de autenticação
            if not request.auth or not hasattr(request.auth, 'allow_scopes') or not request.auth.allow_scopes(scopes):
                raise HttpError(401, 'Permissão de escopo insuficiente.')
            return func(request, *args, **kwargs)

        return wrapper

    return decorator
