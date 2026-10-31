from datetime import timedelta

from django.apps import apps

from djtools.utils import get_datetime_now
from rh.models import UnidadeOrganizacional


def transforma_periodo_em_lista_dias(data_inicio, data_fim):
    """Retorna a lista de dias entre a data_inicio até data_fim"""
    dias = []
    while data_inicio <= data_fim:
        dias.append(data_inicio)
        data_inicio += timedelta(days=1)
    return dias


def buscar_liberacoes(data_inicio):
    """retorna a lista de dias que não tem expediente"""
    liberacoes = []
    Liberacao = apps.get_model('ponto', 'Liberacao')
    if Liberacao:
        data_fim = data_inicio + timedelta(days=150)

        lista_liberacoes = list(Liberacao.get_liberacoes_calendario_recorrentes(UnidadeOrganizacional.TIPO_REITORIA, data_inicio.year)) + list(
            Liberacao.objects.filter(uo=None, data_inicio__gte=data_inicio, ch_maxima_exigida=0)
        )

        if data_inicio.year != data_fim.year:
            lista_liberacoes = lista_liberacoes + list(Liberacao.get_liberacoes_calendario(UnidadeOrganizacional.TIPO_REITORIA, data_fim.year))

        for liberacao in lista_liberacoes:
            liberacoes.extend(transforma_periodo_em_lista_dias(liberacao.data_inicio, liberacao.data_fim))
        return liberacoes


def calcula_data_limite_sem_feriados_fds(prazo_ciencia):
    data_inicial = get_datetime_now()
    liberacoes = buscar_liberacoes(data_inicial)
    # Verificar se a data inicial é um feriado ou fim de semana e ajustar
    while data_inicial.weekday() >= 5 or data_inicial in liberacoes:
        data_inicial += timedelta(days=1)
    dias_contados = 0
    while dias_contados < prazo_ciencia:
        data_inicial += timedelta(days=1)
        if data_inicial.weekday() < 5 and data_inicial not in liberacoes:
            dias_contados += 1
    #
    return data_inicial
