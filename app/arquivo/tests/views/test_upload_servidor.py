"""Upload de arquivos do servidor: as telas ``/arquivo/arquivos_upload/`` e o uploader ajax.

O uploader não exigia login nem permissão (#17715): um anônimo gravava no storage e qualquer logado anexava à pasta
de qualquer servidor; as telas também abriam para qualquer um. Agora telas e uploader exigem a permissão do menu
"Upload de Arquivos" (``arquivo.pode_fazer_upload_arquivo``, grupo "Uploader de Arquivos") e, como a tela só aceita
``.pdf`` no navegador, o uploader confere a extensão e o cabeçalho ``%PDF-``.
"""

import inspect
import io
import json
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

import arquivo.views
from arquivo.models import Arquivo
from djtools.storages import AWSUploadBackend, LocalUploadBackend
from rh.models import Servidor
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

PDF = b'%PDF-1.4\n%arquivo de teste\n'


@pytest.fixture
def servidor(sync_permissions: None) -> Servidor:
    return ServidorFactory()


@pytest.fixture
def cliente(servidor: Servidor) -> Client:
    """Um usuário do grupo "Uploader de Arquivos", que anexa à pasta de outro servidor."""
    uploader = ServidorFactory().get_user()
    uploader.groups.add(Group.objects.get(name='Uploader de Arquivos'))
    cliente = Client()
    cliente.force_login(uploader)
    return cliente


@pytest.fixture
def sem_permissao(servidor: Servidor) -> Client:
    """O próprio servidor, logado, mas fora do grupo "Uploader de Arquivos"."""
    cliente = Client()
    cliente.force_login(servidor.get_user())
    return cliente


@pytest.fixture
def midia(settings, tmp_path: Path) -> Path:
    """O storage em ``tmp_path``: o ``LocalUploadBackend`` grava sob ``MEDIA_ROOT``, o AWS via ``default_storage``."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        **settings.STORAGES,
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': str(tmp_path)}},
    }
    return tmp_path


@pytest.fixture(params=[LocalUploadBackend, AWSUploadBackend], ids=['local', 'aws'])
def storage(request, monkeypatch, midia: Path) -> Path:
    """O backend do uploader. ``unwrap``: o ``login_required`` copia o ``__dict__`` da instância para o wrapper."""
    monkeypatch.setattr(inspect.unwrap(arquivo.views.upload_handler), 'get_backend', request.param)
    return midia


def _enviar(cliente: Client, servidor: Servidor, query: str = '', conteudo: bytes = PDF, **extra) -> HttpResponse:
    url = f'{reverse("upload_handler")}?servidor={servidor.matricula}{query}'
    return cliente.post(url, data=conteudo, content_type='application/octet-stream', headers={'X-Requested-With': 'XMLHttpRequest'}, **extra)


def _gravados(midia: Path) -> list[Path]:
    return [caminho for caminho in midia.rglob('*') if caminho.is_file()]


def test_ajax_sem_nome_do_arquivo_responde_success_false(cliente: Client, servidor: Servidor) -> None:
    resposta = _enviar(cliente, servidor)

    assert resposta.status_code == 200
    assert resposta.json() == {'success': False}


def test_upload_cancelado_responde_success_false(cliente: Client, servidor: Servidor, storage: Path) -> None:
    # CONTENT_LENGTH maior que o corpo: o navegador cancelou o envio no meio
    resposta = _enviar(cliente, servidor, query='&qqfile=a.pdf', CONTENT_LENGTH=str(len(PDF) + 10), **{'wsgi.input': io.BytesIO(PDF)})

    assert resposta.status_code == 200
    assert json.loads(resposta.content)['success'] is False
    assert not Arquivo.objects.exists()
    assert _gravados(storage) == []


def test_upload_completo_cria_o_arquivo(cliente: Client, servidor: Servidor, storage: Path) -> None:
    resposta = _enviar(cliente, servidor, query='&qqfile=a.pdf')

    assert json.loads(resposta.content)['success'] is True
    arquivo = Arquivo.objects.get()
    assert arquivo.nome == 'a.pdf'
    assert arquivo.file.read() == PDF
    assert [caminho.read_bytes() for caminho in _gravados(storage)] == [PDF]


def test_anonimo_nao_anexa(servidor: Servidor, midia: Path) -> None:
    resposta = _enviar(Client(), servidor, query='&qqfile=a.pdf')

    assert resposta.status_code == 302
    assert resposta['Location'].startswith(django_settings.LOGIN_URL)
    assert not Arquivo.objects.exists()
    assert _gravados(midia) == []


@pytest.mark.parametrize(('nome', 'conteudo'), [('a.exe', PDF), ('a.pdf', b'MZ\x90\x00 executavel')], ids=['extensao', 'conteudo'])
def test_upload_recusa_o_que_nao_e_pdf(cliente: Client, servidor: Servidor, midia: Path, nome: str, conteudo: bytes) -> None:
    """A tela só aceita ``.pdf`` no navegador (``AjaxFileUploadField``); o servidor confere extensão e cabeçalho."""
    resposta = _enviar(cliente, servidor, query=f'&qqfile={nome}', conteudo=conteudo)

    assert json.loads(resposta.content)['success'] is False
    assert not Arquivo.objects.exists()
    assert _gravados(midia) == []


def test_sem_a_permissao_nao_anexa(sem_permissao: Client, servidor: Servidor, midia: Path) -> None:
    assert _enviar(sem_permissao, servidor, query='&qqfile=a.pdf').status_code == 403
    assert not Arquivo.objects.exists()
    assert _gravados(midia) == []


def _telas(servidor: Servidor) -> list[str]:
    return [reverse('selecionar_servidor'), reverse('arquivos_upload', kwargs={'servidor_matricula': servidor.matricula})]


def test_telas_de_upload_exigem_a_permissao(cliente: Client, sem_permissao: Client, servidor: Servidor) -> None:
    for url in _telas(servidor):
        anonimo = Client().get(url)
        assert anonimo.status_code == 302
        assert anonimo['Location'].startswith(django_settings.LOGIN_URL)
        assert sem_permissao.get(url).status_code == 403
        assert cliente.get(url).status_code == 200
