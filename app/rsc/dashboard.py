"""Agregações para o Painel (dashboard) da CPPD do módulo RSC docente.

Funções puras de consulta/agrupamento, sem camada HTTP, reutilizáveis e testáveis.
Usa exclusivamente datas internas do módulo RSC (ValidacaoCPPD.data,
ProcessoAvaliador.data_aceite/data_convite/data_cadastro, Avaliacao.data_finalizacao e
ProcessoRSC.data_finalizacao_processo).
"""

import datetime

from django.db.models import Count
from django.db.models.query import QuerySet
from django.utils import timezone

from rsc.models import Avaliacao, ProcessoAvaliador, ProcessoRSC, ValidacaoCPPD

STATUS_VALIDACAO = (ProcessoRSC.STATUS_AGUARDANDO_VALIDACAO_CPPD, ProcessoRSC.STATUS_AGUARDANDO_NOVA_VALIDACAO)
STATUS_ACAO_CPPD = (*STATUS_VALIDACAO, ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES, ProcessoRSC.STATUS_CIENTE_DO_RESULTADO)
STATUS_EM_ANDAMENTO = (ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR, ProcessoRSC.STATUS_EM_AVALIACAO)
MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

# Quantidade correta de avaliadores principais por processo (Resolução): 1 interno + 2 externos.
QTD_AVALIADORES_INTERNOS = 1
QTD_AVALIADORES_EXTERNOS = 2


def base_queryset(tipo_rsc_id: int | str | None = None) -> QuerySet:
    qs = ProcessoRSC.objects.all()
    if tipo_rsc_id:
        qs = qs.filter(tipo_rsc_id=tipo_rsc_id)
    return qs


def indicadores(qs: QuerySet) -> dict:
    return {
        'aguardando_validacao': qs.filter(status__in=STATUS_VALIDACAO).count(),
        'aguardando_avaliadores': qs.filter(status=ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES).count(),
        'aguardando_aceite': qs.filter(status=ProcessoRSC.STATUS_AGUARDANDO_ACEITE_AVALIADOR).count(),
        'em_avaliacao': qs.filter(status=ProcessoRSC.STATUS_EM_AVALIACAO).count(),
        'aguardando_finalizacao': qs.filter(status=ProcessoRSC.STATUS_CIENTE_DO_RESULTADO).count(),
    }


def _situacao_para_dados(contagem: dict) -> list:
    return [[label, contagem.get(status, 0)] for status, label in ProcessoRSC.STATUS_CHOICES if contagem.get(status, 0)]


def dados_por_situacao(qs: QuerySet) -> list:
    contagem = dict(qs.values_list('status').annotate(total=Count('id')))
    return _situacao_para_dados(contagem)


def dados_por_tipo_rsc(qs: QuerySet) -> list:
    linhas = qs.values('tipo_rsc__nome').annotate(total=Count('id')).order_by('tipo_rsc__nome')
    return [[linha['tipo_rsc__nome'] or 'Sem tipo', linha['total']] for linha in linhas]


def dados_por_unidade(qs: QuerySet) -> list:
    linhas = qs.values('servidor__setor__uo__sigla').annotate(total=Count('id')).order_by('-total')
    return [[linha['servidor__setor__uo__sigla'] or 'Sem unidade', linha['total']] for linha in linhas]


def dados_resultado(qs: QuerySet) -> list:
    rotulos = [
        (ProcessoRSC.STATUS_APROVADO, 'Deferido'),
        (ProcessoRSC.STATUS_REPROVADO, 'Indeferido'),
        (ProcessoRSC.STATUS_ANALISADO, 'Analisado'),
    ]
    return [[rotulo, qs.filter(status=status).count()] for status, rotulo in rotulos]


def _contagem_para_meses(contagem: dict) -> list:
    return [[MESES[mes - 1], contagem.get(mes, 0)] for mes in range(1, 13)]


def dados_finalizados_por_mes(qs: QuerySet, ano: int) -> list:
    linhas = qs.filter(data_finalizacao_processo__year=ano).values_list('data_finalizacao_processo__month').annotate(total=Count('id'))
    return _contagem_para_meses(dict(linhas))


def _parse_data_limite(texto: str | None) -> datetime.date | None:
    if not texto:
        return None
    try:
        return datetime.datetime.strptime(texto, '%d/%m/%Y').date()
    except ValueError:
        return None


def dias_restantes(processo_avaliador: ProcessoAvaliador) -> int | None:
    try:
        texto = processo_avaliador.data_limite()
    except Exception:
        return None
    data = _parse_data_limite(texto)
    if data is None:
        return None
    return (data - datetime.date.today()).days


def avaliadores_prazo_critico(limite_dias: int = 3) -> list:
    qs = ProcessoAvaliador.objects.filter(status__in=[ProcessoAvaliador.AGUARDANDO_ACEITE, ProcessoAvaliador.EM_AVALIACAO])
    criticos = []
    for processo_avaliador in qs:
        dias = dias_restantes(processo_avaliador)
        if dias is not None and dias <= limite_dias:
            criticos.append({'avaliador': processo_avaliador, 'dias': dias})
    criticos.sort(key=lambda item: item['dias'])
    return criticos


def processos_avaliadores_incompletos(qs: QuerySet) -> list:
    em_andamento = qs.filter(status__in=STATUS_EM_ANDAMENTO)
    incompletos = []
    for processo in em_andamento:
        internos = processo.qtd_avaliadores_internos_ativos()
        externos = processo.qtd_avaliadores_externos_ativos()
        if internos != QTD_AVALIADORES_INTERNOS or externos != QTD_AVALIADORES_EXTERNOS:
            incompletos.append({'processo': processo, 'internos': internos, 'externos': externos})
    return incompletos


def processos_sem_reserva(qs: QuerySet) -> list:
    em_andamento = qs.filter(status__in=STATUS_EM_ANDAMENTO)
    return [p for p in em_andamento if p.qtd_avaliadores_internos_reserva() == 0 or p.qtd_avaliadores_externos_reserva() == 0]


def ultima_movimentacao(processo: ProcessoRSC) -> datetime.datetime | None:
    datas = []
    validacao = ValidacaoCPPD.objects.filter(processo=processo).order_by('-data').first()
    if validacao:
        datas.append(validacao.data)
    avaliador = ProcessoAvaliador.objects.filter(processo=processo, data_aceite__isnull=False).order_by('-data_aceite').first()
    if avaliador:
        datas.append(avaliador.data_aceite)
    avaliacao = Avaliacao.objects.filter(processo=processo, data_finalizacao__isnull=False).order_by('-data_finalizacao').first()
    if avaliacao:
        datas.append(avaliacao.data_finalizacao)
    return max(datas) if datas else None


def parado_dias(processo: ProcessoRSC) -> int | None:
    movimentacao = ultima_movimentacao(processo)
    if movimentacao is None:
        return None
    return (timezone.now() - movimentacao).days


def processos_acao_cppd(qs: QuerySet) -> list:
    processos = qs.filter(status__in=STATUS_ACAO_CPPD).order_by('status', 'id')
    return [{'processo': processo, 'parado_dias': parado_dias(processo)} for processo in processos]
