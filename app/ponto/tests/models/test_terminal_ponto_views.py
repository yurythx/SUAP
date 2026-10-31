from types import SimpleNamespace
import zipfile

from ponto import views


def _pessoa_terminal(matricula: str):
    foto = SimpleNamespace(name=f'fotos/{matricula}.jpg')
    return SimpleNamespace(matricula=matricula, pessoa_fisica=SimpleNamespace(foto=foto))


def test_adicionar_foto_terminal_ponto_ignora_foto_sem_cache(monkeypatch, tmp_path):
    arquivo_dump = tmp_path / 'fotos.zip'

    monkeypatch.setattr(views, 'cache_file', lambda _remote_filename: None)

    pessoa = _pessoa_terminal('1111111')
    with zipfile.ZipFile(arquivo_dump, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        views._adicionar_foto_terminal_ponto(zip_file, pessoa.pessoa_fisica, pessoa.matricula)

    with zipfile.ZipFile(arquivo_dump) as zip_file:
        assert zip_file.namelist() == []


def test_arquivo_zip_valido_rejeita_arquivo_corrompido(tmp_path):
    arquivo_dump = tmp_path / 'fotos.zip'
    arquivo_dump.write_bytes(b'')

    assert views._arquivo_zip_valido(str(arquivo_dump)) is False
