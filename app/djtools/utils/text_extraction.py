"""
Utilitários para extração de conteúdo textual de documentos.

Este módulo fornece funções para extrair texto de:
- Arquivos PDF (usando pypdf)
- Arquivos DOCX (usando python-docx)

Pode ser usado por qualquer módulo do sistema que precise extrair texto de documentos.
"""

from __future__ import annotations

import logging
import os
from io import BytesIO

from django.core.files import File
from docx import Document
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def _sem_caracteres_nulos(texto: str) -> str:
    """Remove o caractere NUL (``\\x00``), que o PostgreSQL recusa em campos de texto."""
    return texto.replace('\x00', '')


def extrair_texto_pdf(arquivo: File) -> str | None:
    """
    Extrai texto de arquivo PDF usando pypdf.

    Args:
        arquivo (File): Arquivo PDF

    Returns:
        str: Texto extraído ou None se houver erro
    """
    with arquivo.open('rb') as file:
        content = BytesIO(file.read())
    try:
        texto = []
        leitor = PdfReader(content)
        for pagina in leitor.pages:
            conteudo_pagina = pagina.extract_text()
            if conteudo_pagina:
                texto.append(conteudo_pagina)
        return _sem_caracteres_nulos(' '.join(texto))
    except Exception as e:
        logger.error(f'Erro ao extrair texto de PDF {arquivo.name}: {e!s}')
        return None


def extrair_texto_docx(arquivo: File) -> str | None:
    """
    Extrai texto de arquivo DOCX usando python-docx.

    Args:
        arquivo (File): Arquivo

    Returns:
        str: Texto extraído ou None se houver erro
    """
    with arquivo.open('rb') as file:
        content = BytesIO(file.read())
    try:
        documento = Document(content)
        texto = []
        for paragrafo in documento.paragraphs:
            if paragrafo.text:
                texto.append(paragrafo.text)
        return _sem_caracteres_nulos('\n'.join(texto))
    except Exception as e:
        logger.error(f'Erro ao extrair texto de DOCX {arquivo.name}: {e!s}')
        return None


def extrair_texto_documento(arquivo: File, normalizar: bool = True) -> str | None:
    """
    Extrai conteúdo textual de arquivo PDF ou DOCX.

    Detecta automaticamente o tipo de arquivo pela extensão e chama
    a função apropriada de extração.

    Args:
        arquivo (File): Arquivo
        normalizar (bool): Se True, normaliza espaços e quebras de linha

    Returns:
        str: Texto extraído ou None se não conseguir extrair

    Raises:
        FileNotFoundError: Se o arquivo não existir
        ValueError: Se a extensão não for suportada
    """
    arquivo_path = arquivo.name or ''

    extensao = os.path.splitext(arquivo_path)[1].lower()

    conteudo = None
    if extensao == '.pdf':
        conteudo = extrair_texto_pdf(arquivo)
    elif extensao in ('.docx', '.doc'):
        conteudo = extrair_texto_docx(arquivo)
    else:
        logger.error(f'Extensão não suportada: {extensao}')
        raise ValueError(f'Extensão não suportada: {extensao}. Use .pdf, .docx ou .doc')

    # Normaliza espaços e quebras de linha se solicitado
    if conteudo and normalizar:
        conteudo = ' '.join(conteudo.split())

    return conteudo
