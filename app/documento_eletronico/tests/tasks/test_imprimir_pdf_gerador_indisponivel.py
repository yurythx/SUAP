"""Tasks ``imprimir_pdf``/``imprimir_pdfa`` com o gerador de PDF (``/wkhtml_to_pdf`` do ``caminho_libreoffice``) fora do ar.

Só a fronteira HTTP é simulada (``requests.Session.post``). Timeout, queda de conexão e resposta 500 do gerador devem
encerrar a tarefa com mensagem ao usuário, e não escapar como erro não tratado do worker.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from unittest import mock

import pytest
import requests
from django.test import RequestFactory

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from djtools.models import Task
from documento_eletronico import tasks
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _static_root_sem_collectstatic(settings) -> None:
    # O selo do cabeçalho é lido de ``STATIC_ROOT`` (``gerar_pdf_documento_texto``), que só existe após o collectstatic.
    settings.STATIC_ROOT = os.path.join(settings.BASE_DIR, 'comum', 'static')


def _resposta_500() -> requests.Response:
    resposta = requests.Response()
    resposta.status_code = 500
    resposta._content = b'wkhtmltopdf quebrou'
    return resposta


def _gerador_fora_do_ar(falha: type[Exception] | None) -> Callable[..., requests.Response]:
    def post(url: str, **kwargs: object) -> requests.Response:
        if falha:
            raise falha('gerador fora do ar')
        return _resposta_500()

    return post


@pytest.mark.parametrize('imprimir', [tasks.imprimir_pdf, tasks.imprimir_pdfa], ids=['pdf', 'pdfa'])
@pytest.mark.parametrize(
    'falha', [requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, None], ids=['timeout', 'conexao', 'http_500']
)
def test_gerador_indisponivel_encerra_a_tarefa_com_mensagem(sync_permissions, imprimir: Callable[..., object], falha: type[Exception] | None) -> None:
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFRN'})
    Configuracao.objects.update_or_create(app='comum', chave='caminho_libreoffice', defaults={'valor': 'http://gerador.test:9000'})
    Configuracao.clear_cache()
    servidor = ServidorFactory(setor=SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria'))
    user = servidor.get_user()
    documento = DocumentoTextoFactory(usuario_criacao=user)
    request = RequestFactory().get('/')
    request.user = user

    with (
        mock.patch('djtools.utils.pdf.running_tests', return_value=False),
        mock.patch.object(requests.Session, 'post', side_effect=_gerador_fora_do_ar(falha)),
    ):
        resposta = imprimir(request, documento, None, False, False, 'portrait')

    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    assert tarefa.end is not None
    assert tasks.MENSAGEM_GERADOR_PDF_INDISPONIVEL in tarefa.error
    assert not tarefa.file
