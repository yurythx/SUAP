# ruff: noqa: UP032
"""SIAPE: agendamento, cancelamento, interrupção e consulta de ocorrências sem importar dados externos."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela
from rh.tests.factories import ImportacaoSiapeArquivoFactory, ImportacaoSiapeFactory, ImportacaoSiapeOcorrenciaFactory

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_agendar_cancelar_importacao(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import ImportacaoSiape, SituacaoImportacaoSiape

    importacao = ImportacaoSiapeFactory()
    arquivo = ImportacaoSiapeArquivoFactory(importacao=importacao)
    ocorrencia = ImportacaoSiapeOcorrenciaFactory(arquivo=arquivo)
    tela.ir('/rh/importacao_siape/').ver_titulo('Importação SIAPE')
    tela.ir('/rh/importacao_siape/{}/'.format(importacao.pk))
    tela.clicar_botao('Agendar selecionados')
    tela.sucesso('Importação agendada para a execução noturna (01:07).')
    assert ImportacaoSiape.objects.filter(pk=importacao.pk, situacao=SituacaoImportacaoSiape.AGENDADA).exists()
    tela.clicar_botao('Cancelar agendamento')
    tela.sucesso('Agendamento cancelado.')
    assert ImportacaoSiape.objects.filter(pk=importacao.pk, situacao=SituacaoImportacaoSiape.IDENTIFICADA).exists()
    resposta = tela.buscar('/rh/importacao_siape/{}/arquivo/{}/ocorrencias/'.format(importacao.pk, arquivo.pk))
    assert resposta.status == 200
    assert ocorrencia.mensagem in resposta.text()
    assert arquivo.ocorrencias.filter(pk=ocorrencia.pk).exists()


def test_interromper_importacao(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    from rh.models import ImportacaoSiape, SituacaoImportacaoSiape

    importacao = ImportacaoSiapeFactory(situacao=SituacaoImportacaoSiape.EXECUTANDO)
    tela.ir('/rh/importacao_siape/{}/'.format(importacao.pk))
    tela.clicar_botao('Marcar como interrompida')
    tela.sucesso('Importação marcada como interrompida.')
    assert ImportacaoSiape.objects.filter(pk=importacao.pk, situacao=SituacaoImportacaoSiape.FALHOU, fim__isnull=False).exists()


def test_redireciona_extrator_legado(logado_rh: Callable[[str], Page]) -> None:
    tela = Tela(logado_rh('sistemico'))
    resposta = tela.buscar('/rh/upload_arquivos_extrator/')
    assert resposta.status == 302
    assert resposta.headers['location'] == '/rh/importacao_siape/'
