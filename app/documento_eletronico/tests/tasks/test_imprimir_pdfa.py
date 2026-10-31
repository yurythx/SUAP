"""Task ``imprimir_pdfa``: gera o PDF do documento e o converte para PDF/A no serviço externo (``caminho_libreoffice``).

Só a fronteira HTTP é simulada (``requests.Session.post``): o mesmo serviço atende o ``wkhtml_to_pdf`` (geração do PDF)
e o ``pdf_to_pdfa`` (conversão), que é a chamada que estoura no Sentry.
"""

from __future__ import annotations

import os
import tempfile
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

PDFA = b'%PDF-1.4 convertido para PDF/A'


@pytest.fixture(autouse=True)
def _static_root_sem_collectstatic(settings) -> None:
    # O selo do cabeçalho é lido de ``STATIC_ROOT`` (``gerar_pdf_documento_texto``), que só existe após o collectstatic.
    settings.STATIC_ROOT = os.path.join(settings.BASE_DIR, 'comum', 'static')


def _conversor(falha_pdfa: type[Exception] | None, status_pdfa: int = 200) -> Callable[..., requests.Response]:
    def post(url: str, **kwargs: object) -> requests.Response:
        if url.endswith('/pdf_to_pdfa') and falha_pdfa:
            raise falha_pdfa('conversor fora do ar')
        resposta = requests.Response()
        resposta.status_code = status_pdfa if url.endswith('/pdf_to_pdfa') else 200
        resposta._content = PDFA if url.endswith('/pdf_to_pdfa') else b'%PDF-1.4 original'
        return resposta

    return post


def _imprimir_pdfa(falha_pdfa: type[Exception] | None = None, status_pdfa: int = 200) -> Task:
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFRN'})
    Configuracao.objects.update_or_create(app='comum', chave='caminho_libreoffice', defaults={'valor': 'http://conversor.test:9000'})
    Configuracao.clear_cache()
    servidor = ServidorFactory(setor=SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria'))
    user = servidor.get_user()
    documento = DocumentoTextoFactory(usuario_criacao=user)
    request = RequestFactory().get('/')
    request.user = user
    # Sem o patch de ``running_tests`` o ``convert_pdf_to_pdfa`` devolve o próprio arquivo de entrada e nunca chega ao HTTP.
    with (
        mock.patch('djtools.utils.pdf.running_tests', return_value=False),
        mock.patch.object(requests.Session, 'post', side_effect=_conversor(falha_pdfa, status_pdfa)),
    ):
        resposta = tasks.imprimir_pdfa(request, documento, None, False, False, 'portrait')
    uuid = resposta.url.rstrip('/').rsplit('/', 1)[-1]
    return Task.objects.get(uuid=uuid)


@pytest.mark.parametrize('falha', [requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError])
def test_conversor_indisponivel_encerra_a_tarefa_com_mensagem(sync_permissions, falha: type[Exception]) -> None:
    """#16792: o ``ReadTimeout`` do conversor escapava da task como erro não tratado e o usuário ficava sem resposta."""
    tarefa = _imprimir_pdfa(falha_pdfa=falha)

    assert tarefa.end is not None
    assert 'Serviço de conversão para PDF/A indisponível' in tarefa.error
    assert not tarefa.file


@pytest.mark.parametrize('status', [500, 503])
def test_conversor_respondendo_erro_http_encerra_a_tarefa_com_mensagem(sync_permissions, status: int) -> None:
    """#17587: status != 200 do conversor virava ``Exception`` genérica (não tratada no Sentry) em vez de indisponibilidade."""
    tarefa = _imprimir_pdfa(status_pdfa=status)

    assert tarefa.end is not None
    assert 'Serviço de conversão para PDF/A indisponível' in tarefa.error
    assert not tarefa.file


@pytest.mark.parametrize('falha', [{'falha_pdfa': requests.exceptions.ReadTimeout}, {'status_pdfa': 503}])
def test_falha_do_conversor_nao_deixa_temporarios(sync_permissions, tmp_path, monkeypatch, falha: dict[str, object]) -> None:
    """#17601: o temporário de saída do PDF/A nascia antes do POST e sobrava vazio a cada falha do conversor."""
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))

    _imprimir_pdfa(**falha)

    assert list(tmp_path.iterdir()) == []


def test_conversao_com_sucesso_anexa_o_pdfa(sync_permissions) -> None:
    tarefa = _imprimir_pdfa()

    assert not tarefa.error
    assert tarefa.message == 'Documento impresso com sucesso.'
    with open(tarefa.file, 'rb') as arquivo:
        assert arquivo.read() == PDFA
