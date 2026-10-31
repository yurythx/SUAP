"""Composição das partes do PDF do processo (``gerar_partes_processo_pdf``), sem banco."""

from __future__ import annotations

from types import SimpleNamespace

from processo_eletronico.utils import gerar_partes_processo_pdf


def _pdf(conteudo: bytes) -> SimpleNamespace:
    """Objeto cujo ``get_pdf`` devolve ``conteudo``, ignorando as opções de impressão."""
    return SimpleNamespace(get_pdf=lambda **_: conteudo)


def test_partes_na_ordem_sem_removidos_nem_requerimento_repetido() -> None:
    removidos: list = []
    processo_do_documento = SimpleNamespace(get_documentos_removidos=lambda: removidos)
    requerimento = SimpleNamespace(id=1, pode_ler=lambda **_: True, documentodigitalizadoprocesso_set=None)

    tramite = _pdf(b'despacho')  # sem ``documento``: é um despacho
    processo_minuta = SimpleNamespace(documento=None, eh_minuta=True, minuta=_pdf(b'minuta'))
    texto = SimpleNamespace(documento=_pdf(b'texto'), processo=processo_do_documento)
    digitalizado_doc = SimpleNamespace(id=2, documentodigitalizadoprocesso_set=None, get_pdf=lambda **_: b'digitalizado')
    digitalizado = SimpleNamespace(documento=digitalizado_doc, processo=processo_do_documento)
    removido = SimpleNamespace(documento=_pdf(b'removido'), processo=processo_do_documento)
    removidos.append(removido)
    requerimento_no_processo = SimpleNamespace(documento=requerimento, processo=processo_do_documento)

    processo = SimpleNamespace(
        get_capa_pdf=lambda: b'capa',
        has_requerimento_processo=lambda: True,
        get_requerimento_processo=lambda: SimpleNamespace(documento=requerimento),
        get_requerimento_pdf=lambda: b'requerimento',
        get_todos_documentos_processo=lambda reverse: [tramite, processo_minuta, texto, removido, requerimento_no_processo, digitalizado],
    )

    partes = gerar_partes_processo_pdf(processo, user=None, leitura_para_barramento=False)

    assert [(p['tipo_parte_processo'], p['pdf']) for p in partes] == [
        ('CAPA', b'capa'),
        ('REQUERIMENTO', b'requerimento'),
        ('DESPACHO', b'despacho'),
        ('MINUTA', b'minuta'),
        ('DOCUMENTO_TEXTO', b'texto'),
        ('DOCUMENTO_DIGITALIZADO', b'digitalizado'),
    ]
