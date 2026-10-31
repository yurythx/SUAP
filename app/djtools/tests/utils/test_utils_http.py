import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from djtools.utils.http import ids_da_query, upload_em_pdf

PDF = b'%PDF-1.7\n' + b'conteudo do pdf\n' * 200_000  # ~3 MB


@pytest.mark.parametrize(
    ('query', 'esperado'),
    [('', []), ('?ids=', []), ('?ids=,,abc', []), ('?ids=1,,abc,2', [1, 2]), ('?ids=%203%20,-4,5.0', [3])],
)
def test_ids_da_query_le_do_get_descartando_lixo(query: str, esperado: list[int]) -> None:
    assert ids_da_query(RequestFactory().get('/' + query)) == esperado


@pytest.mark.parametrize(('valor', 'esperado'), [(None, []), ('', []), ('7-,-abc-8', [7, 8])])
def test_ids_da_query_aceita_string_e_separador(valor: str | None, esperado: list[int]) -> None:
    assert ids_da_query(valor, sep='-') == esperado


def test_ids_da_query_string_com_virgula_por_padrao() -> None:
    assert ids_da_query('1,2,x') == [1, 2]


class _CorpoContado(io.BytesIO):
    """Corpo do request que registra o tamanho pedido em cada ``read``."""

    def __init__(self, conteudo: bytes) -> None:
        super().__init__(conteudo)
        self.leituras: list[int] = []

    def read(self, size: int | None = -1) -> bytes:
        self.leituras.append(-1 if size is None else size)
        return super().read(size)


def _request_ajax(corpo: bytes, nome: str = 'doc.pdf'):
    request = RequestFactory().post(
        f'/up/?qqfile={nome}', data=corpo, content_type='application/octet-stream', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
    )
    request._stream = _CorpoContado(corpo)
    return request


@pytest.mark.parametrize('tamanho_leitura', [3, 5, 4093, 64 * 2**10, -1])
def test_upload_em_pdf_ajax_confere_so_o_cabecalho_e_devolve_o_conteudo_inteiro(tamanho_leitura: int) -> None:
    request = _request_ajax(PDF)

    upload, is_raw, filename = upload_em_pdf(request)

    assert request._stream.leituras == [5]
    assert (is_raw, filename) == (True, 'doc.pdf')
    pedacos = []
    while pedaco := upload.read(tamanho_leitura):
        pedacos.append(pedaco)
    assert b''.join(pedacos) == PDF


def test_upload_em_pdf_ajax_que_nao_e_pdf_devolve_none() -> None:
    assert upload_em_pdf(_request_ajax(b'GIF89a' + b'x' * 100)) is None
    assert upload_em_pdf(_request_ajax(PDF, nome='doc.txt')) is None


def test_upload_em_pdf_formulario_mantem_o_arquivo_do_inicio() -> None:
    request = RequestFactory().post('/up/', {'arquivo': SimpleUploadedFile('doc.pdf', PDF)})

    upload, is_raw, filename = upload_em_pdf(request)

    assert (is_raw, filename) == (False, 'doc.pdf')
    assert upload.read() == PDF
