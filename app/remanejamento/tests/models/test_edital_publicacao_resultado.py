"""Regras de publicação dos resultados do edital com o cronograma incompleto.

As datas do resultado parcial, do fim dos recursos e da homologação são opcionais
(``null=True``): um edital sem elas não pode publicar o resultado, e a tela de
gerenciamento do edital não pode quebrar ao consultar a regra (Sentry SUAP-WNW).
"""

from __future__ import annotations

import datetime

from documento_eletronico.models import DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory
from remanejamento.tests.factories import EditalFactory

ONTEM = datetime.datetime.now() - datetime.timedelta(days=1)
AMANHA = datetime.datetime.now() + datetime.timedelta(days=1)


def _documento(status: int) -> DocumentoTexto:
    return DocumentoTextoFactory.build(status=status, usuario_criacao=None)


def test_resultado_parcial_sem_data_e_sem_documento_nao_pode_ser_publicado() -> None:
    edital = EditalFactory.build(data_resultado_parcial=None)

    assert edital.pode_publicar_resultado_parcial() is False


def test_resultado_parcial_sem_documento_pode_ser_publicado_apos_a_data_prevista() -> None:
    edital = EditalFactory.build(data_resultado_parcial=ONTEM)

    assert edital.pode_publicar_resultado_parcial() is True


def test_resultado_parcial_com_documento_pendente_sem_fim_dos_recursos_nao_pode_ser_publicado() -> None:
    documento = _documento(DocumentoStatus.STATUS_RASCUNHO)
    edital = EditalFactory.build(data_resultado_parcial=ONTEM, resultado_parcial_documentotexto=documento, fim_recursos=None)

    assert edital.pode_publicar_resultado_parcial() is False


def test_resultado_parcial_com_documento_pendente_pode_ser_publicado_ate_o_fim_dos_recursos() -> None:
    documento = _documento(DocumentoStatus.STATUS_RASCUNHO)
    edital = EditalFactory.build(data_resultado_parcial=ONTEM, resultado_parcial_documentotexto=documento, fim_recursos=AMANHA)

    assert edital.pode_publicar_resultado_parcial() is True


def test_resultado_final_sem_fim_dos_recursos_nao_pode_ser_publicado() -> None:
    documento = _documento(DocumentoStatus.STATUS_FINALIZADO)
    edital = EditalFactory.build(resultado_parcial_documentotexto=documento, fim_recursos=None)

    assert edital.pode_publicar_resultado_final() is False


def test_homologacao_do_resultado_final_sem_data_nao_pode_ser_publicada() -> None:
    documento = _documento(DocumentoStatus.STATUS_FINALIZADO)
    edital = EditalFactory.build(resultado_final_documentotexto=documento, data_homologacao_resultado=None)

    assert edital.pode_publicar_homologacao_resultado_final() is False
