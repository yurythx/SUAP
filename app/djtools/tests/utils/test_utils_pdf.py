from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from django.forms import ValidationError
from django.test import override_settings

from djtools.utils.pdf import _check_content_type_allowed, full_check_file


class TestCheckContentTypeAllowed:
    def test_pdf_mime_returns_true(self):
        result = _check_content_type_allowed('application/pdf', raise_validation_error=False)
        assert result is True

    @override_settings(CONTENT_TYPES=['application/pdf', 'text/plain'])
    def test_allowed_non_pdf_returns_false(self):
        result = _check_content_type_allowed('text/plain', raise_validation_error=False)
        assert result is False

    def test_disallowed_type_returns_none(self):
        result = _check_content_type_allowed('video/mp4', raise_validation_error=False)
        assert result is None

    def test_disallowed_type_raises(self):
        with pytest.raises(ValidationError, match='Tipo de arquivo não permitido'):
            _check_content_type_allowed('video/mp4', raise_validation_error=True)

    @override_settings(CONTENT_TYPES=['application/pdf', 'image/png', 'text/csv'])
    def test_custom_content_types_from_settings(self):
        assert _check_content_type_allowed('application/pdf', False) is True
        assert _check_content_type_allowed('image/png', False) is False
        assert _check_content_type_allowed('text/csv', False) is False
        assert _check_content_type_allowed('video/mp4', False) is None


class TestFullCheckFileRequired:
    def test_content_none_raises_when_required(self):
        with pytest.raises(ValidationError, match='Este campo é obrigatório'):
            full_check_file(None, check_required=True)

    def test_content_none_returns_false_when_required_no_raise(self):
        result = full_check_file(None, check_required=True, raise_validation_error=False)
        assert result is False

    def test_empty_content_returns_true_when_not_required(self):
        result = full_check_file(None, check_required=False)
        assert result is True

    def test_falsy_content_returns_true_when_not_required(self):
        result = full_check_file('', check_required=False)
        assert result is True


class TestFullCheckFileMaxSize:
    def test_content_below_max_size_passes(self):
        content = MagicMock(size=100)
        content.read.return_value = b'%PDF-1.4 fake pdf content'
        with (
            patch('djtools.utils.pdf.check_pdf', return_value=True),
            patch('djtools.utils.pdf.decrypt_pdf_content', return_value=content),
            patch('djtools.utils.pdf.check_can_edit_pdf', return_value=True),
            patch('djtools.utils.pdf.magic') as mock_magic,
        ):
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            result = full_check_file(content, max_file_size=200)
            assert result is True

    def test_content_above_max_size_raises(self):
        content = MagicMock(size=300)
        with pytest.raises(ValidationError, match='tamanho máximo'):
            full_check_file(content, max_file_size=200)

    def test_content_above_max_size_returns_false_no_raise(self):
        content = MagicMock(size=300)
        result = full_check_file(content, max_file_size=200, raise_validation_error=False)
        assert result is False


class TestFullCheckFileContentTypes:
    def test_disallowed_content_type_raises(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'video/mp4'
            with pytest.raises(ValidationError, match='Tipo de arquivo não permitido'):
                full_check_file(content, check_content_types=True)

    def test_skip_content_type_check(self):
        content = MagicMock(size=100)
        with (
            patch('djtools.utils.pdf.check_pdf', return_value=True),
            patch('djtools.utils.pdf.decrypt_pdf_content', return_value=content),
            patch('djtools.utils.pdf.check_can_edit_pdf', return_value=True),
        ):
            result = full_check_file(content, check_content_types=False)
            assert result is True


class TestFullCheckFileNonPdf:
    @override_settings(CONTENT_TYPES=['application/pdf', 'text/plain'])
    def test_allowed_non_pdf_skips_qpdf_checks_and_passes(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'text/plain'
            result = full_check_file(content)
            assert result is True

    @override_settings(CONTENT_TYPES=['application/pdf', 'text/plain'])
    def test_allowed_non_pdf_does_not_call_qpdf(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'text/plain'
            with patch('djtools.utils.pdf.check_pdf') as mock_check:
                result = full_check_file(content)
                assert result is True
                mock_check.assert_not_called()


class TestFullCheckFilePdf:
    def test_valid_pdf_passes_all_checks(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with (
                patch('djtools.utils.pdf.check_pdf', return_value=True),
                patch('djtools.utils.pdf.decrypt_pdf_content', return_value=content),
                patch('djtools.utils.pdf.check_can_edit_pdf', return_value=True),
            ):
                result = full_check_file(content)
                assert result is True

    def test_invalid_pdf_raises(self):
        content = MagicMock(size=100)
        with (
            patch('djtools.utils.pdf.magic') as mock_magic,
            patch('djtools.utils.pdf.check_pdf', return_value=False),
        ):
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with pytest.raises(ValidationError, match='Arquivo protegido com senha'):
                full_check_file(content)

    def test_invalid_pdf_returns_false_no_raise(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with patch('djtools.utils.pdf.check_pdf', return_value=False):
                result = full_check_file(content, raise_validation_error=False)
                assert result is False

    def test_encrypted_pdf_raises(self):
        content = MagicMock(size=100)
        with (
            patch('djtools.utils.pdf.magic') as mock_magic,
            patch('djtools.utils.pdf.check_pdf', return_value=True),
            patch('djtools.utils.pdf.decrypt_pdf_content', side_effect=Exception('encrypted')),
        ):
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with pytest.raises(ValidationError, match='Arquivo protegido com senha'):
                full_check_file(content)

    def test_encrypted_pdf_without_decrypt_passes(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with (
                patch('djtools.utils.pdf.check_pdf', return_value=True),
                patch('djtools.utils.pdf.check_can_edit_pdf', return_value=True),
            ):
                result = full_check_file(content, can_decrypt_content=False)
                assert result is True

    def test_uneditable_pdf_raises(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with (
                patch('djtools.utils.pdf.check_pdf', return_value=True),
                patch('djtools.utils.pdf.decrypt_pdf_content', return_value=content),
                patch('djtools.utils.pdf.check_can_edit_pdf', return_value=False),
                pytest.raises(ValidationError, match='protegido contra escrita'),
            ):
                full_check_file(content)

    def test_skip_edit_check_passes(self):
        content = MagicMock(size=100)
        with patch('djtools.utils.pdf.magic') as mock_magic:
            mock_magic.Magic.return_value.from_buffer.return_value = 'application/pdf'
            with (
                patch('djtools.utils.pdf.check_pdf', return_value=True),
                patch('djtools.utils.pdf.decrypt_pdf_content', return_value=content),
            ):
                result = full_check_file(content, can_edit_required=False)
                assert result is True


class TestRenderPdfComWkhtmltopdf:
    """O ramo HTTP de render_pdf_from_template_with_wkhtmltopdf."""

    def _configuracao(self, _app, chave, _enviroment_variable_name=None):
        # get_valor_por_chave(app, chave, ...): a ordem real dos args, não (chave, padrao).
        return {'caminho_libreoffice': 'http://pdfprinter:8000', 'token_libreoffice': 'segredo'}[chave]

    def _resposta(self, status_code, content=b'%PDF-1.4', json_data=None):
        resposta = MagicMock(status_code=status_code, content=content, text='')
        resposta.json.return_value = json_data or {}
        return resposta

    def _chamar(self, mock_post, assets):
        from djtools.utils.pdf import render_pdf_from_template_with_wkhtmltopdf

        with (
            patch('comum.models.Configuracao.get_valor_por_chave', side_effect=self._configuracao),
            patch('djtools.utils.pdf.render_to_string', return_value='<html></html>'),
            patch('djtools.utils.pdf.coletar_assets', return_value=assets),
            patch('djtools.utils.pdf.requests.post', mock_post),
        ):
            return render_pdf_from_template_with_wkhtmltopdf('x.html', cmd_options={'orientation': 'portrait'})

    def test_payload_leva_apenas_os_hashes(self):
        from djtools.utils.estaticos_pdf import Asset

        mock_post = MagicMock(return_value=self._resposta(200))
        assert self._chamar(mock_post, {'css/x.css': Asset('abc', 'Y29udGV1ZG8=')}) == b'%PDF-1.4'
        enviado = mock_post.call_args.kwargs['json']
        assert enviado['assets'] == {'css/x.css': 'abc'}
        assert 'blobs' not in enviado

    def test_409_reenvia_uma_vez_com_os_blobs_faltantes(self):
        from djtools.utils.estaticos_pdf import Asset

        assets = {'css/x.css': Asset('abc', 'AAA='), 'img/y.png': Asset('def', 'BBB=')}
        mock_post = MagicMock(side_effect=[self._resposta(409, json_data={'missing': ['abc']}), self._resposta(200)])
        assert self._chamar(mock_post, assets) == b'%PDF-1.4'
        assert mock_post.call_count == 2
        segundo = mock_post.call_args_list[1].kwargs['json']
        assert segundo['blobs'] == {'abc': 'AAA='}
        assert segundo['assets'] == {'css/x.css': 'abc', 'img/y.png': 'def'}

    def test_segundo_409_levanta_excecao(self):
        from djtools.utils.estaticos_pdf import Asset

        mock_post = MagicMock(return_value=self._resposta(409, json_data={'missing': ['abc']}))
        with pytest.raises(requests.HTTPError, match='servidor de impressão'):
            self._chamar(mock_post, {'css/x.css': Asset('abc', 'AAA=')})
        assert mock_post.call_count == 2

    def test_sem_cmd_options_nao_levanta(self):
        from djtools.utils.pdf import render_pdf_from_template_with_wkhtmltopdf

        mock_post = MagicMock(return_value=self._resposta(200))
        with (
            patch('comum.models.Configuracao.get_valor_por_chave', side_effect=self._configuracao),
            patch('djtools.utils.pdf.render_to_string', return_value='<html></html>'),
            patch('djtools.utils.pdf.coletar_assets', return_value={}),
            patch('djtools.utils.pdf.requests.post', mock_post),
        ):
            assert render_pdf_from_template_with_wkhtmltopdf('x.html') == b'%PDF-1.4'
        assert mock_post.call_args.kwargs['json']['options'] == {}
