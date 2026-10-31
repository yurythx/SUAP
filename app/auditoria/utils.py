import calendar
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q, Subquery

from auditoria.models.liberacao import CategoriaLiberacao
from comum.utils import get_setores_que_sou_chefe_hoje
from djtools.utils import DateInterval, get_datetime_now, is_feriado, is_final_de_semana
from ferias.models import ParcelaFerias
from rh.models import Funcao, Servidor, ServidorAfastamento, ServidorFuncaoHistorico, Setor

CACHE_TIMEOUT = 60 * 15  # 5 minutos


def setores_que_sou_chefe_hoje_diretamente(user):
    """
    Retorna os setores que o usuário é chefe hoje diretamente, incluindo os descendentes.
    """
    # Subquery para obter os IDs dos setores descendentes
    ids_descendentes_subquery = Setor.objects.suap_ativos().filter(superior=OuterRef('pk')).values_list('id', flat=True)

    # Obter os setores que o usuário é chefe hoje
    setores_chefe = get_setores_que_sou_chefe_hoje(user)

    # Filtrar os setores descendentes
    return Setor.objects.suap().filter(id__in=Subquery(ids_descendentes_subquery)).filter(id__in=setores_chefe.values_list('id', flat=True))


def setores_que_respondo_como_chefe(user):
    """
    Retorna os setores que o usuário responde como chefe, incluindo os descendentes sem chefes.
    """
    hoje = get_datetime_now().date()
    chefes_existem_subquery = (
        ServidorFuncaoHistorico.objects.filter(
            setor_suap=OuterRef('pk'),
            funcao__codigo__in=Funcao.get_codigos_funcao_chefia(),
        )
        .exclude(
            servidor__vinculos__user=user  # Exclui o próprio usuário da checagem
        )
        .filter(Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))
    )

    setores_chefe = get_setores_que_sou_chefe_hoje(user)
    chefias_diretas = setores_chefe.values_list('id', flat=True)

    # IDs dos setores e seus descendentes
    ids_incluidos = set()
    for setor in setores_chefe:
        ids_incluidos.add(setor.id)
        ids_incluidos.update(setor.ids_descendentes)

    # Retorna todos setores (chefia ou descendentes) sem outro chefe ativo
    setores = (
        Setor.objects.suap()
        .filter(id__in=ids_incluidos)
        .annotate(tem_outro_chefe=Exists(chefes_existem_subquery))
        .filter(Q(tem_outro_chefe=False) | Q(id__in=chefias_diretas))
        .distinct()
    )
    return setores


def dias_uteis_para_auditoria(data_inicial, data_final, uo=None):
    """
    Conta os dias úteis entre duas datas (inclusive a data_inicial e data_final),
    ignorando finais de semana e feriados se fornecido uma UO.

    Args:
        data_inicial (date): data inicial do intervalo.
        data_final (date): data final do intervalo.
        uo (comum.UnidadeOrganizacional): unidade organizacional para verificação de feriados.

    Returns:
        int: quantidade de dias úteis no intervalo.
    """
    if data_final < data_inicial:
        # Inverte se a ordem for invertida
        data_inicial, data_final = data_final, data_inicial

    dias_uteis = 0
    data_atual = data_inicial
    considerar_ponto = considerar_liberacoes_ponto()

    while data_atual <= data_final:
        if not is_final_de_semana(data_atual) or (considerar_ponto and is_feriado(data_atual, uo)):
            dias_uteis += 1
        data_atual += timedelta(days=1)

    return dias_uteis


def get_ch_prevista_auditor_periodo(servidor: Servidor, data_inicial: date, data_fim: date):
    ch_diaria = servidor.jornada_trabalho.get_jornada_trabalho_diaria()
    dias_uteis = dias_uteis_para_auditoria(data_inicial, data_fim, servidor.setor.uo)
    return dias_uteis * ch_diaria


def get_ch_afastada_periodo(servidor: Servidor, data_inicial: date, data_fim: date):
    ch_afastada = 0
    ferias_mes = ParcelaFerias.objects.filter(
        ferias__servidor=servidor,
        data_inicio__gte=data_inicial,
        data_fim__lte=data_fim,
    )
    ch_afastada += sum(ferias.duracao_em_horas() for ferias in ferias_mes)
    # Horas afastadas devido a afastamentos
    concedidos = ServidorAfastamento.objects.filter(
        servidor=servidor,
        cancelado=False,
        data_inicio__lte=data_fim,
        data_termino__gte=data_inicial,
    )
    ch_afastada += sum(afastamento.ch_intervalo(data_inicial, data_fim) for afastamento in concedidos)
    return ch_afastada


def calcular_liberacoes_programadas(servidor: Servidor, data_inicial: date, data_fim: date):
    """
    Calcula a carga horária a ser descontada no período devido a liberações programadas ativas do servidor.
    """
    from .models import LiberacaoProgramada

    jornada_diaria = servidor.jornada_trabalho.get_jornada_trabalho_diaria()
    uo = servidor.setor.uo
    qs = LiberacaoProgramada.objects.ativas().filter(Q(uo=uo) | Q(uo__isnull=True))
    return qs.desconto_total_periodo(jornada_diaria, data_inicial, data_fim)


def get_ch_prevista_auditor_ano(auditor: Servidor, ano: int) -> dict[int, int]:
    carga_horaria_mensal = {}
    for mes in range(1, 13):
        data_inicio = datetime(ano, mes, 1).date()
        # Calcular o último dia do mês
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        data_fim = datetime(ano, mes, ultimo_dia).date()
        # Obter a carga horária prevista para o mês
        ch_prevista = get_ch_prevista_auditor_periodo(auditor, data_inicio, data_fim)
        descontos = calcular_liberacoes_programadas(auditor, data_inicio, data_fim)
        carga_horaria_mensal[mes] = ch_prevista - descontos
    return carga_horaria_mensal


def get_ch_prevista_auditores_ano(auditores, ano):
    carga_horaria_por_auditor = {}
    for auditor in auditores:
        user = auditor.user
        cache_key = f'ch_auditor_{user.id}_{ano}'  # Chave única para cada auditor no ano
        carga_horaria = cache.get(cache_key)
        if carga_horaria is None:
            # Se não estiver no cache, calcula e armazena
            carga_horaria = get_ch_prevista_auditor_ano(auditor.relacionamento, ano)
            cache.set(cache_key, carga_horaria, CACHE_TIMEOUT)  # Armazena no cache
        # Adiciona ao dicionário final
        carga_horaria_por_auditor[user] = carga_horaria
    return carga_horaria_por_auditor


def acumular_afastamentos(
    afastamentos: Iterable[object],
    intervalo_mes: DateInterval,
    *,
    get_intervalo: Callable[[object], DateInterval],
    get_dias_uteis: Callable[[object, date, date], int],
    get_carga_horaria: Callable[[object, date, date], float] | None = None,
) -> tuple[list[object], int, float]:
    selecionados: list[object] = []
    dias_afastados = 0
    horas_afastadas = 0.0

    for afastamento in afastamentos:
        obj_interval = get_intervalo(afastamento)
        if obj_interval.intersects(intervalo_mes):
            selecionados.append(afastamento)
            dias_afastados += int(get_dias_uteis(afastamento, intervalo_mes.start, intervalo_mes.end))
            if get_carga_horaria is not None:
                horas_afastadas += float(get_carga_horaria(afastamento, intervalo_mes.start, intervalo_mes.end))

    return selecionados, dias_afastados, horas_afastadas


def considerar_liberacoes_ponto():
    from comum.models import Configuracao

    return bool(Configuracao.get_valor_por_chave('auditoria', 'considerar_liberacoes_ponto'))


def _liberacoes_de_feriado(uo=None):
    """Liberações programadas ativas de feriado que valem para a UO informada."""
    from auditoria.models import LiberacaoProgramada

    categorias = [CategoriaLiberacao.FERIADO, CategoriaLiberacao.FERIADO_RECORRENTE]
    liberacoes = LiberacaoProgramada.objects.ativas().filter(categoria__in=categorias)
    if uo:
        # Liberações da própria UO somadas às globais.
        return liberacoes.filter(Q(uo=uo) | Q(uo__isnull=True))
    return liberacoes.filter(uo__isnull=True)


def fracoes_dias_uteis_auditoria(data_inicial, data_final, uo=None, jornada_diaria_horas=8.0) -> dict[date, float]:
    """
    Mapeia cada dia útil do intervalo na fração de expediente que ele representa.

    Finais de semana ficam de fora do dicionário; os demais dias entram com:
        - 1.0 em dia normal
        - 0.5 em dia de meio expediente
        - 0.0 em dia com liberação total (feriado)

    Existe para que quem precise somar dias **distintos** possa fazê-lo sem
    recontar um dia coberto por mais de um afastamento — ver
    ``horas_afastadas_no_periodo``.

    Args:
        data_inicial (date): data inicial do intervalo.
        data_final (date): data final do intervalo.
        uo (UnidadeOrganizacional): unidade organizacional para filtrar liberações.
        jornada_diaria_horas (float): jornada diária em horas (padrão 8.0).

    Returns:
        dict[date, float]: fração de dia útil por data.
    """
    if data_final < data_inicial:
        # Inverte se a ordem for invertida
        data_inicial, data_final = data_final, data_inicial

    liberacoes = list(_liberacoes_de_feriado(uo))

    fracoes: dict[date, float] = {}
    data_atual = data_inicial
    while data_atual <= data_final:
        if not is_final_de_semana(data_atual):
            # O maior desconto entre as liberações do dia é o que vale.
            desconto_max = 0.0
            for liberacao in liberacoes:
                desconto_max = max(desconto_max, liberacao.desconto_no_dia(data_atual, jornada_diaria_horas))
            fracoes[data_atual] = 1.0 - min(desconto_max / jornada_diaria_horas, 1.0)
        data_atual += timedelta(days=1)

    return fracoes


def dias_uteis_auditoria(data_inicial, data_final, uo=None, jornada_diaria_horas=8.0):
    """
    Conta os dias úteis entre duas datas usando as liberações programadas da auditoria,
    ignorando finais de semana e dias com liberação total.

    Args:
        data_inicial (date): data inicial do intervalo.
        data_final (date): data final do intervalo.
        uo (UnidadeOrganizacional): unidade organizacional para filtrar liberações.
        jornada_diaria_horas (float): jornada diária em horas (padrão 8.0).
    Returns:
        float: quantidade de dias úteis no intervalo.
               - Dia com liberação total (LIBERADO) = 0 dias úteis
               - Dia com meio expediente = 0.5 dias úteis
                - Dia normal = 1 dia útil
    """
    return sum(fracoes_dias_uteis_auditoria(data_inicial, data_final, uo, jornada_diaria_horas).values(), 0.0)


def horas_afastadas_no_periodo(
    intervalos: Iterable[tuple[date, date]],
    data_inicial: date,
    data_final: date,
    uo=None,
    jornada_diaria_horas: float = 8.0,
) -> float:
    """
    Soma as horas afastadas no período contando **cada dia uma única vez**.

    Os afastamentos de um auditor vêm de fontes que se sobrepõem — o que ele
    declarou no planejamento, as férias do app ``ferias`` e os afastamentos
    concedidos pelo RH. Somar a duração de cada registro descontaria o mesmo dia
    tantas vezes quantas fontes o cobrissem; por isso o cálculo é feito sobre a
    união dos dias, e não sobre a soma dos intervalos.

    Args:
        intervalos: pares ``(data_inicio, data_fim)``, inclusivos nas duas pontas.
        data_inicial (date): início do período considerado (recorta os intervalos).
        data_final (date): fim do período considerado (recorta os intervalos).
        uo (UnidadeOrganizacional): unidade organizacional para filtrar liberações.
        jornada_diaria_horas (float): jornada diária em horas (padrão 8.0).

    Returns:
        float: horas afastadas no período.
    """
    fracoes = fracoes_dias_uteis_auditoria(data_inicial, data_final, uo, jornada_diaria_horas)

    dias_afastados: set[date] = set()
    for inicio, fim in intervalos:
        data_atual = max(data_inicial, inicio)
        ultimo_dia = min(data_final, fim)
        while data_atual <= ultimo_dia:
            if data_atual in fracoes:
                dias_afastados.add(data_atual)
            data_atual += timedelta(days=1)

    return sum(fracoes[dia] for dia in dias_afastados) * jornada_diaria_horas
