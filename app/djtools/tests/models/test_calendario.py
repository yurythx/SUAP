from datetime import date, datetime

import pytest

from djtools.utils.calendario import formata_segundos, get_age
from ponto.compensacao import formatar_segundos


@pytest.mark.parametrize(
    ('begin', 'end', 'expected'),
    [
        (datetime(2020, 1, 1), datetime(2020, 1, 1), 0),
        (datetime(2020, 1, 1), datetime(2021, 1, 1), 1),
        (date(2000, 6, 15), date(2023, 1, 1), 22),
        (date(2000, 1, 15), date(2023, 6, 1), 23),
        (date(2000, 2, 29), date(2023, 3, 1), 23),
        (date(2000, 2, 29), date(2023, 2, 28), 22),
        (date(2010, 5, 10), datetime(2020, 5, 10), 10),
        (datetime(2010, 5, 10), date(2020, 5, 10), 10),
        (date(2000, 1, 1), date(2050, 1, 1), 50),
        (date(2023, 6, 1), date(2023, 12, 31), 0),
    ],
)
def test_get_age(begin, end, expected):
    assert get_age(begin, end) == expected


def test_get_age_without_end_uses_now():
    age = get_age(date(2000, 1, 1))
    assert isinstance(age, int)
    assert age >= 0


@pytest.mark.parametrize(
    ('seconds', 'h_fmt', 'm_fmt', 's_fmt', 'omit_zero', 'expected'),
    [
        (3661, None, None, None, False, {'h': 1, 'm': 1, 's': 1}),
        (0, None, None, None, False, {'h': 0, 'm': 0, 's': 0}),
        (-3661, None, None, None, False, {'h': 1, 'm': 1, 's': 1}),
        (3661, '{h}h ', None, None, False, '1h'),
        (3661, '{h}h ', '{m}min ', '{s}seg', False, '1h 1min 1seg'),
        (3600, '{h}h ', '{m}min ', '{s}seg', True, '1h'),
        (61, '{h}h ', '{m}min ', '{s}seg', True, '1min 1seg'),
        (0, '{h}h ', '{m}min ', '{s}seg', True, '0h'),
        (100000, None, None, None, False, {'h': 27, 'm': 46, 's': 40}),
        (42, None, None, None, False, {'h': 0, 'm': 0, 's': 42}),
        (120, None, None, None, False, {'h': 0, 'm': 2, 's': 0}),
    ],
)
def test_formata_segundos(seconds, h_fmt, m_fmt, s_fmt, omit_zero, expected):
    if h_fmt is None:
        result = formata_segundos(seconds)
    elif m_fmt is None and s_fmt is None:
        result = formata_segundos(seconds, str_formato_hora=h_fmt)
    else:
        result = formata_segundos(
            seconds,
            h_fmt,
            m_fmt,
            s_fmt,
            str_formato_omite_se_zero=omit_zero,
        )
    assert result == expected


@pytest.mark.parametrize(
    ('seconds', 'add_suffix', 'omit_zero', 'expected'),
    [
        (3661, True, False, '1h 1min 1seg'),
        (3661, False, False, '01:01:01'),
        (0, False, False, '00:00:00'),
        (0, True, False, '0h 0min 0seg'),
        (0, True, True, '0h'),
        (3600, True, True, '1h'),
        (120, True, True, '2min'),
        (100000, False, False, '27:46:40'),
    ],
)
def test_formatar_segundos(seconds, add_suffix, omit_zero, expected):
    result = formatar_segundos(seconds, add_sufixos_h_min_seg=add_suffix, omite_se_zero=omit_zero)
    assert result == expected


def test_formatar_segundos_defaults_to_zero():
    assert formatar_segundos() == '00:00:00'
