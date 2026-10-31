from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import ceil
from time import mktime

from dateutil.relativedelta import relativedelta
from django.conf import settings

from djtools.choices import Meses


def get_datetime_now():
    """
    Obtem a data e hora atual do servidor.

    Returns:
        timezone.now() caso seja possível importar o timezone, caso contrário, datetime.now().
    """
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        import datetime

        return datetime.datetime.now()


def somar_dias(data, qtd_dias):
    """
    Soma **qtd_dias** a data passada.

    Args:
        data (date|datetime): data para o cálculo;
        qtd_dias (int): número de dias a somar.

    Returns:
        Date/Datetime acrescido de **qtd_dias**.
    """
    t = timedelta(qtd_dias)
    return data + t


def is_final_de_semana(data):
    return data.weekday() in [5, 6]


def is_feriado(data, uo=None):
    result = False
    if 'ponto' in settings.INSTALLED_APPS:
        from ponto.enums import TipoLiberacao
        from ponto.models import Liberacao

        result = (
            Liberacao.filtrar_por_periodo_por_uo(data, data, uo)
            .filter(tipo__in=[TipoLiberacao.get_numero(TipoLiberacao.FERIADO), TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE)])
            .exists()
        )
    return result


def somar_dias_uteis(data, qtd_dias, uo=None):
    """
    Soma **qtd_dias** à **data** ignorando finais de semana e, se informado, as liberações (app ponto) da **uo**.

    Args:
        data (date): data para o cálculo;

        qtd_dias (int): número de dias a somar;

        uo (comum.UnidadeOrganizacional).

    Returns:
        Date acrescido de **qtd_dias**.
    """
    datafinal = data
    for _i in range(qtd_dias):
        datafinal = somar_dias(datafinal, 1)
        eh_dia_inutil = True
        while eh_dia_inutil:
            if is_final_de_semana(datafinal) or is_feriado(datafinal, uo):
                datafinal = somar_dias(datafinal, 1)
            else:
                eh_dia_inutil = False
    return datafinal


def intervalo_intersecao(inicio1: date, fim1: date, inicio2: date, fim2: date):
    """Interseção de dois intervalos [start, end] inclusivos."""
    start = max(inicio1, inicio2)
    end = min(fim1, fim2)
    return (start, end) if start <= end else (None, None)


def contar_dias_uteis(data_inicial, data_final, uo=None):
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

    while data_atual <= data_final:
        if not is_final_de_semana(data_atual) and not is_feriado(data_atual, uo):
            dias_uteis += 1
        data_atual += timedelta(days=1)

    return dias_uteis


def date_to_string(data=None):
    """
    Converte um **date** em uma string no formato dd/mm/aaaa.

    Args:
        date (date): data a ser convertida.

    Returns:
        String com a data passada convertida.
    """
    if data is None:
        data = datetime.today()
    return data.strftime('%d/%m/%Y')


def datetime_to_string(datahora=None):
    """
    Converte um **datetime** em uma string no formato dd/mm/aaaa HH/MM/SS.

    Args:
        datahora (date): data a ser convertida.

    Returns:
        String com a data passada convertida.
    """
    if datahora is None:
        datahora = datetime.now()
    return datahora.strftime('%d/%m/%y %H:%M:%S')


def eh_bissexto(ano):
    """
    Verifica se o ano é bissexto.

    Args:
        ano (int): ano a ser testado.

    Returns:
         True se o ano for bissexto.
    """
    return bool(ano % 4 == 0 and ano % 100 != 0 or ano % 400 == 0)


def ultimo_dia(mes, ano):
    """
    Obtem o último dia do mês.

    Args:
        mes (int): número do mês;
        ano (int): número do ano.

    Returns:
        Inteiro com o último dia do mês.
    """
    ultimosDias = {1: 31, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    if mes == 2:
        if eh_bissexto(ano):
            return 29
        else:
            return 28
    else:
        return ultimosDias[mes]


def ultimo_dia_date(mes, ano):
    """
    Obtem o **date** com o último dia do mês.

    Args:
        mes (int): número com o mês;
        ano (int): número com o ano.

    Returns:
        Retorna um objeto **date** com o último dia do mês.
    """
    return date(ano, mes, ultimo_dia(mes, ano))


def data_extenso(data=None):
    """
    Obtem o **date** escrito por extenso.

    Args:
        data (date): data a processar.

    Returns:
         String com o **date** escrito por extenso.
    """
    try:
        data = data or date.today()
        # Se já for string no formato DD/MM/YYYY ou DD-MM-YYYY
        if isinstance(data, str):
            dia = data[:2]
            mes = Meses.get_mes(int(data[3:5]))
            ano = data[6:]
            return f'{dia} de {mes} de {ano}'

        result = f'{data.day} de {Meses.get_mes(data.month)} de {data.year}'
        if hasattr(data, 'time'):
            result = f'{result} às {data.hour:02d}:{data.minute:02d}:{data.second:02d}'
        return result
    except ValueError:
        return data
    except Exception:
        return '-'


@dataclass(frozen=True)
class DateInterval:
    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError('End date cannot be before start date')

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def intersects(self, other: DateInterval) -> bool:
        return not (other.end < self.start or other.start > self.end)

    def intersection(self, other: DateInterval) -> type[DateInterval]:
        return DateInterval(max(self.start, other.start), min(self.end, other.end))

    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __str__(self):
        return f'[{self.start} → {self.end}]'


def str_to_dateBR(value, force_4_digits_year=True):
    """
    Converte ums string no formato dia/mês/ano em um "**datetime.date**".

    Args:
        value (string): data para conversão;
        force_4_digits_year (bool): indica que o ano deve ter 4 digitos.

    Raises:
        ValueError se **value** tiver mais que 2 '/';
        ValueError se o ano não tiver 4 digitos e **force_4_digits_year** for verdadeiro.

    Returns:
        Date com base em **value**.

    """
    # convert yyyy-mm-dd format to dd/mm/yyyy format
    if value and '-' in value:
        date_list = value.split('-')
        date_list.reverse()
        value = '/'.join(date_list)
    date_list = value.split('/')
    if len(date_list) != 3:
        raise ValueError('Data inválida.')
    if force_4_digits_year and len(date_list[2]) != 4:
        raise ValueError('O ano deve ter 4 dígitos.')

    format = (not force_4_digits_year and len(date_list[2]) != 4) and '%d/%m/%y' or '%d/%m/%Y'

    return datetime.strptime(value, format).date()


def datetime_to_ordinal(datetime_):
    """
    Converte um datetime para um valor orginal.

    Args:
        datetime_ (datetime): datetime a converter.

    Returns:
        Ordinal do datetime.
    """
    return mktime(datetime_.timetuple())


def ordinal_to_datetime(ordinal_):
    """
    Converte um valor orginal em um datetime.

    Args:
        ordinal_ (int): orninal a converter.

    Returns:
        Ordinal do datetime.
    """
    return datetime.fromtimestamp(ordinal_)


def date2datetime(date_):
    """
    Converte um **date** em um **datetime**.

    Args:
        date_ (date): data a ser convertida.

    Returns:
        Datetime da data passada.
    """
    return datetime(date_.year, date_.month, date_.day)


def strptime_or_default(string, format_, default=None):
    """
    Converte uma string em um datetime. Se não for possível converter o valor default é retornado.

    Args:
        string (string): string a ser convertida;
        format_ (string): formatação a ser utilizada;
        default (datetime): valor default.

    Examples:
        >>> strptime_or_default('20101011', '%Y%m%d')
        datetime.datetime(2010, 10, 11, 0, 0)
        >>> strptime_or_default('20101000', '%Y%m%d')

    Returns:
        Datetime do valor passado ou o valor default.
    """
    try:
        return datetime.strptime(string, format_)
    except Exception:
        return default


def strptime_date_or_default(string, format_, default=None):
    """
    Converte uma string em um date. Se não for possível converter o valor default é retornado.

    Args:
        string (string): string a ser convertida;
        format_ (string): formatação a ser utilizada;
        default (date): valor default.

    Examples:
        >>> strptime_or_default('20101011', '%Y%m%d')
        datetime.datetime(2010, 10, 11, 0, 0)
        >>> strptime_or_default('20101000', '%Y%m%d')

    Returns:
        Date do valor passado ou o valor default.
    """
    try:
        return datetime.strptime(string, format_).date()
    except Exception:
        return default


def get_age(begin, end=None):
    """
    Obtem o número de anos entre duas datas, caso o **end** não seja informado será utilizado a data atual.

    Args:
        begin (datetime): data inicial;
        end (datetime): data final.

    Returns:
        Inteiro com o número de anos entre **begin** e **end**.

    Note:
        Adaptado de
    """

    # adapted from http://stackoverflow.com/questions/765797/python-timedelta-in-years
    def yearsago(years, from_date=None):
        if from_date is None:
            from_date = datetime.now()
        try:
            return from_date.replace(year=from_date.year - years)
        except Exception:
            # Must be 2/29!
            assert from_date.month == 2
            assert from_date.day == 29
            return from_date.replace(month=2, day=28, year=from_date.year - years)

    if isinstance(begin, date):
        begin = date2datetime(begin)
    if end is None:
        end = datetime.now()
    else:
        if isinstance(end, date):
            end = date2datetime(end)

    num_years = int((end - begin).days / 365.25)
    if begin > yearsago(num_years, end):
        return num_years - 1
    else:
        return num_years


def primeiro_dia_da_semana(data_referencia):
    """
    Obtem o primeiro dia da semana com base na data passada.

    Args:
        data_referencia (date|datetime): data de referência.

    Returns:
         Datetime com o primeiro dia da semana.
    """
    return data_referencia - timedelta(data_referencia.weekday())


def years_between(start, end):
    """
    Cálcula o número de anos entre duas datas.

    Args:
        start (datetime): data inicial;
        end (datetime): data final.

    Returns:
        Número de anos.
    """
    if not isinstance(start, datetime):
        start = datetime(start.year, start.month, start.day)
    if not isinstance(end, datetime):
        end = datetime(end.year, end.month, end.day)
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days + 1)):
        yield start_date + timedelta(n)


def adicionar_mes(data, meses=1):
    return data + relativedelta(months=meses)


def datas_entre(data_ini, data_fim, sabado=True, domingo=True):
    """ """
    dias = []
    data_atual = data_ini
    while data_atual <= data_fim:
        if not sabado and data_atual.weekday() == 5:
            data_atual = data_atual + timedelta(1)
            continue
        if not domingo and data_atual.weekday() == 6:
            data_atual = data_atual + timedelta(1)
            continue
        dias.append(data_atual)
        data_atual = data_atual + timedelta(1)
    return dias


def get_qtd_dias_por_ano(periodo_data_inicio, periodo_data_final):
    #
    # dado um período de datas, calcular a quantidade de dias por ano
    qtd_dias_por_ano = {}  # {ano: qtd, ano: qtd, ano: qtd, ...}
    for data in datas_entre(periodo_data_inicio, periodo_data_final):
        ano = data.year
        if ano not in qtd_dias_por_ano:
            qtd_dias_por_ano[ano] = 0
        qtd_dias_por_ano[ano] += 1
    return qtd_dias_por_ano


def get_date(data_str, date_formats: list[str]) -> tuple[date, str]:
    date_result, msg = (None, 'Data não informada.')
    if data_str:
        msg = ''
        for date_formart in date_formats:
            try:
                date_result = datetime.strptime(data_str, date_formart).date()
                msg = ''
                break
            except Exception as error:
                date_result = None
                msg += f'{error}. '
    return date_result, msg


def extrair_periodo(data_ini, data_fim):
    """
    Retorna string que representa o período entre as datas passadas.
    Ex: date(2008, 1, 1), date(2008, 2, 1) --> '01/01/2008 até '01/02/2008'.
    """
    return '{} até {}'.format(data_ini.strftime('%d/%m/%Y'), data_fim.strftime('%d/%m/%Y'))


def formatar_periodo(data_inicio, data_fim=None, hora_inicio=None, hora_fim=None, data_inicio_fallback=None, data_fim_fallback=None):
    """
    Formata um período com datas e horas de forma inteligente.

    Args:
        data_inicio (date|None): Data de início do período
        data_fim (date|None): Data de fim do período
        hora_inicio (time|None): Hora de início
        hora_fim (time|None): Hora de fim
        data_inicio_fallback (date|None): Data de início alternativa (fallback)
        data_fim_fallback (date|None): Data de fim alternativa (fallback)

    Returns:
        str|None: Período formatado ou None se não houver dados suficientes

    Examples:
        >>> formatar_periodo(date(2024, 1, 10))
        '10/01/2024'

        >>> formatar_periodo(date(2024, 1, 10), date(2024, 1, 15))
        '10/01/2024 até 15/01/2024'

        >>> formatar_periodo(date(2024, 1, 10), date(2024, 1, 10), time(8, 0), time(18, 0))
        '10/01/2024 das 08:00 às 18:00'

        >>> formatar_periodo(date(2024, 1, 10), date(2024, 1, 15), time(8, 0), time(18, 0))
        '10/01/2024 às 08:00 até 15/01/2024 às 18:00'
    """
    # Caso 1: Sem data de início, usa as datas de fallback
    if not data_inicio:
        if data_inicio_fallback and data_fim_fallback:
            if data_inicio_fallback == data_fim_fallback:
                return data_inicio_fallback.strftime('%d/%m/%Y')
            else:
                return f'{data_inicio_fallback.strftime("%d/%m/%Y")} até {data_fim_fallback.strftime("%d/%m/%Y")}'
        elif data_inicio_fallback:
            return data_inicio_fallback.strftime('%d/%m/%Y')
        else:
            return None

    # Caso 2: Apenas data de início (sem data fim)
    if not data_fim:
        if hora_inicio:
            return f'{data_inicio.strftime("%d/%m/%Y")} às {hora_inicio.strftime("%H:%M")}'
        else:
            return data_inicio.strftime('%d/%m/%Y')

    # Caso 3: Com data de fim
    # Subcaso 3.1: Sem horas definidas
    if not hora_inicio or not hora_fim:
        return f'{data_inicio.strftime("%d/%m/%Y")} até {data_fim.strftime("%d/%m/%Y")}'

    # Subcaso 3.2: Mesmo dia com horas
    if data_inicio == data_fim:
        return f'{data_inicio.strftime("%d/%m/%Y")} das {hora_inicio.strftime("%H:%M")} às {hora_fim.strftime("%H:%M")}'

    # Subcaso 3.3: Dias diferentes com horas
    return (
        f'{data_inicio.strftime("%d/%m/%Y")} às {hora_inicio.strftime("%H:%M")} até {data_fim.strftime("%d/%m/%Y")} às {hora_fim.strftime("%H:%M")}'
    )


def meses_entre(data_ini, data_fim):
    """
    Exs:
        08/12/2017 a 17/08/2018 >>>> [12, 1, 2, 3, 4, 5, 6, 7, 8]

                                         2016                    2017                          2018
                                      ----------  -------------------------------------  ----------------------
        08/10/2016 a 17/08/2018 >>>> [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    """
    meses = []
    for ano in range(data_ini.year, data_fim.year + 1):
        if ano == data_ini.year:
            meses += list(range(data_ini.month, (12 if data_ini.year != data_fim.year else data_fim.month) + 1))
        elif ano == data_fim.year:
            meses += list(range(1, data_fim.month + 1))
        else:
            meses += list(range(1, 13))
    return meses


def get_parcela_do_ano(data: date | None = None, meses_por_parcela: int = 6) -> int:
    """
    Retorna a "parcela" do ano correspondente à data informada, com base na duração de meses de cada parcela.
    Exemplo: meses_por_parcela=6 retorna o semestre, meses_por_parcela=3 retorna o trimestre.

    :param data: a data a avaliar (valor padrão: date.today())
    :type data: :class:`date`
    :param meses_por_parcela: a quantidade de meses em cada parcela (ex: 6 para semestre, 3 para trimestre, etc.)
    :type meses_por_parcela: :class:`int`
    :returns: o número da parcela (ex: 1 ou 2 para semestres, 1 a 4 para trimestres, etc.)
    :rtype: :class:`int`
    """
    if 12 % meses_por_parcela != 0:
        raise ValueError(f'{meses_por_parcela} deve ser um divisor de 12')
    if not data:
        data = date.today()
    parcela = ceil(data.month / meses_por_parcela)
    return parcela


def get_trimestre(data: date | None = None) -> int:
    """Retorna um valor de 1 a 4, representando o trimestre do ano ao qual a `data` pertence."""
    return get_parcela_do_ano(data, meses_por_parcela=3)


def get_semestre(data: date | None = None) -> int:
    """Retorna o valor 1 ou 2, representando o semestre do ano ao qual a `data` pertence."""
    return get_parcela_do_ano(data, meses_por_parcela=6)


def get_meses_da_parcela_do_ano(parcela: int, meses_por_parcela: int = 6) -> dict[int, str]:
    """
    Retorna um dicionário com os meses correspondentes à parcela do ano, no formato {<número do mês>: <nome do mês>, [...]}.

    Exemplos:
        get_meses_da_parcela_do_ano(1, 3) retorna {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março'}
        get_meses_da_parcela_do_ano(2, 3) retorna {4: 'Abril', 5: 'Maio', 6: 'Junho'}
        get_meses_da_parcela_do_ano(1, 6) retorna {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho'}

    :param parcela: o número da parcela (ex: 1 ou 2 para semestre, 1 a 4 para trimestres, etc.)
    :type parcela: :class:`int`
    :param meses_por_parcela: a quantidade de meses em cada parcela (ex: 6 para semestre, 3 para trimestre, etc.)
    :type meses_por_parcela: :class:`int`
    :returns: um dicionário de meses {numero_mes: nome_mes}
    :rtype: :class:`dict[int, str]`
    :raises ValueError: se o tamanho da parcela não for um divisor de 12
    :raises IndexError: se a parcela estiver fora do intervalo possível para o tamanho da parcela
    """
    if 12 % meses_por_parcela != 0:
        raise ValueError(f'{meses_por_parcela} deve ser um divisor de 12')

    max_parcelas = 12 // meses_por_parcela
    if parcela < 1 or parcela > max_parcelas:
        raise IndexError(f'parcela deve ser um número de 1 a {max_parcelas} para parcelas de {meses_por_parcela} meses.')

    mes_inicial = (parcela - 1) * meses_por_parcela + 1
    mes_final = parcela * meses_por_parcela
    meses = range(mes_inicial, mes_final + 1)

    meses_dict = {num_mes: nome_mes for num_mes, nome_mes in Meses.get_choices() if num_mes in meses}
    return meses_dict


def get_meses_do_trimestre(trimestre: int) -> dict[int, str]:
    """Retorna um dicionário com os meses do trimestre correspondente."""
    return get_meses_da_parcela_do_ano(trimestre, 3)


def get_meses_do_semestre(semestre: int) -> dict[int, str]:
    """Retorna um dicionário com os meses do semestre correspondente."""
    return get_meses_da_parcela_do_ano(semestre, 6)


def formata_segundos(
    segundos,
    str_formato_hora='',
    str_formato_min='',
    str_formato_seg='',
    str_formato_omite_se_zero=False,  # no padrão '%(h)'  # no padrão '%(m)'  # no padrão '%(s)'
):
    try:
        segundos = int(abs(segundos))
    except Exception:
        segundos = -1
    t_hora = segundos // 3600
    aux = segundos % 3600
    t_minuto = aux // 60
    t_segundo = aux % 60
    dic_tempo = {'h': t_hora, 'm': t_minuto, 's': t_segundo}
    #
    if str_formato_hora or str_formato_min or str_formato_seg:
        if str_formato_omite_se_zero:
            str_formato_hora = '' if dic_tempo['h'] == 0 else str_formato_hora
            str_formato_min = '' if dic_tempo['m'] == 0 else str_formato_min
            str_formato_seg = '' if dic_tempo['s'] == 0 else str_formato_seg
        #
        # retorna a string formatada com os valores de hora, min e seg
        h_m_s = f'{str_formato_hora}{str_formato_min}{str_formato_seg}'.format(**dic_tempo)
        if not h_m_s:
            return '0h'
        return h_m_s.strip()
    #
    # retorna o dicionário com os valores de hora, min e seg
    return dic_tempo


def formata_segundos_h_min_seg(segundos):
    return formata_segundos(segundos, '{h}h ', '{m}min ', '{s}seg', True)


def get_hms(from_segundos: int) -> dict[str, int]:
    return formata_segundos(from_segundos)


def get_segundos(from_hms: str) -> int:
    """
    str_hms = '999:999:999'
    """
    hms = from_hms.split(':')
    h: int = int(hms[0]) * 3600
    m: int = int(hms[1]) * 60
    s: int = int(hms[2])
    return h + m + s


def formata_timedelta(
    value: timedelta,
    format_start: str = 'd',  # opções: d, h, m, s, z
    format_days: str = '{d}d',  # ex: '{d:xxxx}'
    format_hours: str = '{h}h',  # ex: '{h:xxxx}'
    format_minutes: str = '{m}m',  # ex: '{m:xxxx}'
    format_seconds: str = '{s}s',  # ex: '{s:xxxx}'
    format_milliseconds: str = '{z}',  # ex: '{z:xxxx}'
    format_sep: str = ' ',
    hide_milliseconds: bool = True,
) -> str:
    days: int = value.days
    hours: int = value.seconds // 3600
    minutes: int = (value.seconds - hours * 3600) // 60
    seconds: int = value.seconds - minutes * 60 - hours * 3600
    milliseconds: int = 0

    if format_start == 'd':
        if hide_milliseconds:
            f_str = f'{format_days}{format_sep}{format_hours}{format_sep}{format_minutes}{format_sep}{format_seconds}'
        else:
            f_str = (
                f'{format_days}{format_sep}{format_hours}{format_sep}{format_minutes}{format_sep}{format_seconds}{format_sep}{format_milliseconds}'
            )
    elif format_start == 'h':
        hours += days * 24
        days = 0
        if hide_milliseconds:
            f_str = f'{format_hours}{format_sep}{format_minutes}{format_sep}{format_seconds}'
        else:
            f_str = f'{format_hours}{format_sep}{format_minutes}{format_sep}{format_seconds}{format_sep}{format_milliseconds}'
    elif format_start == 'm':
        hours += days * 24
        minutes += hours * 60
        days = 0
        hours = 0
        if hide_milliseconds:
            f_str = f'{format_minutes}{format_sep}{format_seconds}'
        else:
            f_str = f'{format_minutes}{format_sep}{format_seconds}{format_sep}{format_milliseconds}'
    elif format_start == 's':
        days = 0
        hours = 0
        minutes = 0
        seconds = int(value.total_seconds())
        if hide_milliseconds:
            f_str = f'{format_seconds}'
        else:
            f_str = f'{format_seconds}{format_sep}{format_milliseconds}'
    elif format_start == 'z':
        days = 0
        hours = 0
        minutes = 0
        seconds = 0
        milliseconds = int(value.total_seconds() * 1000)
        if hide_milliseconds:
            f_str = '?'  # inconsistência nos parâmetros
        else:
            f_str = f'{format_milliseconds}'
    else:
        f_str = '?'  # inconsistência nos parâmetros

    return f_str.format(d=days, h=hours, m=minutes, s=seconds, z=milliseconds)


def proximo_mes(data):
    mes = data.month
    dia = data.day
    while data.month <= mes + 1:
        data = somar_dias(data, 1)
        if data.day == dia:
            data = somar_dias(data, 1)
            break
    data = somar_dias(data, -1)
    return data
