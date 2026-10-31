import io
import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from djtools.storages import backends
from djtools.storages.backends import AWSUploadBackend, LocalUploadBackend
from djtools.utils.http import upload_em_pdf

CONTEUDO = b'conteudo do arquivo' * 10
# O CONTENT_LENGTH de um POST multipart inclui delimitadores e outros campos, então é maior que o arquivo.
CONTENT_LENGTH_MULTIPART = len(CONTEUDO) + 200


@pytest.fixture
def backend_local(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    backend = LocalUploadBackend()
    backend.setup('up', 'arquivo.txt')
    return backend


def _gravado(backend):
    backend.upload_complete()
    with open(backend._filepath, 'rb') as f:
        return f.read()


class TestLocalUploadBackend:
    def test_upload_por_formulario_mantem_o_arquivo(self, backend_local):
        uploaded = SimpleUploadedFile('arquivo.txt', CONTEUDO)

        assert backend_local.upload(uploaded, CONTENT_LENGTH_MULTIPART, False) is True
        assert _gravado(backend_local) == CONTEUDO

    def test_upload_ajax_completo_mantem_o_arquivo(self, backend_local):
        assert backend_local.upload(io.BytesIO(CONTEUDO), len(CONTEUDO), True) is True
        assert _gravado(backend_local) == CONTEUDO

    def test_upload_ajax_cancelado_remove_o_arquivo(self, backend_local):
        assert backend_local.upload(io.BytesIO(CONTEUDO), len(CONTEUDO) + 1, True) is False
        assert backend_local._dest.closed
        assert not os.path.exists(backend_local._filepath)

    def test_upload_ajax_com_erro_de_leitura_remove_o_arquivo_parcial(self, backend_local, tmp_path):
        class LeituraQuebrada(io.BytesIO):
            lidos = 0

            def read(self, size=-1):
                self.lidos += 1
                if self.lidos > 1:
                    raise OSError('conexão derrubada')
                return super().read(size)

        assert backend_local.upload(LeituraQuebrada(CONTEUDO), len(CONTEUDO), True) is False
        assert backend_local._dest.closed
        assert not os.path.exists(backend_local._filepath)
        assert [p for p in tmp_path.rglob('*') if p.is_file()] == []


class TestAWSUploadBackend:
    @pytest.fixture
    def salvos(self, monkeypatch):
        salvos = {}

        def salvar(nome, conteudo):
            salvos[nome] = conteudo.getvalue()
            return nome

        monkeypatch.setattr(backends.default_storage, 'save', salvar)
        return salvos

    def test_upload_por_formulario_grava_no_storage(self, salvos):
        backend = AWSUploadBackend()
        backend.setup('up', 'arquivo.txt')

        assert backend.upload(SimpleUploadedFile('arquivo.txt', CONTEUDO), CONTENT_LENGTH_MULTIPART, False) is True
        assert salvos == {'up/arquivo.txt': CONTEUDO}

    def test_upload_ajax_cancelado_nao_grava(self, salvos):
        backend = AWSUploadBackend()
        backend.setup('up', 'arquivo.txt')

        assert backend.upload(io.BytesIO(CONTEUDO), len(CONTEUDO) + 1, True) is False
        assert salvos == {}

    def test_upload_complete_sem_upload_bem_sucedido_nao_levanta(self, salvos):
        backend = AWSUploadBackend()
        backend.setup('up', 'arquivo.txt')

        assert backend.upload(io.BytesIO(CONTEUDO), len(CONTEUDO) + 1, True) is False
        assert backend.upload_complete() is None


class TestUploadEmPdfComOsBackends:
    """O stream que ``upload_em_pdf`` devolve no ajax (cabeçalho relido + resto do corpo) é gravado inteiro pelos dois backends."""

    PDF = b'%PDF-1.7\n' + CONTEUDO * 20_000

    def _upload(self):
        request = RequestFactory().post(
            '/up/?qqfile=a.pdf', data=self.PDF, content_type='application/octet-stream', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        return upload_em_pdf(request)[0]

    def test_local(self, backend_local):
        assert backend_local.upload(self._upload(), len(self.PDF), True) is True
        assert _gravado(backend_local) == self.PDF

    def test_aws(self, monkeypatch):
        salvos = []
        monkeypatch.setattr(backends.default_storage, 'save', lambda nome, conteudo: salvos.append(conteudo.getvalue()) or nome)
        backend = AWSUploadBackend()
        backend.setup('up', 'a.pdf')

        assert backend.upload(self._upload(), len(self.PDF), True) is True
        assert salvos == [self.PDF]
