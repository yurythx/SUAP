"""Relatório de situação dos processos de RSC docente que entraram num ano.

Reúne num só lugar o que antes exigia cruzar as abas de processos com a lista de avaliadores:
os processos do ano separados pela situação em que estão e, nos que estão em análise, o
andamento da banca — cada avaliador, a situação dele, quantas avaliações já foram finalizadas
e quantas faltam.

O ano é o de **entrada** do processo, isto é, do envio à CPPD: o processo RSC não guarda data
própria de abertura, e o processo eletrônico (ou, nos antigos, o protocolo físico) nasce
justamente no envio.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import QuerySet
from django.db.models.functions import Coalesce

from rsc import dashboard
from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC

# O resultado só é consolidado com 3 avaliações finalizadas (Avaliacao.finalizar_avaliacao).
AVALIACOES_NECESSARIAS = 3

# Avaliadores que compõem a banca; os demais são reservas (em espera) ou já saíram do processo.
STATUS_AVALIADOR_DA_BANCA = (ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.EM_AVALIACAO, ProcessoAvaliador.AVALIACAO_FINALIZADA)
STATUS_AVALIADOR_COM_PRAZO = (ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.EM_AVALIACAO)
STATUS_AVALIACAO_FINALIZADA = (Avaliacao.DEFERIDA, Avaliacao.INDEFERIDA)


@dataclass(frozen=True)
class Secao:
    chave: str
    titulo: str
    status: tuple[int, ...]


SECAO_EM_ANALISE = 'em_analise'

# Na ordem do fluxo. Os nomes seguem as abas da lista de processos, que é como a CPPD já as conhece.
SECOES = (
    Secao('validados', 'Validados', (ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES,)),
    Secao(SECAO_EM_ANALISE, 'Em análise', (ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO)),
    Secao('aguardando_ciencia', 'Aguardando ciência', (ProcessoRSC.STATUS_AGUARDANDO_CIENCIA,)),
    Secao('cientes', 'Cientes do resultado', (ProcessoRSC.STATUS_CIENTE_DO_RESULTADO,)),
    Secao('finalizados', 'Finalizados', (ProcessoRSC.STATUS_APROVADO, ProcessoRSC.STATUS_REPROVADO, ProcessoRSC.STATUS_ANALISADO)),
)


def processos_do_ano(ano: int, tipo_rsc_id: int | str | None = None) -> QuerySet:
    """Processos cuja entrada (processo eletrônico ou protocolo físico) ocorreu no ano."""
    qs = ProcessoRSC.objects.annotate(data_entrada=Coalesce('processo_eletronico__data_hora_criacao', 'protocolo__data_cadastro'))
    qs = qs.filter(data_entrada__year=ano)
    if tipo_rsc_id:
        qs = qs.filter(tipo_rsc_id=tipo_rsc_id)
    return qs.select_related('servidor', 'tipo_rsc', 'processo_eletronico', 'protocolo').order_by('data_entrada', 'id')


def numero_processo(processo: ProcessoRSC) -> str:
    if processo.processo_eletronico:
        return str(processo.processo_eletronico.numero_protocolo_fisico or processo.processo_eletronico)
    if processo.protocolo:
        return processo.protocolo.numero_processo
    return ''


def _prazo(processo_avaliador: ProcessoAvaliador) -> tuple[str | None, int | None]:
    """Data limite e dias restantes, só para quem ainda deve aceite ou avaliação.

    ``data_limite()`` consulta a configuração e percorre os dias úteis; é chamada uma vez só e os
    dias restantes saem da própria data devolvida.
    """
    if processo_avaliador.status not in STATUS_AVALIADOR_COM_PRAZO:
        return None, None
    try:
        data_limite = processo_avaliador.data_limite()
    except Exception:
        return None, None
    data = dashboard._parse_data_limite(data_limite)
    return data_limite, (data - datetime.date.today()).days if data else None


def _situacao_avaliador(processo_avaliador: ProcessoAvaliador, avaliacao_finalizada: Avaliacao | None) -> str:
    situacao = processo_avaliador.get_status_display()
    if avaliacao_finalizada:
        return f'{situacao} ({avaliacao_finalizada.get_status_display()})'
    return situacao


def resumir_banca(vinculos: Iterable[ProcessoAvaliador], avaliacoes: Iterable[Avaliacao], reservas: int) -> dict:
    """Andamento da banca a partir dos avaliadores e das avaliações do processo.

    Args:
        vinculos: Avaliadores que compõem a banca (aguardando aceite, em avaliação ou finalizados).
        avaliacoes: Todas as avaliações do processo.
        reservas: Quantidade de avaliadores reserva em espera.

    Returns:
        ``avaliadores`` (uma linha por avaliador), ``finalizadas``, ``faltam`` e ``reservas``.
    """
    # Só a avaliação finalizada entra no rótulo do avaliador. Como nem `ProcessoAvaliador` nem
    # `Avaliacao` são únicos por (processo, avaliador), um avaliador que desistiu e voltou tem duas
    # avaliações; indexar todas deixaria o rótulo depender da ordem do banco.
    finalizadas_por_avaliador = {avaliacao.avaliador_id: avaliacao for avaliacao in avaliacoes if avaliacao.status in STATUS_AVALIACAO_FINALIZADA}
    finalizadas = sum(1 for avaliacao in avaliacoes if avaliacao.status in STATUS_AVALIACAO_FINALIZADA)

    linhas = []
    for vinculo in vinculos:
        data_limite, dias = _prazo(vinculo)
        linhas.append(
            {
                'avaliador': vinculo.avaliador,
                'tipo': vinculo.get_tipo_avaliador_display(),
                'situacao': _situacao_avaliador(vinculo, finalizadas_por_avaliador.get(vinculo.avaliador_id)),
                'data_limite': data_limite,
                'dias_restantes': dias,
            }
        )
    return {
        'avaliadores': linhas,
        'finalizadas': finalizadas,
        'faltam': max(AVALIACOES_NECESSARIAS - finalizadas, 0),
        'reservas': reservas,
    }


def bancas_por_processo(processos: Iterable[ProcessoRSC]) -> dict[int, dict]:
    """Andamento da banca de vários processos com duas consultas, em vez de três por processo."""
    ids = [processo.pk for processo in processos]
    vinculos = (
        ProcessoAvaliador.objects.filter(processo_id__in=ids, status__in=(*STATUS_AVALIADOR_DA_BANCA, ProcessoAvaliador.EM_ESPERA))
        .select_related('avaliador__vinculo__user')
        .order_by('tipo_avaliador', 'data_cadastro')
    )
    banca = defaultdict(list)
    reservas = defaultdict(int)
    for vinculo in vinculos:
        if vinculo.status == ProcessoAvaliador.EM_ESPERA:
            reservas[vinculo.processo_id] += 1
        else:
            banca[vinculo.processo_id].append(vinculo)

    avaliacoes = defaultdict(list)
    for avaliacao in Avaliacao.objects.filter(processo_id__in=ids):
        avaliacoes[avaliacao.processo_id].append(avaliacao)

    return {pk: resumir_banca(banca[pk], avaliacoes[pk], reservas[pk]) for pk in ids}


def agrupar_por_secao(processos: Iterable[ProcessoRSC]) -> list[dict]:
    """Distribui os processos nas seções do relatório; o que não pertence a nenhuma fica de fora."""
    processos = list(processos)
    status_em_analise = next(secao.status for secao in SECOES if secao.chave == SECAO_EM_ANALISE)
    bancas = bancas_por_processo([processo for processo in processos if processo.status in status_em_analise])

    grupos = []
    for secao in SECOES:
        itens = [{'processo': processo, 'numero': numero_processo(processo)} for processo in processos if processo.status in secao.status]
        if secao.chave == SECAO_EM_ANALISE:
            for item in itens:
                item['banca'] = bancas[item['processo'].pk]
        grupos.append({'secao': secao, 'itens': itens})
    return grupos


def montar_relatorio(ano: int, tipo_rsc_id: int | str | None = None) -> list[dict]:
    return agrupar_por_secao(processos_do_ano(ano, tipo_rsc_id))


def _data(valor: datetime.datetime | datetime.date | None) -> str:
    return valor.strftime('%d/%m/%Y') if valor else ''


def _colunas_processo(item: dict) -> list:
    processo = item['processo']
    return [
        item['numero'],
        str(processo.servidor),
        getattr(processo.servidor, 'matricula', ''),
        str(processo.tipo_rsc),
        _data(getattr(processo, 'data_entrada', None)),
        processo.get_status_display(),
    ]


CABECALHO_PROCESSO = ['Processo', 'Docente', 'Matrícula', 'Tipo de RSC', 'Data de entrada', 'Situação']
CABECALHO_BANCA = ['Avaliações finalizadas', 'Avaliações que faltam', 'Reservas', 'Avaliador', 'Tipo de avaliador', 'Situação do avaliador', 'Prazo']


def _linhas_em_analise(itens: list[dict]) -> list[list]:
    """Uma linha por avaliador da banca, repetindo os dados do processo para a planilha filtrar bem."""
    linhas = [CABECALHO_PROCESSO + CABECALHO_BANCA]
    for item in itens:
        banca = item['banca']
        resumo = [banca['finalizadas'], banca['faltam'], banca['reservas']]
        avaliadores = banca['avaliadores'] or [None]
        for avaliador in avaliadores:
            detalhe = (
                ['', '', '', '']
                if avaliador is None
                else [str(avaliador['avaliador']), avaliador['tipo'], avaliador['situacao'], avaliador['data_limite'] or '']
            )
            linhas.append(_colunas_processo(item) + resumo + detalhe)
    return linhas


def linhas_xls(grupos: list[dict]) -> dict[str, list[list]]:
    """Uma planilha por seção, no formato de ``XlsResponse`` (dicionário de listas de linhas)."""
    planilhas = {}
    for grupo in grupos:
        secao, itens = grupo['secao'], grupo['itens']
        if secao.chave == SECAO_EM_ANALISE:
            planilhas[secao.titulo] = _linhas_em_analise(itens)
            continue
        cabecalho = CABECALHO_PROCESSO + (['Data de finalização'] if secao.chave == 'finalizados' else [])
        linhas = [cabecalho]
        for item in itens:
            extra = [_data(item['processo'].data_finalizacao_processo)] if secao.chave == 'finalizados' else []
            linhas.append(_colunas_processo(item) + extra)
        planilhas[secao.titulo] = linhas
    return planilhas
