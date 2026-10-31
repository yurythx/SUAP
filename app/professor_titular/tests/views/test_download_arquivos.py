import os
import tempfile
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from professor_titular.views import download_arquivos


@pytest.mark.django_db
class DownloadArquivosCacheFileNoneTest:
    """Test that download_arquivos handles cache_file returning None without crashing.

    Bug: SUAP-T44 — os.path.split(None) raises TypeError when cache_file returns None.
    Fix: Skip files where cache_file returns None instead of passing None to os.path.split.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, rf):
        self.factory = rf
        self.user = MagicMock()
        self.user.is_authenticated = True

    def _make_processo(self, arquivosexigidos=None, arquivo_set=None):
        mock_processo = MagicMock()
        mock_processo.arquivosexigidos_set.all.return_value = arquivosexigidos or []
        mock_processo.arquivo_set.all.return_value = arquivo_set or []
        mock_processo.processo_eletronico = None
        mock_processo.protocolo = None
        mock_processo.pk = 1
        type(mock_processo).pk = PropertyMock(return_value=1)
        return mock_processo

    @patch('professor_titular.views.cache_file', return_value=None)
    @patch('professor_titular.views.get_object_or_404')
    def test_cache_file_none_on_arquivosexigidos_skips_gracefully(self, mock_get_404, mock_cache):
        """cache_file returns None for ArquivosExigidos — view skips, no TypeError."""
        mock_ae = MagicMock()
        mock_ae.diretorio = 'path/exigido.pdf'
        mock_ae.nome = 'Doc Exigido'

        mock_get_404.return_value = self._make_processo(arquivosexigidos=[mock_ae])

        request = self.factory.get('/professor_titular/download_arquivos/1/')
        request.user = self.user
        response = download_arquivos(request, processo_id=1)
        assert response.status_code == 200

    @patch('professor_titular.views.cache_file', return_value=None)
    @patch('professor_titular.views.get_object_or_404')
    def test_cache_file_none_on_arquivo_skips_gracefully(self, mock_get_404, mock_cache):
        """cache_file returns None for Arquivo — view skips, no TypeError."""
        mock_arq = MagicMock()
        mock_arq.diretorio = 'path/pontuacao.pdf'
        mock_arq.nome = 'Arquivo Pontuacao'

        mock_get_404.return_value = self._make_processo(arquivo_set=[mock_arq])

        request = self.factory.get('/professor_titular/download_arquivos/1/')
        request.user = self.user
        response = download_arquivos(request, processo_id=1)
        assert response.status_code == 200

    @patch('professor_titular.views.cache_file', return_value=None)
    @patch('professor_titular.views.get_object_or_404')
    def test_cache_file_none_both_types_no_crash(self, mock_get_404, mock_cache):
        """Both ArquivosExigidos and Arquivo have cache_file=None — no TypeError."""
        mock_ae = MagicMock()
        mock_ae.diretorio = 'path/exigido.pdf'
        mock_ae.nome = 'Doc Exigido'

        mock_arq = MagicMock()
        mock_arq.diretorio = 'path/pontuacao.pdf'
        mock_arq.nome = 'Arquivo Pontuacao'

        mock_get_404.return_value = self._make_processo(arquivosexigidos=[mock_ae], arquivo_set=[mock_arq])

        request = self.factory.get('/professor_titular/download_arquivos/1/')
        request.user = self.user
        response = download_arquivos(request, processo_id=1)
        assert response.status_code == 200

    @patch('professor_titular.views.cache_file')
    @patch('professor_titular.views.get_object_or_404')
    def test_mixed_cache_results_skips_none_includes_valid(self, mock_get_404, mock_cache):
        """Mix of None and valid cache_file results — only valid files processed."""
        mock_ae = MagicMock()
        mock_ae.diretorio = 'path/exigido.pdf'
        mock_ae.nome = 'Doc Exigido'

        mock_arq = MagicMock()
        mock_arq.diretorio = 'path/pontuacao.pdf'
        mock_arq.nome = 'Arquivo Pontuacao'

        mock_get_404.return_value = self._make_processo(arquivosexigidos=[mock_ae], arquivo_set=[mock_arq])

        # Create a real temp file so zipfile.ZipFile.write succeeds
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(b'%PDF-1.4 test content')
            tmp_path = tmp.name

        try:
            # First call returns None (skip), second returns valid path (include)
            mock_cache.side_effect = [None, tmp_path]

            request = self.factory.get('/professor_titular/download_arquivos/1/')
            request.user = self.user
            response = download_arquivos(request, processo_id=1)
            assert response.status_code == 200
            # Response should be a zip file
            assert response['Content-Disposition'].startswith('attachment')
        finally:
            os.unlink(tmp_path)

    @patch('professor_titular.views.cache_file', return_value=None)
    @patch('professor_titular.views.get_object_or_404')
    def test_all_cache_files_none_returns_empty_zip(self, mock_get_404, mock_cache):
        """All cache_file calls return None — empty zip returned, no crash."""
        mock_ae = MagicMock()
        mock_ae.diretorio = 'path/exigido.pdf'
        mock_ae.nome = 'Doc Exigido'

        mock_arq = MagicMock()
        mock_arq.diretorio = 'path/pontuacao.pdf'
        mock_arq.nome = 'Arquivo Pontuacao'

        mock_get_404.return_value = self._make_processo(arquivosexigidos=[mock_ae], arquivo_set=[mock_arq])

        request = self.factory.get('/professor_titular/download_arquivos/1/')
        request.user = self.user
        response = download_arquivos(request, processo_id=1)
        assert response.status_code == 200
