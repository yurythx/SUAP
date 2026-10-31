"""Conversores de ``djtools.utils.pdf`` que usam o serviço externo (``caminho_libreoffice``): docx, xlsx e csv para PDF.

Só a fronteira é simulada: a configuração e o ``requests.post`` do wrapper ``djtools.utils.requests``.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from djtools.utils.pdf import converter_csv_para_pdf, gerar_documento_impressao


def _configuracao(_app: str, chave: str, _enviroment_variable_name: str | None = None) -> str:
    return {'caminho_libreoffice': 'http://pdfprinter:8000', 'token_libreoffice': 'segredo'}[chave]


def _gerar(resposta: MagicMock | Exception) -> str:
    post = MagicMock(side_effect=resposta) if isinstance(resposta, Exception) else MagicMock(return_value=resposta)
    with (
        patch('comum.models.Configuracao.get_valor_por_chave', side_effect=_configuracao),
        patch('djtools.utils.pdf.requests.post', post),
    ):
        return gerar_documento_impressao({'#NOME#': 'Fulano'}, io.BytesIO(b'docx'))


@pytest.mark.parametrize('status', [500, 503, 204])
def test_servico_respondendo_nao_200_levanta_http_error(status: int) -> None:
    """#17600: o não-200 virava ``Exception`` genérica, indistinguível de erro de programação."""
    with pytest.raises(requests.HTTPError, match='servidor de impressão'):
        _gerar(MagicMock(status_code=status, content=b''))


def test_queda_do_servico_chega_como_request_exception() -> None:
    with pytest.raises(requests.exceptions.RequestException):
        _gerar(requests.exceptions.ReadTimeout('servico fora do ar'))


def test_resposta_200_devolve_o_pdf_num_temporario() -> None:
    caminho = _gerar(MagicMock(status_code=200, content=b'%PDF-1.4 gerado'))

    assert Path(caminho).read_bytes() == b'%PDF-1.4 gerado'
    Path(caminho).unlink()


def test_csv_respondendo_nao_200_levanta_http_error(tmp_path: Path) -> None:
    csv = tmp_path / 'dados.csv'
    csv.write_text('nome,idade\nFulano,30\nBeltrano,40\n')
    with (
        patch('djtools.utils.pdf.running_tests', return_value=False),
        patch('djtools.utils.pdf.magic.Magic', return_value=MagicMock(from_file=MagicMock(return_value='text/csv'))),
        patch('comum.models.Configuracao.get_valor_por_chave', side_effect=_configuracao),
        patch('djtools.utils.pdf.requests.post', MagicMock(return_value=MagicMock(status_code=503, content=b''))),
        pytest.raises(requests.HTTPError),
    ):
        converter_csv_para_pdf(str(csv))
