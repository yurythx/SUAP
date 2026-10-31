"""Upload ajax dos arquivos do processo de professor titular: por critério (``/professor_titular/professor_titular_upload/``)
e documentos exigidos (``/professor_titular/professor_titular_upload_documentos_exigidos/``).

Os uploaders gravavam no storage antes de conferir o dono (#17715): quem não era dono recebia 403, mas o arquivo
ficava órfão. Agora anexa só quem vê o uploader na tela (o dono, com o processo editável), antes de gravar, e só PDF.
"""

import inspect
import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.http import HttpResponse
from django.test import Client

import professor_titular.views
from comum.models import User
from djtools.storages import AWSUploadBackend
from rh.tests.factories import ServidorFactory
from professor_titular.models import Arquivo, ArquivosExigidos, ProcessoTitular
from professor_titular.tests.factories import CriterioFactory, PontuacaoMinimaFactory, ProcessoTitularFactory

pytestmark = pytest.mark.django_db

PDF = b'%PDF-1.4\n%arquivo de teste\n'
CRITERIO, DOCUMENTOS_EXIGIDOS = 'criterio', 'documentos_exigidos'


@pytest.fixture(autouse=True)
def _limpa_cache_de_perfil() -> Iterator[None]:
    """``User.VINCULOS`` é cache de classe por ``user.id``; o banco de teste recicla ids e o ``eh_dono`` erraria."""
    User.VINCULOS.clear()
    yield
    User.VINCULOS.clear()


@pytest.fixture
def midia(settings, tmp_path: Path) -> Path:
    """O storage em ``tmp_path``: o ``LocalUploadBackend`` grava sob ``MEDIA_ROOT``, o AWS via ``default_storage``."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        **settings.STORAGES,
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': str(tmp_path)}},
    }
    return tmp_path


@pytest.fixture
def processo(sync_permissions: None) -> ProcessoTitular:
    """Processo que o dono ainda edita: a tela só mostra o uploader com ``avaliado_pode_editar``."""
    return ProcessoTitularFactory(status=ProcessoTitular.STATUS_AGUARDANDO_ENVIO_CPPD)


@pytest.fixture
def cliente(processo: ProcessoTitular) -> Client:
    cliente = Client()
    cliente.force_login(processo.servidor.get_user())
    return cliente


@pytest.fixture(params=[CRITERIO, DOCUMENTOS_EXIGIDOS])
def rota(request) -> str:
    return request.param


def _url(rota: str, processo: ProcessoTitular) -> str:
    if rota == CRITERIO:
        criterio = CriterioFactory()
        # a resposta do critério mostra o teto do grupo, que vem da pontuação mínima do ano do processo
        PontuacaoMinimaFactory(grupo=criterio.indicador.grupo, ano=processo.ano)
        return f'/professor_titular/professor_titular_upload/?processo={processo.pk}&criterio={criterio.pk}'
    return f'/professor_titular/professor_titular_upload_documentos_exigidos/?processo={processo.pk}&tipo=TITULO_DOUTOR'


def _enviar(cliente: Client, rota: str, processo: ProcessoTitular, query: str = '&qqfile=a.pdf', conteudo: bytes = PDF, **extra) -> HttpResponse:
    """Como o uploader da tela: arquivo cru no corpo do POST ajax e o nome na querystring."""
    url = f'{_url(rota, processo)}{query}'
    return cliente.post(url, data=conteudo, content_type='application/octet-stream', headers={'X-Requested-With': 'XMLHttpRequest'}, **extra)


def _gravados(midia: Path) -> list[Path]:
    return [caminho for caminho in midia.rglob('*') if caminho.is_file()]


def _nada_anexado(processo: ProcessoTitular, midia: Path) -> bool:
    return (
        not Arquivo.objects.filter(processo=processo).exists()
        and not ArquivosExigidos.objects.filter(processo=processo).exists()
        and not _gravados(midia)
    )


def test_ajax_sem_nome_do_arquivo_responde_success_false(cliente: Client, processo: ProcessoTitular) -> None:
    resposta = _enviar(cliente, DOCUMENTOS_EXIGIDOS, processo, query='')

    assert resposta.status_code == 200
    assert resposta.json() == {'success': False}


def test_upload_cancelado_no_storage_remoto_responde_success_false(cliente: Client, processo: ProcessoTitular, monkeypatch, midia: Path) -> None:
    # ``unwrap``: o ``login_required`` copia o ``__dict__`` da instância para o wrapper
    monkeypatch.setattr(inspect.unwrap(professor_titular.views.professor_titular_upload_documentos_exigidos), 'get_backend', AWSUploadBackend)

    # CONTENT_LENGTH maior que o corpo: o navegador cancelou o envio no meio
    resposta = _enviar(cliente, DOCUMENTOS_EXIGIDOS, processo, CONTENT_LENGTH=str(len(PDF) + 10), **{'wsgi.input': io.BytesIO(PDF)})

    assert resposta.status_code == 200
    assert json.loads(resposta.content)['success'] is False
    assert _nada_anexado(processo, midia)


def test_anonimo_nao_anexa(processo: ProcessoTitular, midia: Path, rota: str) -> None:
    resposta = _enviar(Client(), rota, processo)

    assert resposta.status_code == 302
    assert resposta['Location'].startswith(django_settings.LOGIN_URL)
    assert _nada_anexado(processo, midia)


def test_quem_nao_e_dono_nao_anexa(processo: ProcessoTitular, midia: Path, rota: str) -> None:
    outro = Client()
    outro.force_login(ServidorFactory().get_user())

    assert _enviar(outro, rota, processo).status_code == 403
    assert _nada_anexado(processo, midia)


def test_dono_nao_anexa_com_o_processo_fora_da_edicao(cliente: Client, processo: ProcessoTitular, midia: Path, rota: str) -> None:
    processo.status = ProcessoTitular.STATUS_AGUARDANDO_AVALIADORES
    processo.save()

    assert _enviar(cliente, rota, processo).status_code == 403
    assert _nada_anexado(processo, midia)


def test_dono_anexa_pdf(cliente: Client, processo: ProcessoTitular, midia: Path, rota: str) -> None:
    resposta = _enviar(cliente, rota, processo)

    assert resposta.status_code == 200
    assert json.loads(resposta.content)['success'] is True
    assert [caminho.read_bytes() for caminho in _gravados(midia)] == [PDF]
    assert Arquivo.objects.filter(processo=processo).count() + ArquivosExigidos.objects.filter(processo=processo).count() == 1


@pytest.mark.parametrize(('nome', 'conteudo'), [('a.exe', PDF), ('a.pdf', b'MZ\x90\x00 executavel')], ids=['extensao', 'conteudo'])
def test_upload_recusa_o_que_nao_e_pdf(cliente: Client, processo: ProcessoTitular, midia: Path, rota: str, nome: str, conteudo: bytes) -> None:
    """A tela só aceita ``.pdf`` no navegador (``AjaxFileUploadField``); o servidor confere extensão e cabeçalho."""
    resposta = _enviar(cliente, rota, processo, query=f'&qqfile={nome}', conteudo=conteudo)

    assert json.loads(resposta.content)['success'] is False
    assert _nada_anexado(processo, midia)
