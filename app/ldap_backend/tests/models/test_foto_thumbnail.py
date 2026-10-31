"""Foto do servidor (``thumbnailPhoto``) lida durante o ``sync_user`` do login.

#17597: com o S3 lento, a leitura da foto segurava o ``authenticate`` até o gunicorn abortar o worker. A fronteira simulada é a
rede: um "S3" local que aceita a conexão e nunca responde.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from ldap_backend.utils import _storage_da_foto, get_thumbnail_content

SERVIDOR_COM_FOTO = SimpleNamespace(foto=SimpleNamespace(name='fotos/1234567.jpg'))


@pytest.fixture
def s3_que_nao_responde(settings) -> Iterator[None]:
    servidor = socket.create_server(('127.0.0.1', 0))
    conexoes: list[socket.socket] = []

    def aceitar_e_calar() -> None:
        while True:
            try:
                conexoes.append(servidor.accept()[0])
            except OSError:
                return

    threading.Thread(target=aceitar_e_calar, daemon=True).start()
    settings.STORAGES = {
        **settings.STORAGES,
        'default': {
            'BACKEND': 'djtools.storages.s3.MediaS3Storage',
            'OPTIONS': {
                'endpoint_url': f'http://127.0.0.1:{servidor.getsockname()[1]}',
                'access_key': 'chave',
                'secret_key': 'segredo',
                'region_name': 'us-east-1',
            },
        },
    }
    _storage_da_foto.cache_clear()
    yield
    _storage_da_foto.cache_clear()
    servidor.close()
    for conexao in conexoes:
        conexao.close()


@pytest.fixture
def foto_no_disco(settings, tmp_path: Path) -> Iterator[bytes]:
    settings.MEDIA_ROOT = str(tmp_path)
    conteudo = b'\xff\xd8 jpeg 75x100'
    (tmp_path / 'fotos' / '75x100').mkdir(parents=True)
    (tmp_path / 'fotos' / '75x100' / '1234567.jpg').write_bytes(conteudo)
    _storage_da_foto.cache_clear()
    yield conteudo
    _storage_da_foto.cache_clear()


def test_s3_sem_resposta_devolve_sem_foto_em_vez_de_segurar_o_login(s3_que_nao_responde: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('ldap_backend.utils.TIMEOUT_FOTO_SEGUNDOS', 1)
    inicio = time.monotonic()

    assert get_thumbnail_content(SERVIDOR_COM_FOTO) is None
    assert time.monotonic() - inicio < 10


def test_foto_disponivel_vai_para_o_thumbnail(foto_no_disco: bytes) -> None:
    assert get_thumbnail_content(SERVIDOR_COM_FOTO) == foto_no_disco


def test_servidor_sem_foto_nao_consulta_o_storage() -> None:
    assert get_thumbnail_content(SimpleNamespace(foto=None)) is None
