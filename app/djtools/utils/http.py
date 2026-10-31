from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, UnreadablePostError

__all__ = ['fake_request', 'get_client_ip', 'ids_da_query', 'is_ajax', 'upload_em_pdf']


def is_ajax(request):
    return (hasattr(request, 'headers') and request.headers.get('x-requested-with') == 'XMLHttpRequest') or (
        hasattr(request, 'META') and request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    )


class _StreamComPrefixo:
    """Leitor que devolve ``prefixo`` e depois o resto de ``resto``, sem carregar o corpo inteiro na memória."""

    def __init__(self, prefixo: bytes, resto: HttpRequest) -> None:
        self._prefixo = prefixo
        self._resto = resto

    def read(self, size: int = -1) -> bytes:
        """Lê até ``size`` bytes (todos, se negativo), consumindo primeiro o prefixo."""
        if not self._prefixo:
            return self._resto.read(size)
        if 0 <= size <= len(self._prefixo):
            lido, self._prefixo = self._prefixo[:size], self._prefixo[size:]
            return lido
        lido, self._prefixo = self._prefixo, b''
        return lido + self._resto.read(-1 if size < 0 else size - len(lido))


def upload_em_pdf(request: HttpRequest) -> tuple[_StreamComPrefixo | UploadedFile, bool, str] | None:
    """O arquivo enviado ao uploader ajax como ``(upload, is_raw, filename)``, se for PDF; senão ``None``.

    No ajax o arquivo vem cru no corpo e o nome na querystring; no form, é o único de ``request.FILES``. É PDF com a
    extensão ``.pdf`` e o conteúdo começando por ``%PDF-``: o ``AjaxFileUploadField`` só restringe a extensão no navegador.
    No ajax só os 5 bytes do cabeçalho são lidos aqui; o ``upload`` devolvido entrega-os de novo e segue com o resto do corpo.
    """
    if is_ajax(request):
        filename = request.GET.get('qqfile') or request.POST.get('qqfilename') or ''
        try:
            cabecalho = request.read(5)
        except UnreadablePostError:  # o navegador cancelou o envio no meio
            return None
        upload, is_raw = _StreamComPrefixo(cabecalho, request), True
    elif len(request.FILES) == 1:
        upload = request.FILES.getlist(next(iter(request.FILES)))[-1]
        filename, is_raw = upload.name or '', False
        cabecalho = upload.read(5)
        upload.seek(0)
    else:
        return None
    eh_pdf = filename.lower().endswith('.pdf') and cabecalho == b'%PDF-'
    return (upload, is_raw, filename) if eh_pdf else None


def get_client_ip(request):
    """
    Obtem o **IP** do cliente que realizou uma requisição.

    Args:
        request (HttpREquest): objeto request.

    Returns:
        String com o IP do cliente.
    """
    for attr in settings.CLIENT_IP_HEADERS:
        if request.META.get(attr):
            return request.META.get(attr)


def fake_request(user):
    port = 443 if settings.SITE_URL.startswith('https') else 80
    servername = settings.SITE_URL.split('//')[1]
    if ':' in servername:
        servername, port = servername.split(':')
        port = int(port)
    request = HttpRequest()
    request.META['SERVER_NAME'] = servername
    request.META['SERVER_PORT'] = port
    request.user = user
    request.session = {}
    return request


def ids_da_query(fonte: HttpRequest | str | None, sep: str = ',') -> list[int]:
    """Lê uma lista de pks no formato ``1,2,3`` descartando pedaços vazios e não numéricos.

    Args:
        fonte: a requisição (lê ``request.GET['ids']``) ou a própria string (ex. guardada na sessão).
        sep: separador entre os pks.

    Returns:
        Os pks válidos. Sem o parâmetro, com ``ids=`` ou só com lixo, devolve lista vazia — o
        ``filter(pk__in=[])`` não casa nada, em vez de estourar ``AttributeError``/``ValueError`` (#17406, #17447).
    """
    valor = fonte.GET.get('ids', '') if isinstance(fonte, HttpRequest) else fonte or ''
    return [int(pedaco) for pedaco in valor.split(sep) if pedaco.strip().isdecimal()]
