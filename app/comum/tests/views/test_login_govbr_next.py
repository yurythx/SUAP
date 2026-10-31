"""Regressão do encaminhamento do `next` para o login Gov.BR (chamado do AVA).

O botão "Entrar com Gov.BR" monta a URL de login a partir de `request.GET.next`, que o
Django já entrega decodificado. Sem `|urlencode`, os `&` do `next` passam a separar
parâmetros do próprio `/accounts/login/`, truncando o destino em `/o/authorize/?response_type=code`
e fazendo o django-oauth-toolkit responder "Missing client_id parameter".
"""

import html
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.template import Context, Template
from django.test import RequestFactory

AUTHORIZE_URL = (
    '/o/authorize/?response_type=code&client_id=4oQ3egl1jhGTB0Yt7WPyxc5pzXWsV1sC0rlpmqz2&redirect_uri=https://ava.ifrn.edu.br/authenticate/'
)


def _linha_do_botao_govbr() -> str:
    conteudo = Path(settings.BASE_DIR, 'comum', 'templates', 'login.html').read_text(encoding='utf-8')
    linha = next(linha for linha in conteudo.splitlines() if 'login-govbr' in linha)
    return re.sub(r'\s*class="btn default login-govbr">$', '></a>', linha.strip())


def test_botao_govbr_preserva_o_next_inteiro():
    """O `next` renderizado no botão Gov.BR deve chegar íntegro ao servidor."""
    request = RequestFactory().get('/accounts/login/', {'next': AUTHORIZE_URL})

    href_renderizado = Template(_linha_do_botao_govbr()).render(Context({'request': request}))

    # O navegador desfaz as entidades HTML do autoescape antes de enviar a requisição.
    url_clicada = html.unescape(re.search(r'href="([^"]+)"', href_renderizado).group(1))
    parametros = parse_qs(urlsplit(url_clicada).query, keep_blank_values=True)

    assert parametros['next'] == [AUTHORIZE_URL]
    assert 'client_id' not in parametros, 'o client_id vazou do next para a query do /accounts/login/'
