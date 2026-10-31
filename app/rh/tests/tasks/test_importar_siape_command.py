"""Comando importar_siape (beat das 01:07) sobre o motor novo."""

import os
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from rh.importacao_siape import execucao as execucao_mod
from rh.importacao_siape.execucao import agendar_importacao
from rh.importacao_siape.preparacao import criar_importacao
from rh.models import Banco, ImportacaoSiape, SituacaoImportacaoSiape
from rh.tests.siape import zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')


@pytest.fixture
def pasta():
    # a mídia do teste já é um diretório temporário (fixture `limpar_importacoes`)
    return 'rh/arquivos_siape'


def test_comando_importa_o_zip_da_pasta_e_o_remove(pasta):
    caminho = default_storage.save(f'{pasta}/extracao.zip', ContentFile(zip_do_extrator()))

    call_command('importar_siape', pasta=pasta)

    importacao = ImportacaoSiape.objects.get()
    assert importacao.origem == 'comando'
    assert importacao.situacao in (SituacaoImportacaoSiape.CONCLUIDA, SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS)
    assert importacao.arquivos.get(layout='bancos').situacao == 'concluido'
    assert Banco.objects.filter(codigo='001').exists()
    assert not default_storage.exists(caminho)


def test_comando_sem_zip_nao_cria_importacao(pasta):
    call_command('importar_siape', pasta=pasta)

    assert not ImportacaoSiape.objects.exists()


def test_falha_de_um_zip_nao_interrompe_o_processamento_dos_demais(pasta):
    """Um zip com falha inesperada não aborta o `for` do comando: os demais da noite são processados."""
    default_storage.save(f'{pasta}/a.zip', ContentFile(zip_do_extrator()))
    default_storage.save(f'{pasta}/b.zip', ContentFile(zip_do_extrator()))
    executar_de_verdade = execucao_mod.executar_importacao

    def falha_apenas_no_primeiro(importacao, workers):
        if importacao.arquivo == 'a.zip':
            # simula o contrato de executar_importacao: grava a situação final antes de relançar.
            ImportacaoSiape.objects.filter(pk=importacao.pk).update(situacao=SituacaoImportacaoSiape.FALHOU)
            raise RuntimeError('falha simulada')
        return executar_de_verdade(importacao, workers)

    with mock.patch('rh.management.commands.importar_siape.executar_importacao', side_effect=falha_apenas_no_primeiro):
        call_command('importar_siape', pasta=pasta)

    assert not default_storage.exists(f'{pasta}/a.zip')  # falhou: o zip também é apagado
    assert not default_storage.exists(f'{pasta}/b.zip')
    importacao_b = ImportacaoSiape.objects.get(arquivo='b.zip')
    assert importacao_b.situacao in (SituacaoImportacaoSiape.CONCLUIDA, SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS)


def test_zip_invalido_na_pasta_do_extrator_sai_da_fila_sem_ser_apagado(pasta):
    """Zip ainda em cópia ou corrompido: preservado para diagnóstico, mas não é tentado de novo toda noite."""
    default_storage.save(f'{pasta}/quebrado.zip', ContentFile(b'isto nao e zip'))

    call_command('importar_siape', pasta=pasta)
    call_command('importar_siape', pasta=pasta)

    assert not default_storage.exists(f'{pasta}/quebrado.zip')
    with default_storage.open(f'{pasta}/quebrado.zip.invalido', 'rb') as preservado:
        assert preservado.read() == b'isto nao e zip'
    assert not ImportacaoSiape.objects.exists()


def test_comando_executa_agendadas_pela_tela_antes_dos_zips(pasta):
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    bancos = importacao.arquivos.get(layout='bancos')
    agendar_importacao(importacao, [bancos.pk])

    call_command('importar_siape', pasta=pasta)

    importacao.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
    assert importacao.arquivos.get(layout='bancos').situacao == 'concluido'
    assert Banco.objects.filter(codigo='001').exists()
    assert importacao.arquivos.get(layout='estado_civil').situacao == 'ignorado'
