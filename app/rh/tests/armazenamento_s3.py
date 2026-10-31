"""Storage de teste com a semântica de pasta do S3/MinIO, sobre o sistema de arquivos.

No S3 uma "pasta" é só um prefixo de chave: `exists(pasta)` devolve False mesmo com arquivos
dentro, `listdir` de um prefixo sem nada devolve listas vazias e apagar o prefixo não faz nada.
Código que funciona com o `FileSystemStorage` do dev pode quebrar em silêncio com o MinIO.
"""

from __future__ import annotations

import os

from django.core.files.storage import FileSystemStorage


class ArmazenamentoComoS3(FileSystemStorage):
    def exists(self, name: str) -> bool:
        return os.path.isfile(self.path(name))

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        if not os.path.isdir(self.path(path)):
            return [], []
        return super().listdir(path)

    def delete(self, name: str) -> None:
        if os.path.isdir(self.path(name)):
            return
        super().delete(name)
