"""``AlunoArquivo.to_pdfa``: conversão para PDF/A no serviço externo (``caminho_libreoffice``).

Só a fronteira HTTP é simulada (``requests.Session.post``, usada pelo wrapper ``djtools.utils.requests``). Sem o patch de ``running_tests`` o ``convert_pdf_to_pdfa`` devolve o
próprio arquivo de entrada e nunca chega ao HTTP.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest import mock

import pytest
import requests

from comum.models import Configuracao
from edu.tests.factories import AlunoArquivoFactory

pytestmark = pytest.mark.django_db

PDFA = b'%PDF-1.4 convertido para PDF/A'
URL_CONVERSOR = 'http://conversor.test:9000'


@pytest.fixture
def tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redireciona os temporários do ``tempfile`` para ``tmp_path``, para contar o que sobra depois."""
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    return tmp_path


@pytest.fixture
def conversor_configurado() -> None:
    Configuracao.objects.update_or_create(app='comum', chave='caminho_libreoffice', defaults={'valor': URL_CONVERSOR})
    Configuracao.clear_cache()


def _to_pdfa(**post_kwargs: object) -> str:
    aluno_arquivo = AlunoArquivoFactory()
    with (
        mock.patch('djtools.utils.pdf.running_tests', return_value=False),
        mock.patch.object(requests.Session, 'post', **post_kwargs),
    ):
        return aluno_arquivo.to_pdfa()


@pytest.mark.parametrize('falha', [requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError])
def test_conversor_indisponivel_levanta_mensagem_amigavel_e_nao_vaza_temporarios(
    tmp_dir: Path, conversor_configurado: None, falha: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger='edu.models.arquivos'), pytest.raises(RuntimeError) as excinfo:
        _to_pdfa(side_effect=falha(f'falha em {URL_CONVERSOR}'))

    assert 'Serviço de conversão para PDF/A indisponível' in str(excinfo.value)
    assert 'conversor.test' not in str(excinfo.value)
    assert URL_CONVERSOR in caplog.text  # o detalhe técnico fica só no log
    # O ``convert_pdf_to_pdfa`` deixa para trás o arquivo de saída ainda vazio; os temporários do ``to_pdfa`` (com o conteúdo) somem.
    assert all(arquivo.stat().st_size == 0 for arquivo in tmp_dir.iterdir())


def test_conversao_com_sucesso_devolve_o_pdfa_e_remove_os_temporarios(tmp_dir: Path, conversor_configurado: None) -> None:
    resposta = requests.Response()
    resposta.status_code = 200
    resposta._content = PDFA

    caminho = _to_pdfa(return_value=resposta)

    assert Path(caminho).read_bytes() == PDFA
    assert list(tmp_dir.iterdir()) == [Path(caminho)]
