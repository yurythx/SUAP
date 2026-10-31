"""Recebe o zip do extrator, grava os pares REF/TXT na pasta da importação e os identifica."""

from __future__ import annotations

import gzip
import io
import zipfile
import zlib
from typing import TYPE_CHECKING

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from rh.importacao_siape.armazenamento import apagar_pasta
from rh.importacao_siape.identificacao import carregar_refs, identificar
from rh.importacao_siape.layouts import LAYOUTS
from rh.models import ImportacaoSiape, ImportacaoSiapeArquivo, SituacaoArquivoSiape

if TYPE_CHECKING:
    from comum.models import User

PASTA_IMPORTACOES = 'rh/arquivos_siape/importacoes'


class ArquivoExtratorInvalido(Exception):
    """O zip enviado não é válido: não é um zip, está corrompido, ou não contém pares REF/TXT."""


# Para que serve: ponto único que transforma um zip do extrator (enviado pela tela ou achado pelo
# comando noturno) numa importação pronta para seleção. Se algo der errado no meio, não sobra nem
# registro nem arquivo órfão no storage.
def criar_importacao(nome: str, conteudo_zip: bytes, origem: str, usuario: User | None = None) -> ImportacaoSiape:
    """Cria a `ImportacaoSiape` a partir do zip do extrator: descompacta, grava os pares REF/TXT
    na pasta da importação e identifica o layout de cada um.

    Args:
        nome: Nome original do arquivo enviado, gravado em `ImportacaoSiape.arquivo`.
        conteudo_zip: Bytes do zip do extrator.
        origem: `'tela'` (upload manual) ou `'comando'` (pasta do extrator, via management command).
        usuario: Usuário que fez o upload, quando houver (`None` para importações por comando).

    Returns:
        A `ImportacaoSiape` criada (situação `identificada`), com um `ImportacaoSiapeArquivo` por
        par REF/TXT completo.

    Raises:
        ArquivoExtratorInvalido: se o zip não puder ser lido, algum membro estiver corrompido, ou
            não houver nenhum par REF/TXT completo dentro dele (nada é criado nesses casos).
        Exception: qualquer erro ao gravar no banco ou no storage é relançado, depois de desfeita
            a transação e apagados os arquivos já gravados.
    """
    pares = _ler_pares(conteudo_zip)
    refs = carregar_refs()
    pasta = ''
    try:
        with transaction.atomic():
            importacao = ImportacaoSiape.objects.create(arquivo=nome, origem=origem, enviado_por=usuario)
            importacao.pasta = pasta = f'{PASTA_IMPORTACOES}/{importacao.pk}'
            importacao.save()
            for base, par in sorted(pares.items()):
                _registrar_arquivo(importacao, base, par, refs)
    except Exception:
        # a transação desfaz os registros, mas não os arquivos já gravados no storage
        apagar_pasta(pasta)
        raise
    return importacao


def _ler_pares(conteudo_zip: bytes) -> dict[str, dict[str, bytes]]:
    """Lê o zip e agrupa por nome base os membros `.REF`/`.TXT` (descomprimindo `.gz` quando houver).

    O caminho de pastas dentro do zip é descartado: dois membros com o mesmo nome em pastas
    diferentes caem no mesmo par, e o último lido prevalece.

    Args:
        conteudo_zip: Bytes do zip do extrator.

    Returns:
        Nome base do par -> {'REF': conteúdo, 'TXT': conteúdo}, só para os pares completos (com
        ambas as extensões presentes).

    Raises:
        ArquivoExtratorInvalido: se `conteudo_zip` não for um zip válido, se algum membro estiver
            corrompido, ou se nenhum par REF/TXT completo for encontrado.
    """
    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except zipfile.BadZipFile as erro:
        raise ArquivoExtratorInvalido('O arquivo enviado não é um zip válido.') from erro
    pares: dict[str, dict[str, bytes]] = {}
    with arquivo_zip:
        for membro in arquivo_zip.infolist():
            nome_membro = membro.filename.rsplit('/', 1)[-1]
            nome, conteudo = _ler_membro(arquivo_zip, membro, nome_membro)
            base, _, extensao = nome.rpartition('.')
            if base and extensao.upper() in ('REF', 'TXT'):
                pares.setdefault(base, {})[extensao.upper()] = conteudo
    completos = {base: par for base, par in pares.items() if len(par) == 2}
    if not completos:
        raise ArquivoExtratorInvalido('O zip não contém pares de arquivos .REF/.TXT do extrator.')
    return completos


def _ler_membro(arquivo_zip: zipfile.ZipFile, membro: zipfile.ZipInfo, nome_membro: str) -> tuple[str, bytes]:
    """Lê e descomprime um membro do zip, convertendo qualquer erro de leitura em `ArquivoExtratorInvalido`.

    Raises:
        ArquivoExtratorInvalido: se o membro estiver corrompido (zip, gzip ou zlib inválido).
    """
    try:
        return _descomprimir(nome_membro, arquivo_zip.read(membro))
    except (zipfile.BadZipFile, gzip.BadGzipFile, EOFError, zlib.error, OSError) as erro:
        raise ArquivoExtratorInvalido(f'{nome_membro}: arquivo corrompido.') from erro


def _descomprimir(nome: str, conteudo: bytes) -> tuple[str, bytes]:
    """Descomprime `conteudo` se `nome` terminar em `.gz` (removendo a extensão do nome devolvido)."""
    if nome.lower().endswith('.gz'):
        return nome[:-3], gzip.decompress(conteudo)
    return nome, conteudo


def _situacao_inicial(layout: str | None) -> tuple[str, bool, str]:
    """Situação, seleção e motivo iniciais de um `ImportacaoSiapeArquivo`, a partir do layout identificado.

    Args:
        layout: Nome do layout identificado pelo `.REF` (ver `identificacao.identificar`), ou
            `None` se não reconhecido.

    Returns:
        Uma tupla `(situacao, selecionado, motivo)`: `pendente`/selecionável quando o layout é
        conhecido e ativo; `ignorado`/não selecionável (com o motivo) quando o layout não foi
        reconhecido, não tem rotina de importação, ou está inativo.
    """
    if layout is None:
        return SituacaoArquivoSiape.IGNORADO, False, 'Layout não reconhecido.'
    if layout not in LAYOUTS:
        return SituacaoArquivoSiape.IGNORADO, False, 'Layout reconhecido, mas sem rotina de importação.'
    if not LAYOUTS[layout].ativo:
        return SituacaoArquivoSiape.IGNORADO, False, LAYOUTS[layout].motivo_inativo
    return SituacaoArquivoSiape.PENDENTE, True, ''


def _registrar_arquivo(importacao: ImportacaoSiape, base: str, par: dict[str, bytes], refs: dict[str, str]) -> None:
    """Identifica o layout do par REF/TXT, grava os dois arquivos no storage e cria o
    `ImportacaoSiapeArquivo` correspondente, já com a situação inicial apropriada.

    Args:
        importacao: Importação dona do arquivo (define a pasta de destino no storage).
        base: Nome base do par (sem extensão), usado para nomear os arquivos gravados.
        par: `{'REF': conteúdo, 'TXT': conteúdo}` do par a registrar.
        refs: Nome do layout -> conteúdo do `.REF` de referência, para a identificação.
    """
    identificacao = identificar(par['REF'].decode('utf-8', 'replace'), refs)
    situacao, selecionado, motivo = _situacao_inicial(identificacao.layout)
    ImportacaoSiapeArquivo.objects.create(
        importacao=importacao,
        nome_ref=default_storage.save(f'{importacao.pasta}/{base}.REF', ContentFile(par['REF'])),
        nome_txt=default_storage.save(f'{importacao.pasta}/{base}.TXT', ContentFile(par['TXT'])),
        layout=identificacao.layout,
        diagnostico=identificacao.diagnostico,
        selecionado=selecionado,
        situacao=situacao,
        motivo=motivo,
        total_linhas=len(par['TXT'].splitlines()),
    )
