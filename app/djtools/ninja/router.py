from collections.abc import Callable
from functools import wraps
from typing import get_origin

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.text import slugify
from ninja import Router
from ninja.pagination import paginate

from djtools.ninja.auth import JWTAuth, OAuth2TokenAuth, SessionAuth
from djtools.ninja.pagination import Pagination
from djtools.ninja.schema import ErrorSchema
from djtools.utils import send_mail

deprecated_router = Router(tags=['Depreciados'])

data_depreciacao = '01/01/2026'

DEFAULT_AUTH = (
    JWTAuth(),
    OAuth2TokenAuth(),
    SessionAuth(),
)

SUCCESS_CODE = 200
ERROR_CODES = frozenset({401, 403, 404})


def get_email(user):
    if user.email:
        return user.email

    vinculo = user.get_vinculo()
    if vinculo and vinculo.email_notificacao:
        return vinculo.email_notificacao
    if vinculo and vinculo.email_pessoal:
        return vinculo.email_pessoal
    return None


def send_deprecation_email(request: HttpRequest, router: Router, path: str | None) -> None:
    """
    Envia um e-mail de notificação para o usuário sobre a depreciação do endpoint.
    """
    if not hasattr(request, 'application') or not hasattr(request.application, 'user') or not request.application.user.is_authenticated:
        # Não envia e-mail se o usuário não estiver autenticado (ou sem atributo user)
        return

    email = get_email(request.application.user)
    if not email:
        # Não envia e-mail se o usuário não tiver um e-mail válido
        return

    # 💌 Monta a mensagem
    subject = f'Aviso de Depreciação de Endpoint: {request.path}'
    depreciation_cache_key = f'deprecation_email_sent_{request.application.id}_{slugify(path)}'
    if cache.get(depreciation_cache_key):
        # Já enviou o e-mail recentemente
        return

    if path:
        # Se 'path' existe, o endpoint principal é conhecido
        novo_endpoint = f'/api/{router.api_url_prefix}/{path}'
        message = (
            f'Olá {request.application.user or ""},\n\n'
            f'Sua aplicação "{request.application}" acessou o endpoint depreciado <b>{settings.SITE_URL}{request.path}</b>.\n'
            f'Este endpoint será removido em <b>{data_depreciacao}</b>.\n\n'
            f'Por favor, atualize seu código para usar o novo endpoint:\n'
            f'<b>{settings.SITE_URL}{novo_endpoint}</b>'
        )
    else:
        # Se 'path' é None, é uma remoção sem substituição direta de rota
        message = (
            f'Olá {request.application.user or ""},\n\n'
            f'Sua aplicação "{request.application}" acessou o endpoint depreciado <b>{settings.SITE_URL}{request.path}</b>.\n'
            f'Este endpoint será removido em <b>{data_depreciacao}</b> e não será substituído.'
        )

    # 📤 Envia o e-mail
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,  # Remetente padrão
            [email],  # Destinatário
            fail_silently=True,
        )
        cache.set(depreciation_cache_key, True, 3600 * 24)  # Evita reenvio por 24 horas
    except Exception:
        pass


def generate_kwargs(
    kwargs: dict,
) -> dict:
    """
    Gera os argumentos para os endpoints.
    """
    auth_param = kwargs.get('auth')
    response_param = kwargs.get('response')
    if not isinstance(response_param, dict):
        kwargs['response'] = {SUCCESS_CODE: response_param, ERROR_CODES: ErrorSchema}
    if auth_param is None:
        kwargs['auth'] = DEFAULT_AUTH
    elif isinstance(auth_param, bool):
        kwargs['auth'] = DEFAULT_AUTH if auth_param else None
    return kwargs


def check_response_type(kwargs: dict) -> bool:
    """
    Verifica se a paginação deve ser aplicada com base nos argumentos fornecidos.
    """
    response_type = kwargs.get('response')
    for response in response_type.values():
        origin = get_origin(response)
        if origin is list:
            return True
    return False


def generate_deprecated_kwargs(
    kwargs: dict,
    router: Router,
    path: str | None,
) -> dict:
    """
    Gera os argumentos para os endpoints depreciados.
    """

    kwargs['deprecated'] = True
    if not path:
        kwargs['summary'] = f'Este endpoint será removido em {data_depreciacao}.'
    else:
        kwargs['summary'] = f'Este endpoint será movido para /api/{router.api_url_prefix}/{path} em {data_depreciacao}.'
    kwargs['tags'] = router.tags
    return kwargs


def _create_method_decorator(method_name: str) -> Callable:
    """
    Uma fábrica que cria um decorator para um método HTTP específico.
    """

    def decorator_wrapper(
        router: Router,
        path: str | None = None,
        deprecated_paths: list[str] | None = None,
        ignore_paginate: bool = False,
        *args,
        **options,
    ):
        def decorator(view_func: Callable) -> Callable:
            kwargs = generate_kwargs(options)
            should_paginate = check_response_type(kwargs)
            if should_paginate and not ignore_paginate:
                view_func = paginate(Pagination)(view_func)

            @wraps(view_func)
            def notify_and_call_view(request, *view_args, **view_kwargs):
                # Envia o e-mail de notificação ANTES da view ser executada
                send_deprecation_email(request, router, path)
                # Chama a view, que pode ser a view original ou a view paginada
                return view_func(request, *view_args, **view_kwargs)

            # Pega o método correspondente do router (ex: router.get, router.post)
            router_method = getattr(router, method_name)
            deprecated_router_method = getattr(deprecated_router, method_name)

            # Registra o endpoint principal, se houver
            if path is not None:
                router_method(path, *args, **kwargs)(view_func)

            # Registra os endpoints depreciados
            if deprecated_paths:
                # Usar .copy() evita modificar os kwargs do endpoint principal
                deprecated_kwargs = generate_deprecated_kwargs(kwargs.copy(), router, path)
                for dpath in deprecated_paths:
                    deprecated_router_method(
                        dpath,
                        *args,
                        **deprecated_kwargs,
                    )(notify_and_call_view)

            # Retorna a função original (ou paginada) para que a lógica não
            # seja aplicada duas vezes se a view for usada em outro lugar.
            return view_func

        return decorator

    return decorator_wrapper


get = _create_method_decorator('get')
post = _create_method_decorator('post')
put = _create_method_decorator('put')
delete = _create_method_decorator('delete')
patch = _create_method_decorator('patch')
