"""Atualização automática das bases de dados abertos na periodicidade prometida.

Percorre as bases cuja ``frequencia_atualizacao`` já venceu, re-coleta cada recurso que tem URL e
republica no CKAN. É a contrapartida operacional do que o PDA promete ao cidadão no Cronograma de
Abertura (Art. 4º, VI, b da Resolução nº 3/2017 do CGINDA).

Duas fronteiras são deliberadas:

* **Só mantém o que já está publicado.** Base nunca sincronizada não é selecionada: a primeira
  publicação é ato do gestor, passa pelas etapas do PDA e pela liberação do LAI.
* **A isenção do LAI vale só aqui.** ``RecursoDados.save()`` continua reabrindo a análise em toda
  edição humana; a rotina grava por um caminho próprio e só reabre quando o *esquema* muda, porque
  ela re-coleta a mesma URL — mesma consulta, mesma origem, apenas dados mais recentes.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.utils import timezone

from dados_abertos.enums import ResultadoAtualizacao
from dados_abertos.models import AtualizacaoBaseDados, BaseDados, RecursoDados
from dados_abertos.models.base_dados import reabrir_lai_por_edicao
from dados_abertos.services import coleta, espelho_csv
from dados_abertos.services.ckan_api_service import get_ckan_service
from dados_abertos.services.ckan_service import recurso_alterado_apos_sync, sync_dataset_with_ckan, sync_resource_with_ckan
from dados_abertos.services.periodicidade import intervalo_mais_estrito, proxima_atualizacao

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Desfecho:
    """Resultado da tentativa de atualizar uma base."""

    resultado: int
    detalhe: str = ''
    recursos_atualizados: int = 0


@dataclass(frozen=True)
class ResumoAtualizacao:
    """Contagens de uma execução da rotina."""

    verificadas: int = 0
    publicadas: int = 0
    pendentes: int = 0


def _ultima_sincronizacao(base: BaseDados, recursos: list[RecursoDados]):
    """Instante mais recente em que base ou recursos foram sincronizados com o CKAN."""
    candidatos = [dt for dt in [base.sincronizado_em, *(r.sincronizado_em for r in recursos)] if dt]
    return max(candidatos) if candidatos else None


def bases_vencidas(hoje=None) -> list[BaseDados]:
    """Bases já publicadas cuja periodicidade venceu.

    Args:
        hoje: Data de referência (``date``); o padrão é a data corrente.

    Returns:
        list[BaseDados]: Bases a atualizar, com recursos e relações já carregados.
    """
    hoje = hoje or datetime.date.today()
    candidatas = BaseDados.objects.filter(relacoes_pda__frequencia_atualizacao__isnull=False).prefetch_related('recursos', 'relacoes_pda').distinct()
    vencidas = []
    for base in candidatas:
        intervalo = intervalo_mais_estrito(rel.frequencia_atualizacao for rel in base.relacoes_pda.all())
        proxima = proxima_atualizacao(_ultima_sincronizacao(base, list(base.recursos.all())), intervalo)
        if proxima and proxima <= hoje:
            vencidas.append(base)
    return vencidas


def _conteudo_atual(recurso: RecursoDados) -> bytes | None:
    """Bytes do arquivo já gravado, ou ``None`` se não houver arquivo legível."""
    if not recurso.arquivo:
        return None
    try:
        recurso.arquivo.open('rb')
        try:
            return recurso.arquivo.read()
        finally:
            recurso.arquivo.close()
    except FileNotFoundError, OSError, ValueError:
        return None


def _gravar(recurso: RecursoDados, coletado: coleta.Coletado, colunas: list[str]) -> None:
    """Grava o conteúdo coletado sem passar pelo ``save()`` do model.

    ``update()`` não dispara ``save()`` — é assim que a rotina evita reabrir a análise do LAI. Em
    compensação também não aciona o ``auto_now``, então ``data_atualizacao`` vai explícito: é ele
    que ``_recurso_alterado_apos_sync`` compara para decidir reenviar o arquivo ao CKAN.
    """
    recurso.arquivo.save(recurso.nome_de_arquivo(), ContentFile(coletado.conteudo), save=False)
    RecursoDados.objects.filter(pk=recurso.pk).update(
        arquivo=recurso.arquivo.name,
        mimetype=coletado.content_type or recurso.mimetype,
        esquema=colunas,
        data_atualizacao=timezone.now(),
    )


def _confirmar_verificacao(base: BaseDados, recursos: list[RecursoDados]) -> None:
    """Anda o relógio da periodicidade sem republicar.

    Usado quando a coleta não trouxe novidade: local e remoto seguem idênticos, então a promessa de
    atualização foi cumprida e a base não deve aparecer como atrasada.
    """
    agora = timezone.now()
    BaseDados.objects.filter(pk=base.pk).update(sincronizado_em=agora)
    RecursoDados.objects.filter(pk__in=[r.pk for r in recursos]).update(sincronizado_em=agora)


def _publicar(base: BaseDados, recursos: list[RecursoDados], servico) -> tuple[int, int]:
    """Sobe dataset e recursos ao CKAN. Devolve (sucessos, erros) somados."""
    ok_dataset, err_dataset = sync_dataset_with_ckan(BaseDados.objects.filter(pk=base.pk), servico.base_url, servico.api_key)
    ok_recursos, err_recursos = sync_resource_with_ckan(
        RecursoDados.objects.filter(pk__in=[r.pk for r in recursos]), servico.base_url, servico.api_key
    )
    return ok_dataset + ok_recursos, err_dataset + err_recursos


def _publicar_pendencia(base: BaseDados, recursos: list[RecursoDados], servico) -> Desfecho | None:
    """Conclui a publicação que ficou devendo de uma rodada anterior, ou ``None`` se não há.

    Depois de um ``ESQUEMA_ALTERADO`` o conteúdo novo fica gravado localmente e nada sobe ao CKAN.
    A coleta seguinte traz exatamente esse conteúdo, então sem este passo a rodada viraria
    ``SEM_ALTERACAO`` e ``_confirmar_verificacao`` andaria o relógio da periodicidade — a base se
    declarando em dia enquanto o CKAN exibe a versão antiga, para sempre.

    O sinal é o mesmo que o sync usa para decidir reenviar o arquivo
    (``recurso_alterado_apos_sync``), para não existirem duas réguas de "o local está à frente".
    """
    pendentes = [r for r in recursos if recurso_alterado_apos_sync(r)]
    if not pendentes:
        return None
    _, erros = _publicar(base, pendentes, servico)
    if erros:
        return Desfecho(ResultadoAtualizacao.FALHA_CKAN, f'{erros} erro(s) ao publicar no CKAN.', len(pendentes))
    return Desfecho(ResultadoAtualizacao.SUCESSO, 'Publicação pendente de uma rodada anterior concluída.', len(pendentes))


def _coletar_recursos(recursos: list[RecursoDados]) -> tuple[list[tuple], bool]:
    """Coleta todos os recursos e informa se alguma estrutura mudou.

    Returns:
        tuple: lista de ``(recurso, coletado, colunas)`` que mudaram de conteúdo, e um booleano
        indicando se pelo menos um recurso teve o esquema alterado.

    Raises:
        Exception: Qualquer falha de download é propagada — publicar um dataset pela metade é pior
            do que adiar a atualização inteira.
    """
    alterados: list[tuple] = []
    esquema_mudou = False
    for recurso in recursos:
        coletado = coleta.baixar(recurso.url)
        if coletado.conteudo == _conteudo_atual(recurso):
            continue
        colunas = coleta.ler_tabular(coletado.conteudo.decode('utf-8', 'replace'), recurso.formato).colunas
        if recurso.esquema and set(colunas) != set(recurso.esquema):
            esquema_mudou = True
        alterados.append((recurso, coletado, colunas))
    return alterados, esquema_mudou


def atualizar_base(base: BaseDados, servico) -> Desfecho:
    """Re-coleta e republica uma base. Não lança: toda falha vira um ``Desfecho``."""
    recursos = list(base.recursos.all())
    automaticos = [r for r in recursos if r.url]
    if not automaticos:
        return Desfecho(ResultadoAtualizacao.SEM_FONTE_AUTOMATICA, 'Nenhum recurso com URL de origem.')
    if not base.lai_liberada_para_sync():
        return Desfecho(ResultadoAtualizacao.BLOQUEADA_LAI, base.motivo_bloqueio_lai())

    try:
        alterados, esquema_mudou = _coletar_recursos(automaticos)
    except Exception as erro:
        logger.warning('Atualização automática: falha ao coletar a base %s: %s', base.pk, erro)
        return Desfecho(ResultadoAtualizacao.FALHA_DOWNLOAD, str(erro))

    if not alterados:
        devendo = _publicar_pendencia(base, recursos, servico)
        if devendo:
            return devendo
        _confirmar_verificacao(base, automaticos)
        return Desfecho(ResultadoAtualizacao.SEM_ALTERACAO, 'Conteúdo idêntico ao já publicado.')

    for recurso, coletado, colunas in alterados:
        _gravar(recurso, coletado, colunas)

    # Os espelhos CSV acompanham a origem mesmo quando o esquema mudou: o conteúdo local tem de
    # ficar coerente entre os dois, ainda que nada seja publicado nesta rodada.
    espelhos, avisos = espelho_csv.atualizar_espelhos([r for r, _, _ in alterados])

    if esquema_mudou:
        reabrir_lai_por_edicao(base)
        return Desfecho(
            ResultadoAtualizacao.ESQUEMA_ALTERADO,
            'A estrutura do arquivo mudou. O conteúdo novo não foi publicado e a base voltou para análise do LAI.',
            len(alterados),
        )

    _, erros = _publicar(base, [r for r, _, _ in alterados] + espelhos, servico)
    if erros:
        return Desfecho(ResultadoAtualizacao.FALHA_CKAN, f'{erros} erro(s) ao publicar no CKAN.', len(alterados))
    return Desfecho(ResultadoAtualizacao.SUCESSO, '; '.join(avisos), len(alterados))


def executar(hoje=None) -> ResumoAtualizacao:
    """Roda um ciclo completo: seleciona as bases vencidas, atualiza cada uma e grava o histórico.

    Args:
        hoje: Data de referência (``date``); o padrão é a data corrente.

    Returns:
        ResumoAtualizacao: Quantas bases foram verificadas, publicadas e ficaram pendentes.
    """
    servico = get_ckan_service()
    if not servico:
        logger.warning('Atualização automática: API do CKAN não configurada ou inativa.')
        return ResumoAtualizacao()

    verificadas = publicadas = pendentes = 0
    for base in bases_vencidas(hoje):
        desfecho = atualizar_base(base, servico)
        AtualizacaoBaseDados.objects.create(
            base_dados=base,
            resultado=desfecho.resultado,
            detalhe=desfecho.detalhe,
            recursos_atualizados=desfecho.recursos_atualizados,
        )
        verificadas += 1
        if desfecho.resultado == ResultadoAtualizacao.SUCESSO:
            publicadas += 1
        elif desfecho.resultado in ResultadoAtualizacao.PENDENTES:
            pendentes += 1
    return ResumoAtualizacao(verificadas=verificadas, publicadas=publicadas, pendentes=pendentes)
