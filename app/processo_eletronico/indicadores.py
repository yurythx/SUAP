"""Indicadores gerenciais de processos restritos aos setores autorizados pela view."""

from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import TruncMonth, TruncYear

from djtools.html.graficos import ColumnChart
from processo_eletronico.models import Tramite


def filtrar_periodo(queryset: QuerySet, campo_data: str, dados: dict) -> QuerySet:
    """Aplica os limites inclusivos do período à data do evento."""
    if dados.get('data_inicio'):
        queryset = queryset.filter(**{f'{campo_data}__gte': datetime.combine(dados['data_inicio'], datetime.min.time())})
    if dados.get('data_final'):
        queryset = queryset.filter(**{f'{campo_data}__lte': datetime.combine(dados['data_final'], datetime.max.time())})
    return queryset


def limites_periodo(periodo: str, hoje: date) -> tuple[date | None, date | None]:
    """Resolve os atalhos de calendário sem usar intervalos aproximados em dias."""
    mes = hoje.replace(day=1)
    ano = hoje.replace(month=1, day=1)
    return {
        'ano_atual': (ano, hoje),
        'ano_anterior': (ano - relativedelta(years=1), ano - relativedelta(days=1)),
        'mes_atual': (mes, hoje),
        'mes_anterior': (mes - relativedelta(months=1), mes - relativedelta(days=1)),
        'todo': (None, None),
    }[periodo]


def completar_serie(linhas: list[dict], dados: dict) -> list[dict]:
    """Inclui meses/anos sem movimento dentro dos limites consultados."""
    inicio = dados.get('data_inicio') or (linhas[0]['periodo'].date() if linhas else None)
    fim = dados.get('data_final') or (linhas[-1]['periodo'].date() if linhas else None)
    if not inicio or not fim:
        return []
    anual = dados['agrupamento'] == 'ano'
    passo = relativedelta(years=1) if anual else relativedelta(months=1)
    periodo = inicio.replace(month=1, day=1) if anual else inicio.replace(day=1)
    por_periodo = {linha['periodo'].date(): linha for linha in linhas}
    serie = []
    while periodo <= fim:
        linha = por_periodo.get(periodo, {'processos': 0, 'tramitacoes': 0, 'entradas': 0, 'saidas': 0})
        serie.append({**linha, 'rotulo': periodo.strftime('%Y' if anual else '%m/%Y')})
        periodo += passo
    return serie


def indicadores_tramitacao(ids_setores: list[int], dados: dict) -> dict:
    """Consolida a árvore sem duplicar trâmites internos nem processos repetidos."""
    entrada = Q(destinatario_setor_id__in=ids_setores)
    saida = Q(remetente_setor_id__in=ids_setores)
    tramites = filtrar_periodo(Tramite.objects.filter(entrada | saida), 'data_hora_encaminhamento', dados)
    contagens = {
        'processos': Count('processo_id', distinct=True),
        'tramitacoes': Count('pk'),
        'entradas': Count('processo_id', distinct=True, filter=entrada),
        'saidas': Count('processo_id', distinct=True, filter=saida),
    }
    resumo = tramites.aggregate(**contagens)
    agrupar = TruncYear if dados['agrupamento'] == 'ano' else TruncMonth
    linhas = list(
        tramites.order_by().annotate(periodo=agrupar('data_hora_encaminhamento')).values('periodo').annotate(**contagens).order_by('periodo')
    )
    serie = completar_serie(linhas, dados)
    grafico = ColumnChart(
        'grafico_tramitacao',
        title='Processos distintos que tramitaram',
        data=[[linha['rotulo'], linha['processos']] for linha in serie],
    )
    return {'resumo': resumo, 'serie': serie, 'grafico': grafico}
