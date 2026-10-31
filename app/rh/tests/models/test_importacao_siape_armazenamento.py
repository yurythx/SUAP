"""Pastas da importação SIAPE no storage: sistema de arquivos (dev) e S3/MinIO (produção)."""

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from rh.importacao_siape.armazenamento import apagar_pasta, arquivos_da_pasta


@pytest.mark.parametrize('backend', ['django.core.files.storage.FileSystemStorage', 'rh.tests.armazenamento_s3.ArmazenamentoComoS3'])
def test_lista_e_apaga_a_pasta_no_sistema_de_arquivos_e_no_s3(settings, tmp_path, backend):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {**settings.STORAGES, 'default': {'BACKEND': backend}}
    default_storage.save('importacoes/9/A.REF', ContentFile(b'ref'))
    default_storage.save('importacoes/9/A.TXT', ContentFile(b'txt'))

    assert sorted(arquivos_da_pasta('importacoes/9')) == ['A.REF', 'A.TXT']
    assert arquivos_da_pasta('importacoes/inexistente') == []

    apagar_pasta('importacoes/9')
    apagar_pasta('importacoes/inexistente')  # não levanta

    assert arquivos_da_pasta('importacoes/9') == []
