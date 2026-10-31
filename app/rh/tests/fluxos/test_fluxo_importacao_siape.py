"""Fluxo da importação SIAPE: zip do extrator → identificação → seleção → execução."""

import gzip
import io
import logging
import os
import zipfile
from unittest import mock

import psycopg
import pytest
from django.core.files.storage import default_storage
from django.db import OperationalError
from django.db.models.signals import post_save

from comum.models import Configuracao, Log
from rh.importacao_siape.execucao import (
    ImportacaoNaoAgendada,
    ImportacaoNaoCancelada,
    ImportacaoNaoIniciada,
    ImportacaoNaoInterrompida,
    agendar_importacao,
    cancelar_agendamento,
    executar_importacao,
    iniciar_importacao,
    interromper_importacao,
)
from rh.importacao_siape import preparacao
from rh.importacao_siape.armazenamento import arquivos_da_pasta
from rh.importacao_siape.execucao_lotes import TENTATIVAS_POR_DEADLOCK
from rh.importacao_siape.identificacao import PASTA_REFS
from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao
from rh.importador import ImportadorSIAPE
from rh.models import (
    Banco,
    CargoEmprego,
    ImportacaoSiape,
    ImportacaoSiapeArquivo,
    ImportacaoSiapeOcorrencia,
    SituacaoArquivoSiape,
    Servidor,
    SituacaoImportacaoSiape,
)
from rh.tests.factories import ServidorFactory
from rh.tests.siape import ARQUIVOS_SIAPE, zip_do_extrator

pytestmark = pytest.mark.usefixtures('importacao_serial', 'limpar_importacoes')

CARGOS_DO_ARQUIVO = {'707001', '559027'}  # CAREMPR.TXT: duas linhas, dois códigos


@pytest.fixture
def lotes_de_uma_linha():
    """Tamanho de lote 1: o `cargo_emprego` de teste (2 linhas, 2 códigos) vira 2 lotes."""
    Configuracao.objects.update_or_create(app='rh', chave='importacao_siape_tamanho_lote', defaults={'valor': '1'})
    Configuracao.clear_cache()
    yield
    Configuracao.clear_cache()


def _zip_com_grupo_cargo_emprego_ilegivel() -> bytes:
    """Zip de teste com o TXT de `grupo_cargo_emprego` (GRCAREM) corrompido: bytes que não
    decodificam como UTF-8, reproduzindo uma falha de `get_itens` durante a expansão do layout
    (não uma exceção de uma rotina `importar_*`, como os demais testes de falha).
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_:
        for nome in sorted(os.listdir(ARQUIVOS_SIAPE)):
            if not nome.endswith(('.TXT', '.REF')):
                continue
            if nome == 'GRCAREM.TXT':
                conteudo = b'\xff\xfe\xfd'
            else:
                with open(os.path.join(ARQUIVOS_SIAPE, nome), encoding='latin-1') as fh:
                    conteudo = fh.read().encode('utf-8')
            zip_.writestr(f'{nome}.gz', gzip.compress(conteudo))
    return buffer.getvalue()


def _zip_com_servidor1_vazio() -> bytes:
    """Zip de teste + um `servidor1` sem linhas: dependente de `cargo_emprego` para ver o pulo."""
    buffer = io.BytesIO(zip_do_extrator())
    with open(os.path.join(PASTA_REFS, 'servidor1.REF'), 'rb') as ref, zipfile.ZipFile(buffer, 'a') as zip_:
        zip_.writestr('SERVIDOR1.REF', ref.read())
        zip_.writestr('SERVIDOR1.TXT', b'')
    return buffer.getvalue()


def test_zip_do_extrator_vira_arquivos_identificados():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    bancos = importacao.arquivos.get(layout='bancos')
    parente = importacao.arquivos.get(nome_ref__endswith='PARENTE.REF')
    assert bancos.selecionado
    assert bancos.situacao == SituacaoArquivoSiape.PENDENTE
    assert bancos.total_linhas > 0
    assert parente.layout is None
    assert not parente.selecionado
    assert parente.situacao == SituacaoArquivoSiape.IGNORADO
    assert 'Layout mais próximo' in parente.diagnostico


def test_zip_invalido_nao_cria_importacao():
    with pytest.raises(ArquivoExtratorInvalido):
        criar_importacao('extracao.zip', b'isto nao e zip', origem='tela')

    assert not ImportacaoSiape.objects.exists()


def test_membro_gz_corrompido_no_zip_do_extrator_nao_cria_importacao():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_:
        zip_.writestr('X.REF.gz', b'nao e gzip')

    with pytest.raises(ArquivoExtratorInvalido, match='corrompido'):
        criar_importacao('extracao.zip', buffer.getvalue(), origem='tela')

    assert not ImportacaoSiape.objects.exists()


def test_falha_ao_registrar_um_par_apaga_os_arquivos_ja_gravados():
    registrar_de_verdade = preparacao._registrar_arquivo
    chamadas = []

    def falha_no_terceiro(*args, **kwargs):
        chamadas.append(1)
        if len(chamadas) == 3:
            raise RuntimeError('falha simulada ao gravar')
        return registrar_de_verdade(*args, **kwargs)

    with mock.patch.object(preparacao, '_registrar_arquivo', side_effect=falha_no_terceiro), pytest.raises(RuntimeError):
        criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    assert not ImportacaoSiape.objects.exists()
    assert arquivos_da_pasta(f'{preparacao.PASTA_IMPORTACOES}/1') == []


def _iniciar(importacao, *layouts):
    ids = importacao.arquivos.filter(layout__in=layouts).values_list('pk', flat=True)
    iniciar_importacao(importacao, ids)
    return executar_importacao(importacao, workers=1)


def test_importacao_parcial_so_processa_o_que_foi_marcado():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    _iniciar(importacao, 'bancos')

    importacao.refresh_from_db()
    bancos = importacao.arquivos.get(layout='bancos')
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
    assert bancos.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert bancos.processadas == bancos.total_linhas
    assert Banco.objects.filter(codigo='001').exists()
    assert importacao.arquivos.get(layout='estado_civil').situacao == SituacaoArquivoSiape.IGNORADO
    assert Log.objects.filter(app='rh', titulo='Importação de arquivos', texto__contains='bancos').exists()
    assert importacao.pasta
    assert not default_storage.exists(importacao.pasta)


def test_selecao_sem_arquivo_importavel_recusa_importar_e_agendar():
    """Sem nada marcado, a importação terminaria "concluída" sem importar nada e com o zip apagado."""
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    so_nao_reconhecido = importacao.arquivos.filter(layout=None).values_list('pk', flat=True)

    with pytest.raises(ImportacaoNaoIniciada, match='ao menos um arquivo'):
        iniciar_importacao(importacao, [])
    with pytest.raises(ImportacaoNaoAgendada, match='ao menos um arquivo'):
        agendar_importacao(importacao, so_nao_reconhecido)

    importacao.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.IDENTIFICADA
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.PENDENTE
    assert arquivos_da_pasta(importacao.pasta)


@pytest.mark.usefixtures('sync_permissions')
def test_save_pos_importacao_so_roda_quando_o_nucleo_do_servidor_foi_importado():
    """Importação só de tabelas (ex.: `bancos` pela tela, em horário de expediente) não re-salva os servidores ativos."""
    Configuracao.objects.update_or_create(app='rh', chave='executar_save_pos_importacao', defaults={'valor': 'True'})
    Configuracao.clear_cache()
    ServidorFactory()
    salvos = []

    def contar(sender, instance, **kwargs):
        salvos.append(instance.pk)

    post_save.connect(contar, sender=Servidor, dispatch_uid='contar_saves_pos_importacao')
    try:
        _iniciar(criar_importacao('tabelas.zip', zip_do_extrator(), origem='tela'), 'bancos')
        assert salvos == []

        completa = criar_importacao('completa.zip', _zip_com_servidor1_vazio(), origem='tela')
        _iniciar(completa, *completa.arquivos.exclude(layout=None).values_list('layout', flat=True))
        assert completa.arquivos.get(layout='servidor1').situacao == SituacaoArquivoSiape.CONCLUIDO
        assert salvos
    finally:
        post_save.disconnect(sender=Servidor, dispatch_uid='contar_saves_pos_importacao')
        Configuracao.clear_cache()


def test_falha_ao_montar_o_grafo_de_dependencias_encerra_como_falhou_e_limpa_a_pasta():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    ids = importacao.arquivos.filter(layout='bancos').values_list('pk', flat=True)
    iniciar_importacao(importacao, ids)

    with (
        mock.patch('rh.importacao_siape.execucao.dependencias_efetivas', side_effect=RuntimeError('grafo quebrado')),
        pytest.raises(RuntimeError, match='grafo quebrado'),
    ):
        executar_importacao(importacao, workers=1)

    importacao.refresh_from_db()
    bancos = importacao.arquivos.get(layout='bancos')
    assert importacao.situacao == SituacaoImportacaoSiape.FALHOU
    # a exceção estourou antes do grafo rodar: sem `_falhar_arquivos_e_lotes_pendentes` o arquivo
    # selecionado ficaria preso em `aguardando` para sempre sob uma importação já `falhou`.
    assert bancos.situacao == SituacaoArquivoSiape.FALHOU
    assert not importacao.arquivos.filter(situacao=SituacaoArquivoSiape.AGUARDANDO).exists()
    assert arquivos_da_pasta(importacao.pasta) == []
    assert Log.objects.filter(app='rh', titulo='Importação de arquivos', texto__contains='grafo quebrado').exists()


def test_interromper_importacao_ja_concluida_recusa_e_nao_toca_em_nada():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    _iniciar(importacao, 'bancos')
    importacao.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
    fim_antes = importacao.fim

    with pytest.raises(ImportacaoNaoInterrompida):
        interromper_importacao(importacao, usuario=None)

    importacao.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
    assert importacao.fim == fim_antes


def test_falha_de_um_layout_pula_os_dependentes_e_nao_para_os_demais():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    with mock.patch('rh.importador.ImportadorSIAPE.importar_grupo_cargo_emprego', side_effect=RuntimeError('layout quebrado')):
        _iniciar(importacao, 'grupo_cargo_emprego', 'cargo_emprego', 'bancos')

    importacao.refresh_from_db()
    grupo = importacao.arquivos.get(layout='grupo_cargo_emprego')
    cargo = importacao.arquivos.get(layout='cargo_emprego')
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS
    assert grupo.situacao == SituacaoArquivoSiape.FALHOU
    assert 'layout quebrado' in grupo.motivo
    assert cargo.situacao == SituacaoArquivoSiape.PULADO
    assert 'grupo_cargo_emprego' in cargo.motivo
    assert not CargoEmprego.objects.exists()
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.CONCLUIDO
    assert arquivos_da_pasta(importacao.pasta) == []  # com falhas: arquivos apagados também


def test_falha_ao_expandir_arquivo_ilegivel_pula_dependentes_e_conclui_com_falhas():
    importacao = criar_importacao('extracao.zip', _zip_com_grupo_cargo_emprego_ilegivel(), origem='tela')

    _iniciar(importacao, 'grupo_cargo_emprego', 'cargo_emprego', 'bancos')

    importacao.refresh_from_db()
    grupo = importacao.arquivos.get(layout='grupo_cargo_emprego')
    cargo = importacao.arquivos.get(layout='cargo_emprego')
    assert grupo.situacao == SituacaoArquivoSiape.FALHOU
    assert 'UnicodeDecodeError' in grupo.motivo
    assert cargo.situacao == SituacaoArquivoSiape.PULADO
    assert 'grupo_cargo_emprego' in cargo.motivo
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.CONCLUIDO
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS


def test_warning_do_importador_vira_ocorrencia_e_outra_importacao_e_recusada(logging_habilitado):
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    def importar_bancos_com_aviso(self, itens):
        import logging

        for indice, _ in enumerate(itens, start=1):
            if indice == 1:
                logging.getLogger('rh.importador').warning('banco sem sigla')

    with mock.patch('rh.importador.ImportadorSIAPE.importar_bancos', importar_bancos_com_aviso):
        ids = importacao.arquivos.filter(layout='bancos').values_list('pk', flat=True)
        iniciar_importacao(importacao, ids)
        outra = criar_importacao('outra.zip', zip_do_extrator(), origem='tela')
        with pytest.raises(ImportacaoNaoIniciada, match='em execução'):
            iniciar_importacao(outra, outra.arquivos.filter(layout='bancos').values_list('pk', flat=True))
        executar_importacao(importacao, workers=1)

    ocorrencia = ImportacaoSiapeOcorrencia.objects.get(arquivo__importacao=importacao)
    assert (ocorrencia.nivel, ocorrencia.linha, ocorrencia.mensagem) == ('warning', 1, 'banco sem sigla')
    assert (ocorrencia.arquivo.falhas, ocorrencia.arquivo.avisos) == (0, 1)


def test_cancelar_e_agendar_recusam_importacao_em_execucao_sem_tocar_nos_arquivos():
    """Trava contra corrida: `cancelar_agendamento`/`agendar_importacao` não podem derrubar uma

    importação que já está `executando` (beat da noite ou "Executar agora" numa outra aba
    correndo ao mesmo tempo) — nem a situação nem os arquivos podem ser tocados nesse caso.
    """
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    bancos = importacao.arquivos.get(layout='bancos')
    ids = importacao.arquivos.filter(layout='bancos').values_list('pk', flat=True)
    iniciar_importacao(importacao, ids)  # importação e bancos ficam em 'executando'/'aguardando'

    with pytest.raises(ImportacaoNaoCancelada):
        cancelar_agendamento(importacao)
    with pytest.raises(ImportacaoNaoAgendada):
        agendar_importacao(importacao, ids)

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.EXECUTANDO
    assert bancos.situacao == SituacaoArquivoSiape.AGUARDANDO
    assert bancos.selecionado


@pytest.mark.usefixtures('lotes_de_uma_linha')
def test_layout_grande_e_dividido_em_lotes_com_o_mesmo_resultado():
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')

    _iniciar(importacao, 'grupo_cargo_emprego', 'cargo_emprego')

    cargo = importacao.arquivos.get(layout='cargo_emprego')
    lotes = list(cargo.lotes.all())
    assert len(lotes) > 1
    assert {lote.situacao for lote in lotes} == {SituacaoArquivoSiape.CONCLUIDO}
    assert sum(lote.total_linhas for lote in lotes) == cargo.total_linhas
    assert cargo.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert cargo.processadas == cargo.total_linhas
    assert set(CargoEmprego.objects.values_list('codigo', flat=True)) == CARGOS_DO_ARQUIVO
    # layout sem partição (grupo_cargo_emprego) nunca é dividido
    assert importacao.arquivos.get(layout='grupo_cargo_emprego').lotes.count() == 1


@pytest.mark.usefixtures('lotes_de_uma_linha')
def test_falha_num_lote_falha_o_arquivo_sem_parar_os_outros_lotes_e_pula_o_dependente(logging_habilitado):
    importacao = criar_importacao('extracao.zip', _zip_com_servidor1_vazio(), origem='tela')
    importar_cargo_emprego = ImportadorSIAPE.importar_cargo_emprego

    def falhar_no_cargo_559(self, itens):
        if any(item['GR-IDEN-CARGO-EMPREGO'] == '559027' for item in itens):
            logging.getLogger('rh.importador').warning('cargo com problema')
            raise RuntimeError('cargo quebrado')
        importar_cargo_emprego(self, itens)

    with mock.patch.object(ImportadorSIAPE, 'importar_cargo_emprego', falhar_no_cargo_559):
        _iniciar(importacao, 'grupo_cargo_emprego', 'cargo_emprego', 'servidor1')

    cargo = importacao.arquivos.get(layout='cargo_emprego')
    falho = cargo.lotes.get(situacao=SituacaoArquivoSiape.FALHOU)
    assert 'cargo quebrado' in falho.motivo
    assert set(cargo.lotes.exclude(pk=falho.pk).values_list('situacao', flat=True)) == {SituacaoArquivoSiape.CONCLUIDO}
    assert cargo.situacao == SituacaoArquivoSiape.FALHOU
    assert cargo.motivo == f'Lote {falho.numero} falhou: RuntimeError: cargo quebrado'
    assert set(CargoEmprego.objects.values_list('codigo', flat=True)) == {'707001'}
    # a linha da ocorrência é a do arquivo (559027 é a 2ª), não a posição dentro do lote
    ocorrencia = ImportacaoSiapeOcorrencia.objects.get(arquivo=cargo)
    assert (ocorrencia.linha, ocorrencia.mensagem) == (2, 'cargo com problema')
    # só a ocorrência de nível warning foi registrada (a falha do lote em si não gera ocorrência):
    # soma a avisos, não a falhas.
    assert (cargo.falhas, falho.falhas) == (0, 0)
    assert (cargo.avisos, falho.avisos) == (1, 1)
    servidor1 = importacao.arquivos.get(layout='servidor1')
    assert servidor1.situacao == SituacaoArquivoSiape.PULADO
    assert 'cargo_emprego' in servidor1.motivo


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures('lotes_de_uma_linha')
def test_workers_paralelos_isola_falha_por_layout_sem_quebrar_a_conexao_principal():
    """`workers=2` de verdade: cada layout roda numa thread do pool, com sua própria conexão.

    Precisa de `transaction=True` (banco real, sem a transação de teste envolvendo tudo): as
    threads do pool abrem conexões próprias e não enxergariam dados só commitados dentro da
    transação da thread principal.
    """
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    layouts = ['bancos', 'estado_civil', 'grupo_ocorrencia', 'ocorrencia', 'grupo_cargo_emprego', 'cargo_emprego']

    with mock.patch('rh.importador.ImportadorSIAPE.importar_grupo_ocorrencia', side_effect=RuntimeError('layout quebrado')):
        iniciar_importacao(importacao, importacao.arquivos.filter(layout__in=layouts).values_list('pk', flat=True))
        executar_importacao(importacao, workers=2)

    importacao.refresh_from_db()
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS
    grupo = importacao.arquivos.get(layout='grupo_ocorrencia')
    assert grupo.situacao == SituacaoArquivoSiape.FALHOU
    assert 'layout quebrado' in grupo.motivo
    assert importacao.arquivos.get(layout='ocorrencia').situacao == SituacaoArquivoSiape.PULADO
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.CONCLUIDO
    # o layout dividido rodou em lotes nas threads do pool
    cargo = importacao.arquivos.get(layout='cargo_emprego')
    lotes = list(cargo.lotes.all())
    assert cargo.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert len(lotes) > 1
    assert {lote.situacao for lote in lotes} == {SituacaoArquivoSiape.CONCLUIDO}
    assert all(lote.worker.startswith('importacao_siape') for lote in lotes)
    assert importacao.arquivos.get(layout='estado_civil').situacao == SituacaoArquivoSiape.CONCLUIDO
    # a conexão da thread principal segue utilizável: só as threads do pool fecham a própria.
    assert ImportacaoSiape.objects.count() >= 1


def _erro_deadlock() -> OperationalError:
    """Um `OperationalError` como o Django levanta ao embrulhar um deadlock real do Postgres."""
    erro = OperationalError('deadlock detected')
    erro.__cause__ = psycopg.errors.DeadlockDetected('deadlock detected')
    return erro


def test_lote_com_deadlock_tenta_de_novo_e_conclui_sem_dobrar_o_progresso(logging_habilitado):
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    bancos = importacao.arquivos.get(layout='bancos')
    importar_bancos = ImportadorSIAPE.importar_bancos
    chamadas = []
    capturado = {}

    def importar_bancos_com_deadlock_na_primeira(self, itens):
        chamadas.append(1)
        if len(chamadas) == 1:
            list(itens)  # percorre tudo (conta o progresso inteiro) antes de estourar o deadlock
            raise _erro_deadlock()
        importar_bancos(self, itens)

    def _capturar_processadas_durante_a_retentativa(*args, **kwargs):
        capturado['processadas'] = ImportacaoSiapeArquivo.objects.get(pk=bancos.pk).processadas

    with (
        mock.patch.object(ImportadorSIAPE, 'importar_bancos', importar_bancos_com_deadlock_na_primeira),
        mock.patch(
            'rh.importacao_siape.execucao_lotes._aguardar_antes_de_tentar_novamente',
            side_effect=_capturar_processadas_durante_a_retentativa,
        ),
    ):
        _iniciar(importacao, 'bancos')

    bancos.refresh_from_db()
    lote = bancos.lotes.get()
    assert len(chamadas) == 2
    assert lote.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert bancos.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert bancos.processadas == bancos.total_linhas
    # o progresso que a tentativa com deadlock já tinha contado foi desfeito antes de tentar de novo
    assert capturado['processadas'] == 0
    ocorrencias = ImportacaoSiapeOcorrencia.objects.filter(arquivo=bancos, nivel='warning')
    assert ocorrencias.count() == 1
    assert 'nova tentativa 1 de 2' in ocorrencias.get().mensagem


def test_lote_com_deadlock_persistente_falha_apos_esgotar_as_tentativas(logging_habilitado):
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    chamadas = []

    def importar_bancos_sempre_com_deadlock(self, itens):
        chamadas.append(1)
        raise _erro_deadlock()

    with (
        mock.patch.object(ImportadorSIAPE, 'importar_bancos', importar_bancos_sempre_com_deadlock),
        mock.patch('rh.importacao_siape.execucao_lotes._aguardar_antes_de_tentar_novamente'),
    ):
        _iniciar(importacao, 'bancos')

    importacao.refresh_from_db()
    bancos = importacao.arquivos.get(layout='bancos')
    lote = bancos.lotes.get()
    assert len(chamadas) == TENTATIVAS_POR_DEADLOCK == 3
    assert lote.situacao == SituacaoArquivoSiape.FALHOU
    assert 'DeadlockDetected' in lote.motivo
    assert bancos.situacao == SituacaoArquivoSiape.FALHOU
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS


def test_erro_que_nao_e_deadlock_nao_tenta_de_novo(logging_habilitado):
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    chamadas = []

    def importar_bancos_com_erro_comum(self, itens):
        chamadas.append(1)
        raise RuntimeError('erro qualquer, não é deadlock')

    with mock.patch.object(ImportadorSIAPE, 'importar_bancos', importar_bancos_com_erro_comum):
        _iniciar(importacao, 'bancos')

    assert len(chamadas) == 1
    assert importacao.arquivos.get(layout='bancos').situacao == SituacaoArquivoSiape.FALHOU


def test_ocorrencia_da_tentativa_perdida_nao_fica_duplicada_nem_conta_duas_vezes(logging_habilitado):
    """A tentativa que sofre o deadlock loga o mesmo aviso ('banco sem sigla', preso à linha —
    não ao número da chamada) que a retentativa vai logar de novo ao reprocessar a mesma linha:
    sem apagar a ocorrência (e desfazer o que ela tinha somado) da tentativa perdida, ela ficaria
    duplicada na tela e o `avisos` contaria a mesma coisa duas vezes.
    """
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    bancos = importacao.arquivos.get(layout='bancos')
    chamadas = []

    def importar_bancos_com_aviso_e_deadlock_na_primeira(self, itens):
        chamadas.append(1)
        for indice, _ in enumerate(itens, start=1):
            if indice == 1:
                logging.getLogger('rh.importador').warning('banco sem sigla')
        if len(chamadas) == 1:
            raise _erro_deadlock()

    with (
        mock.patch.object(ImportadorSIAPE, 'importar_bancos', importar_bancos_com_aviso_e_deadlock_na_primeira),
        mock.patch('rh.importacao_siape.execucao_lotes._aguardar_antes_de_tentar_novamente'),
    ):
        _iniciar(importacao, 'bancos')

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    lote = bancos.lotes.get()
    assert len(chamadas) == 2
    assert bancos.situacao == SituacaoArquivoSiape.CONCLUIDO
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA  # avisos não bloqueiam a conclusão
    # o aviso "de verdade" não ficou duplicado: só a cópia da tentativa que deu certo sobrou
    ocorrencias_do_aviso = ImportacaoSiapeOcorrencia.objects.filter(arquivo=bancos, mensagem='banco sem sigla')
    assert ocorrencias_do_aviso.count() == 1
    # avisos soma esse aviso deduplicado (1, só a tentativa que sobreviveu) + o próprio aviso de
    # retentativa ("Lote N: conflito de concorrência...", também nível warning e contado por
    # `_registrar_ocorrencia` como qualquer outro — item 5 do round de revisão) — esse não tem
    # cópia perdida para desfazer, é criado uma única vez por retentativa.
    assert bancos.avisos == lote.avisos == 2
    assert bancos.falhas == lote.falhas == 0
    assert ImportacaoSiapeOcorrencia.objects.filter(arquivo=bancos, nivel='warning').count() == 2


def test_erro_da_tentativa_perdida_nao_impede_a_importacao_de_concluir_sem_falhas(logging_habilitado):
    """Reproduz a segunda metade do bug relatado na revisão: um nível `error`/`critical` que
    sobrasse da tentativa perdida faria `_situacao_final` marcar a importação inteira como
    `concluida_com_falhas`, mesmo com a retentativa dando certo. Aqui o erro só acontece na
    tentativa que sofre o deadlock (não é relogado na retentativa) — precisa sumir de vez.
    """
    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    bancos = importacao.arquivos.get(layout='bancos')
    chamadas = []

    def importar_bancos_com_erro_e_deadlock_na_primeira(self, itens):
        chamadas.append(1)
        if len(chamadas) == 1:
            logging.getLogger('rh.importador').error('erro que só aconteceu na tentativa perdida')
            raise _erro_deadlock()

    with (
        mock.patch.object(ImportadorSIAPE, 'importar_bancos', importar_bancos_com_erro_e_deadlock_na_primeira),
        mock.patch('rh.importacao_siape.execucao_lotes._aguardar_antes_de_tentar_novamente'),
    ):
        _iniciar(importacao, 'bancos')

    importacao.refresh_from_db()
    bancos.refresh_from_db()
    assert len(chamadas) == 2
    assert not ImportacaoSiapeOcorrencia.objects.filter(arquivo=bancos, nivel__in=['error', 'critical']).exists()
    assert bancos.falhas == 0
    assert importacao.situacao == SituacaoImportacaoSiape.CONCLUIDA
