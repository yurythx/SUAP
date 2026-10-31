"""Pastas da importação SIAPE no storage padrão: sistema de arquivos (dev) ou S3/MinIO (produção).

Não usa `default_storage.exists(pasta)`: no S3/MinIO uma pasta é só um prefixo de chave e
`exists` devolve False mesmo com arquivos dentro — o código "funcionaria" no dev e, em produção,
não acharia o zip do extrator nem apagaria nada.
"""

from __future__ import annotations

from django.core.files.storage import default_storage


# Para que serve: listar uma pasta do storage igual no dev (disco) e em produção (S3/MinIO).
# O comando noturno usa para achar os zips do extrator e `apagar_pasta` para saber o que apagar;
# com `exists()` no lugar, em produção a pasta pareceria sempre vazia.
def arquivos_da_pasta(pasta: str) -> list[str]:
    """Nomes dos arquivos diretamente dentro da pasta; lista vazia se ela não existir."""
    if not pasta:
        return []
    try:
        return list(default_storage.listdir(pasta)[1])
    except FileNotFoundError:  # sistema de arquivos: diretório inexistente
        return []


# Para que serve: os arquivos do extrator têm dados pessoais e ocupam espaço; depois de importados
# (ou descartados) não devem ficar no storage. Usado ao fim da execução, na interrupção manual e
# para desfazer uma importação que falhou ao ser criada ou que o comando não conseguiu iniciar.
def apagar_pasta(pasta: str) -> None:
    """Apaga os arquivos diretamente dentro da pasta e, no sistema de arquivos, o diretório vazio (no S3 não há o
    que remover). Subpastas não são percorridas.
    """
    for nome in arquivos_da_pasta(pasta):
        default_storage.delete(f'{pasta}/{nome}')
    if pasta:
        try:
            default_storage.delete(pasta)
        except OSError:  # diretório inexistente ou com subpastas: os arquivos já foram
            pass
