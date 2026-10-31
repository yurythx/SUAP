"""Executa uma importação SIAPE: grafo de layouts em série ou em paralelo, com progresso e ocorrências no banco.

Também concentra as transições de situação da `ImportacaoSiape` (iniciar, agendar, cancelar o
agendamento, interromper) e a finalização (situação final, `Log` e limpeza da pasta).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Collection
from datetime import datetime
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import QuerySet

from comum.models import Configuracao, Log
from rh.importacao_siape.armazenamento import apagar_pasta
from rh.importacao_siape.agendador import Resultado, executar_etapas
from rh.importacao_siape.execucao_lotes import ExecucaoPorLotes
from rh.importacao_siape.layouts import GRUPO_TABELAS, LAYOUTS, dependencias_efetivas
from rh.importacao_siape.lotes import TAMANHO_LOTE_PADRAO
from rh.models import (
    SITUACOES_SELECIONAVEIS,
    ImportacaoSiape,
    ImportacaoSiapeArquivo,
    ImportacaoSiapeLote,
    ImportacaoSiapeOcorrencia,
    Servidor,
    SituacaoArquivoSiape,
    SituacaoImportacaoSiape,
)

if TYPE_CHECKING:
    from comum.models import User

log = logging.getLogger(__name__)

WORKERS_PADRAO = 4

# bigint fixo (crc32 de 'rh.importacao_siape') usado como chave de `pg_advisory_xact_lock`:
# serializa o trecho de `iniciar_importacao`/`agendar_importacao`/`cancelar_agendamento`/
# `encerrar_com_falha` que lê e muda a situação da importação (inclusive o "existe uma execução em
# andamento?").
CHAVE_TRAVA_IMPORTACAO = 838954910


class ImportacaoNaoIniciada(Exception):
    """A importação não pôde ser iniciada (já executada, ou outra já em execução)."""


class ImportacaoNaoAgendada(Exception):
    """A importação não pôde ser agendada (já saiu de `identificada`/`agendada`: em execução ou terminada)."""


class ImportacaoNaoCancelada(Exception):
    """O agendamento não pôde ser cancelado (a importação não estava agendada)."""


class ImportacaoNaoInterrompida(Exception):
    """A importação não pôde ser marcada como interrompida (ela não estava em execução)."""


# Para que serve: o tamanho do pool precisa ser ajustável por instalação (servidor com mais ou menos
# CPU/conexões de banco) sem deploy. A tela (via task) e o comando noturno leem daqui, e os testes
# forçam 1 para rodar em série.
def workers_configurados() -> int:
    """Quantidade de workers do pool para a importação, lida de `Configuracao` (mínimo 1).

    Devolve `WORKERS_PADRAO` quando a configuração não existe ou não é um inteiro válido.
    """
    valor = Configuracao.get_valor_por_chave('rh', 'importacao_siape_workers')
    try:
        return max(1, int(valor))
    except TypeError, ValueError:
        return WORKERS_PADRAO


# Para que serve: permite calibrar em produção, sem deploy, a partir de quantas linhas um arquivo é
# dividido em lotes paralelos (lotes grandes demais deixam workers ociosos; pequenos demais pesam
# no custo fixo de cada lote). Lido por `executar_importacao`.
def tamanho_lote_configurado() -> int:
    """Tamanho de lote para dividir arquivos grandes, lido de `Configuracao` (mínimo 1).

    Devolve `TAMANHO_LOTE_PADRAO` quando a configuração não existe ou não é um inteiro válido.
    """
    valor = Configuracao.get_valor_por_chave('rh', 'importacao_siape_tamanho_lote')
    try:
        return max(1, int(valor))
    except TypeError, ValueError:
        return TAMANHO_LOTE_PADRAO


def _arquivos_importaveis(importacao: ImportacaoSiape) -> QuerySet[ImportacaoSiapeArquivo]:
    """Arquivos da importação cujo layout está ativo (os únicos que podem ser selecionados)."""
    layouts_ativos = [nome for nome, layout in LAYOUTS.items() if layout.ativo]
    return importacao.arquivos.filter(layout__in=layouts_ativos)


MENSAGEM_SELECAO_VAZIA = 'Selecione ao menos um arquivo para importar.'


def _selecao_vazia(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> bool:
    """Se nenhum dos ids marcados é de arquivo importável (layout ativo e reconhecido).

    Sem essa checagem, a importação terminaria `concluida` sem importar nada e com o zip já apagado.
    """
    return not _arquivos_importaveis(importacao).filter(pk__in=ids_selecionados).exists()


def _gravar_selecao(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> None:
    """Marca os arquivos escolhidos como aguardando execução e os demais importáveis como ignorados.

    Usado tanto por `iniciar_importacao` quanto por `agendar_importacao`: as duas ações gravam a
    seleção do usuário da mesma forma, só a nova situação da importação muda. Ids de arquivos não
    importáveis (layout inativo ou não reconhecido) são ignorados.
    """
    importaveis = _arquivos_importaveis(importacao)
    importaveis.filter(pk__in=ids_selecionados).update(selecionado=True, situacao=SituacaoArquivoSiape.AGUARDANDO)
    importaveis.exclude(pk__in=ids_selecionados).update(selecionado=False, situacao=SituacaoArquivoSiape.IGNORADO)


def _travar() -> None:
    """Trava até o fim da transação (`pg_advisory_xact_lock`): serializa `iniciar_importacao`,
    `agendar_importacao`, `cancelar_agendamento` e `encerrar_com_falha` entre si.

    Sem isso, um `cancelar_agendamento`/`agendar_importacao` concorrente com um `iniciar_importacao`
    (o beat das 01:07 ou "Executar agora"/"Importar selecionados agora" numa outra aba) pode ler a situação antes da mudança do
    outro e escrever por cima: uma importação `executando` voltaria a `identificada`/`agendada` com
    os arquivos remarcados no meio da execução, e `existe_em_execucao()` passaria a mentir. Sem a
    trava em `encerrar_com_falha`, a mesma corrida valeria para interromper/despachar concorrendo
    com um `iniciar_importacao`.
    """
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [CHAVE_TRAVA_IMPORTACAO])


def _transicionar(importacao: ImportacaoSiape, situacoes_permitidas: Collection[str], nova_situacao: str, erro: Exception, **campos: object) -> None:
    """Atualização condicional da situação: só aplica se `importacao` ainda estiver numa das `situacoes_permitidas` **no banco**.

    Chamada sempre dentro do mesmo `transaction.atomic()` que já tomou `_travar()` — a trava evita
    a corrida na prática, mas o `filter(...).update(...)` é a garantia real (não confia no objeto
    Python em mãos, que pode estar com a situação velha): 0 linhas afetadas significa que a
    situação não era mais a esperada, e `erro` é levantado antes de qualquer arquivo ser tocado.
    """
    linhas = ImportacaoSiape.objects.filter(pk=importacao.pk, situacao__in=situacoes_permitidas).update(situacao=nova_situacao, **campos)
    if not linhas:
        raise erro
    importacao.situacao = nova_situacao
    for campo, valor in campos.items():
        setattr(importacao, campo, valor)


# Para que serve: é o portão único antes de qualquer execução (tela e comando noturno passam por
# aqui). Garante, sob trava, que só uma importação rode por vez e que uma já executada não rode de
# novo; sem ele, duas execuções simultâneas gravariam os mesmos servidores ao mesmo tempo.
def iniciar_importacao(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> None:
    """Grava a seleção e marca a importação como `executando`, pronta para `executar_importacao`.

    Recusa quando a importação já saiu de uma situação selecionável ou quando já existe outra
    importação em execução (só uma por vez).

    Args:
        importacao: Importação a iniciar.
        ids_selecionados: Ids dos `ImportacaoSiapeArquivo` importáveis que o usuário marcou.

    Raises:
        ImportacaoNaoIniciada: se a importação não estiver mais numa situação selecionável, ou se
            já houver outra importação em execução.
    """
    with transaction.atomic():
        _travar()
        situacao_atual = ImportacaoSiape.objects.get(pk=importacao.pk).situacao
        if situacao_atual not in SITUACOES_SELECIONAVEIS:
            raise ImportacaoNaoIniciada('Esta importação já foi executada.')
        if _selecao_vazia(importacao, ids_selecionados):
            raise ImportacaoNaoIniciada(MENSAGEM_SELECAO_VAZIA)
        if ImportacaoSiape.existe_em_execucao():
            raise ImportacaoNaoIniciada('Já existe uma importação SIAPE em execução. Aguarde o término.')
        _transicionar(
            importacao,
            SITUACOES_SELECIONAVEIS,
            SituacaoImportacaoSiape.EXECUTANDO,
            ImportacaoNaoIniciada('Esta importação já foi executada.'),
            inicio=datetime.now(),
        )
        _gravar_selecao(importacao, ids_selecionados)


# Para que serve: importar em horário de expediente disputa banco com os usuários; agendar deixa o
# operador preparar a seleção de dia e deixar o trabalho pesado para o comando das 01:07, que só
# pega importações nesta situação.
def agendar_importacao(importacao: ImportacaoSiape, ids_selecionados: Collection[int]) -> None:
    """Grava a seleção e agenda a importação para a execução noturna, sem rodar nada agora.

    Args:
        importacao: Importação a agendar.
        ids_selecionados: Ids dos `ImportacaoSiapeArquivo` importáveis que o usuário marcou.

    Raises:
        ImportacaoNaoAgendada: se a importação não estiver mais numa situação selecionável.
    """
    with transaction.atomic():
        _travar()
        situacao_atual = ImportacaoSiape.objects.get(pk=importacao.pk).situacao
        if situacao_atual not in SITUACOES_SELECIONAVEIS:
            raise ImportacaoNaoAgendada('Esta importação já foi executada.')
        if _selecao_vazia(importacao, ids_selecionados):
            raise ImportacaoNaoAgendada(MENSAGEM_SELECAO_VAZIA)
        _transicionar(
            importacao, SITUACOES_SELECIONAVEIS, SituacaoImportacaoSiape.AGENDADA, ImportacaoNaoAgendada('Esta importação já foi executada.')
        )
        _gravar_selecao(importacao, ids_selecionados)


# Para que serve: o operador pode mudar de ideia depois de agendar (arquivo errado, quer rodar
# agora, quer outra seleção). Devolve a importação à situação editável sem perder a marcação que
# ele já tinha feito.
def cancelar_agendamento(importacao: ImportacaoSiape) -> None:
    """Desfaz o agendamento: volta a `identificada` e devolve os arquivos tocados a `pendente`.

    O campo `selecionado` não é mexido: mantém a última marcação do usuário para ele ajustar e
    reagendar/executar em seguida, em vez de perder a seleção que já tinha feito.

    Args:
        importacao: Importação agendada a cancelar.

    Raises:
        ImportacaoNaoCancelada: se a importação não estiver agendada.
    """
    with transaction.atomic():
        _travar()
        situacao_atual = ImportacaoSiape.objects.get(pk=importacao.pk).situacao
        if situacao_atual != SituacaoImportacaoSiape.AGENDADA:
            raise ImportacaoNaoCancelada('Esta importação não está agendada.')
        _transicionar(
            importacao,
            (SituacaoImportacaoSiape.AGENDADA,),
            SituacaoImportacaoSiape.IDENTIFICADA,
            ImportacaoNaoCancelada('Esta importação não está agendada.'),
        )
        situacoes_tocadas = (SituacaoArquivoSiape.AGUARDANDO, SituacaoArquivoSiape.IGNORADO)
        _arquivos_importaveis(importacao).filter(situacao__in=situacoes_tocadas).update(situacao=SituacaoArquivoSiape.PENDENTE)


# Para que serve: portão único de "encerrar como falhou" usado tanto pela recuperação manual
# (`interromper_importacao`) quanto pela falha de despacho da task (`views._iniciar`). As duas
# situações têm em comum uma importação que ficou (ou nunca saiu de) `executando` e cujos
# arquivos/lotes pendentes precisam ser fechados, com `Log` e limpeza de pasta — sem isso o
# despacho falho deixava arquivos `aguardando` presos e sem `Log`, e a interrupção manual corria
# sem a trava que serializa as outras transições.
def encerrar_com_falha(importacao: ImportacaoSiape, motivo: str) -> None:
    """Encerra a importação como FALHOU: trava, transição condicional, arquivos/lotes pendentes
    fechados, `Log` e limpeza da pasta.

    Sob a mesma trava (`_travar`) e a mesma atualização condicional (`_transicionar`) usadas pelas
    demais transições: só aplica se a importação ainda estiver `executando` **no banco**. Arquivos
    `aguardando`/`executando` viram `falhou`, lotes `executando` viram `falhou` e lotes
    `aguardando` viram `pulado` (sem isso os lotes de um arquivo interrompido continuam
    aguardando/executando para sempre, e o badge da tela mostra "N · X%"/"em execução" muito
    depois de a importação ter falhado) — tudo dentro do mesmo `transaction.atomic()` da trava e
    da transição. Só depois que a transação é confirmada é que o `Log` é gravado e a pasta é
    apagada (melhor esforço, via `_apagar_pasta_best_effort`): uma falha ao apagar não pode mascarar
    o resultado real da importação nem ficar presa atrás da mesma trava que serializa outras
    transições.

    Args:
        importacao: Importação a encerrar (deve estar `executando` no banco).
        motivo: Texto gravado no `motivo` dos arquivos/lotes pendentes e no `Log`.

    Raises:
        ImportacaoNaoInterrompida: se a importação não estiver mais `executando` no banco; nesse
            caso nada é tocado (nem arquivos/lotes, nem `Log`, nem a pasta).
    """
    agora = datetime.now()
    with transaction.atomic():
        _travar()
        _transicionar(
            importacao,
            (SituacaoImportacaoSiape.EXECUTANDO,),
            SituacaoImportacaoSiape.FALHOU,
            ImportacaoNaoInterrompida('Esta importação não está em execução.'),
            fim=agora,
        )
        _falhar_arquivos_e_lotes_pendentes(importacao, motivo, agora)
    Log.objects.create(titulo='Importação de arquivos', texto=motivo, app='rh')
    _apagar_pasta_best_effort(importacao.pasta)


def _falhar_arquivos_e_lotes_pendentes(importacao: ImportacaoSiape, motivo: str, agora: datetime) -> None:
    """Marca arquivos `aguardando`/`executando` como `falhou` e lotes `executando`/`aguardando`
    como `falhou`/`pulado` (respectivamente), com o mesmo `motivo` e horário de fim.

    Extraído de `encerrar_com_falha` para fechar, numa função só, tudo que ainda estava pendente
    quando a importação foi encerrada como falha.
    """
    importacao.arquivos.filter(situacao__in=[SituacaoArquivoSiape.AGUARDANDO, SituacaoArquivoSiape.EXECUTANDO]).update(
        situacao=SituacaoArquivoSiape.FALHOU, motivo=motivo, fim=agora
    )
    lotes = ImportacaoSiapeLote.objects.filter(arquivo__importacao=importacao)
    lotes.filter(situacao=SituacaoArquivoSiape.EXECUTANDO).update(situacao=SituacaoArquivoSiape.FALHOU, motivo=motivo, fim=agora)
    lotes.filter(situacao=SituacaoArquivoSiape.AGUARDANDO).update(situacao=SituacaoArquivoSiape.PULADO, motivo=motivo, fim=agora)


# Para que serve: backend do botão "interromper" da tela de detalhe. Existe para destravar o
# sistema quando uma execução morreu no meio e deixou a importação `executando`, o que impediria
# qualquer importação nova (ver `iniciar_importacao`).
def interromper_importacao(importacao: ImportacaoSiape, usuario: User | None) -> None:
    """Recuperação manual: marca como FALHOU uma importação presa em EXECUTANDO.

    Cobre o caso em que o processo que a executava morreu (reinício do servidor, worker Celery
    derrubado) e ninguém mais vai atualizar a situação dela: sem isso, `iniciar_importacao`
    a enxerga como "em execução" para sempre e recusa qualquer importação seguinte.

    Não para um processo que ainda esteja vivo: se o `executar_importacao` que gerou essa
    importação `executando` só estava lento e mais tarde termina de verdade, o `_finalizar` dele
    roda incondicionalmente e sobrescreve o `falhou` gravado aqui com a situação final de verdade
    — e a pasta que ele tentar apagar no fim já não existirá mais. Monta o motivo e delega a
    `encerrar_com_falha`: trava (`_travar`) e transição condicional (`_transicionar`), com a
    checagem de situação feita no banco, não no objeto recebido.

    Args:
        importacao: Importação presa em execução a interromper.
        usuario: Usuário que pediu a interrupção (registrado no motivo); `None` quando desconhecido.

    Raises:
        ImportacaoNaoInterrompida: se a importação não estiver com situação `executando` no banco.
    """
    nome = usuario.username if usuario else 'desconhecido'
    motivo = f'Importação marcada como interrompida por {nome}.'
    encerrar_com_falha(importacao, motivo)


# Para que serve: é o motor chamado depois de `iniciar_importacao`, pela task da tela e pelo
# comando noturno. Existe para que os dois caminhos rodem exatamente a mesma coisa: grafo de
# layouts (em série ou em paralelo), situação final coerente (inclusive arquivos/lotes fechados em
# caso de falha) e pasta limpa ao fim.
def executar_importacao(importacao: ImportacaoSiape, workers: int) -> ImportacaoSiape:
    """Executa a importação já iniciada: monta o grafo de layouts selecionados e roda no `agendador`.

    Depois do grafo, roda o pós-processamento (`_pos_processar`) e grava a situação final:
    `concluida`, ou `concluida_com_falhas` se algum layout falhou, foi pulado ou gerou ocorrência
    `error`/`critical`. A falha de um layout não levanta exceção: fica no `Resultado`.

    Todo o corpo — desde a montagem do grafo (`por_layout`/`dependencias`) até o pós-processamento
    — roda dentro do `try`: qualquer exceção (inclusive um ciclo no grafo de dependências ou um
    erro ao montar `ExecucaoPorLotes`, não só as do agendador) sempre finaliza a importação sozinha
    (`_finalizar`: situação `falhou` + `Log`), fechando antes, via
    `_falhar_arquivos_e_lotes_pendentes`, os arquivos/lotes que ainda estavam `aguardando`/
    `executando` (sem isso, uma exceção antes do grafo chegar a rodar deixava arquivos presos sob
    uma importação já `falhou`), e apaga a pasta dela no storage no `finally` — nunca deixando a
    importação presa em `executando`. Esse é um caminho de finalização diferente do de
    `encerrar_com_falha`: aqui é a própria execução que se encerra ao capturar a exceção; lá é
    quem está do lado de fora (interrupção manual, falha de despacho da task) que fecha uma
    importação presa em `executando`.

    Args:
        importacao: Importação com os arquivos já selecionados (por `iniciar_importacao`).
        workers: Tamanho do pool de threads passado ao agendador (`workers <= 1` roda em série).

    Returns:
        A própria `importacao`, com a situação e o horário de fim atualizados.

    Raises:
        Exception: qualquer exceção que escape da montagem do grafo, do agendador (ex.:
            `ValueError` de ciclo, erro num `ao_pular`), do pós-processamento ou do cálculo da
            situação final, após marcar a importação como `falhou`, fechar arquivos/lotes
            pendentes e registrar o `Log` do erro.
    """
    try:
        por_layout: dict[str, list[ImportacaoSiapeArquivo]] = defaultdict(list)
        for arquivo in importacao.arquivos.filter(selecionado=True).exclude(layout=None):
            por_layout[arquivo.layout].append(arquivo)
        dependencias = {nome: dependencias_efetivas(nome, por_layout.keys()) for nome in por_layout}
        _garantir_nivel_de_log()
        lotes = ExecucaoPorLotes(por_layout, workers, tamanho_lote_configurado())
        resultado = executar_etapas(dependencias, lotes.expandir, workers, ao_pular=lotes.ao_pular, ao_finalizar=lotes.ao_finalizar)
        _pos_processar(resultado)
        _finalizar(importacao, _situacao_final(importacao, resultado), _resumo(importacao, resultado))
    except Exception as erro:
        motivo = _resumo_falha(importacao, erro)
        # sem isso, uma exceção antes do grafo rodar (ex.: ciclo de dependências) deixava
        # arquivos/lotes selecionados presos em aguardando/executando sob uma importação já falhou.
        _falhar_arquivos_e_lotes_pendentes(importacao, motivo, datetime.now())
        _finalizar(importacao, SituacaoImportacaoSiape.FALHOU, motivo)
        raise
    finally:
        _apagar_pasta_best_effort(importacao.pasta)
    return importacao


def _garantir_nivel_de_log(logger: str = 'rh.importador') -> None:
    """Rebaixa o nível do logger do importador para WARNING quando ele está acima disso (ERROR ou
    CRITICAL), para que os avisos cheguem aos handlers de `CapturaOcorrencias`.

    Chamado uma vez, na thread principal, antes do grafo começar, e nunca restaurado depois:
    threads do pool não devem disputar o nível do logger entre si (ver
    `progresso.capturando_ocorrencias`).
    """
    alvo = logging.getLogger(logger)
    if alvo.getEffectiveLevel() > logging.WARNING:
        alvo.setLevel(logging.WARNING)


def _finalizar(importacao: ImportacaoSiape, situacao: str, texto: str) -> None:
    """Grava a situação final e o horário de fim da importação e registra o `Log` do resultado."""
    _atualizar(importacao, situacao=situacao, fim=datetime.now())
    Log.objects.create(titulo='Importação de arquivos', texto=texto, app='rh')


def _apagar_pasta_best_effort(pasta: str) -> None:
    """Apaga a pasta da importação sem propagar erro: só registra no log em caso de falha.

    Chamado no `finally` de `executar_importacao` e por `encerrar_com_falha` (depois que a
    transação da transição é confirmada e o `Log` é gravado): uma falha ao apagar não pode
    mascarar o resultado real da importação.
    """
    try:
        apagar_pasta(pasta)
    except Exception:
        log.exception('Falha ao apagar a pasta da importação SIAPE: %s', pasta)


def _atualizar(obj: ImportacaoSiape, **campos: object) -> None:
    """Atualiza os campos no objeto em memória e faz o `UPDATE` correspondente no banco."""
    for campo, valor in campos.items():
        setattr(obj, campo, valor)
    type(obj).objects.filter(pk=obj.pk).update(**campos)


def _pos_processar(resultado: Resultado) -> None:
    """Pós-processamento após o grafo, rodado mesmo que algum layout tenha falhado.

    Quando `executar_save_pos_importacao` está configurado e algum layout fora das tabelas (núcleo do
    servidor ou históricos) foi concluído, re-salva os servidores ativos (o mesmo passo final de
    `comum.importador.Importador._process`, que dispara os `save()`/signals que dependem dos dados
    recém-importados). Uma importação só de tabelas (ex.: `bancos` pela tela, em pleno expediente)
    não traz dado de servidor, e re-salvar todos eles ali seria só carga. Além disso, e sempre,
    invalida o cache `data_ultima_importacao_siape` — isso o `_process` antigo não fazia.
    """
    trouxe_dados_de_servidor = any(LAYOUTS[nome].grupo != GRUPO_TABELAS for nome in resultado.concluidos)
    if trouxe_dados_de_servidor and Configuracao.get_valor_por_chave('rh', 'executar_save_pos_importacao'):
        for servidor in Servidor.objects.ativos().all():
            servidor.save()
    cache.delete('data_ultima_importacao_siape')


def _situacao_final(importacao: ImportacaoSiape, resultado: Resultado) -> str:
    """Decide a situação final da importação: `concluida_com_falhas` se algum layout falhou, foi
    pulado ou gerou ocorrência de nível `error`/`critical`; `concluida` caso contrário.
    """
    houve_erro = ImportacaoSiapeOcorrencia.objects.filter(arquivo__importacao=importacao, nivel__in=['error', 'critical']).exists()
    if resultado.falhos or resultado.pulados or houve_erro:
        return SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS
    return SituacaoImportacaoSiape.CONCLUIDA


def _resumo(importacao: ImportacaoSiape, resultado: Resultado) -> str:
    """Monta o texto do `Log` de uma importação concluída, com os layouts por desfecho."""
    partes = [f'Importação SIAPE #{importacao.pk} ({importacao.arquivo}).']
    if resultado.concluidos:
        partes.append('Importados: ' + ', '.join(sorted(resultado.concluidos)) + '.')
    if resultado.falhos:
        partes.append('Falharam: ' + ', '.join(sorted(resultado.falhos)) + '.')
    if resultado.pulados:
        partes.append('Pulados: ' + ', '.join(sorted(resultado.pulados)) + '.')
    return ' '.join(partes)


def _resumo_falha(importacao: ImportacaoSiape, erro: BaseException) -> str:
    """Monta o texto do `Log` de uma importação interrompida por exceção não tratada."""
    return f'Importação SIAPE #{importacao.pk} ({importacao.arquivo}) falhou: {erro}'
