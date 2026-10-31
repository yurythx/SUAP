from collections.abc import Callable

from django.http import Http404, HttpRequest, HttpResponse

from djtools.modulos_ocultos import caminho_oculto, ocultar_no_admin


class ModulosOcultosMiddleware:
    """Responde 404 nas URLs acadêmicas quando DISABLE_EDU está ligado."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        ocultar_no_admin()
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if caminho_oculto(request.path):
            raise Http404
        return self.get_response(request)
