from datetime import date, datetime, timedelta

from djtools.utils.calendario import (
    DateInterval,
    adicionar_mes,
    daterange,
    datas_entre,
    date2datetime,
    date_to_string,
    eh_bissexto,
    extrair_periodo,
    formatar_periodo,
    formata_segundos,
    formata_segundos_h_min_seg,
    formata_timedelta,
    get_age,
    get_date,
    get_hms,
    get_parcela_do_ano,
    get_meses_da_parcela_do_ano,
    get_qtd_dias_por_ano,
    get_segundos,
    get_trimestre,
    get_semestre,
    intervalo_intersecao,
    is_final_de_semana,
    get_meses_do_trimestre,
    get_meses_do_semestre,
    meses_entre,
    primeiro_dia_da_semana,
    proximo_mes,
    somar_dias,
    str_to_dateBR,
    strptime_date_or_default,
    strptime_or_default,
    ultimo_dia,
    ultimo_dia_date,
    years_between,
)
import pytest


class TestSomarDias:
    def test_add_days(self):
        d = date(2024, 1, 1)
        assert somar_dias(d, 10) == date(2024, 1, 11)

    def test_subtract_days(self):
        d = date(2024, 1, 10)
        assert somar_dias(d, -5) == date(2024, 1, 5)


class TestIsFinalDeSemana:
    def test_saturday(self):
        assert is_final_de_semana(date(2024, 1, 6)) is True

    def test_sunday(self):
        assert is_final_de_semana(date(2024, 1, 7)) is True

    def test_monday(self):
        assert is_final_de_semana(date(2024, 1, 8)) is False

    def test_friday(self):
        assert is_final_de_semana(date(2024, 1, 5)) is False


class TestEhBissexto:
    def test_2024_is_leap(self):
        assert eh_bissexto(2024) is True

    def test_2023_not_leap(self):
        assert eh_bissexto(2023) is False

    def test_2000_is_leap(self):
        assert eh_bissexto(2000) is True

    def test_2100_not_leap(self):
        assert eh_bissexto(2100) is False


class TestUltimoDia:
    def test_january(self):
        assert ultimo_dia(1, 2024) == 31

    def test_february_leap(self):
        assert ultimo_dia(2, 2024) == 29

    def test_february_non_leap(self):
        assert ultimo_dia(2, 2023) == 28

    def test_april(self):
        assert ultimo_dia(4, 2024) == 30


class TestUltimoDiaDate:
    def test_february_leap(self):
        assert ultimo_dia_date(2, 2024) == date(2024, 2, 29)

    def test_december(self):
        assert ultimo_dia_date(12, 2024) == date(2024, 12, 31)


class TestDateToString:
    def test_format(self):
        assert date_to_string(date(2024, 1, 5)) == '05/01/2024'


class TestDateInterval:
    def test_contains(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        assert di.contains(date(2024, 1, 5)) is True
        assert di.contains(date(2024, 1, 15)) is False

    def test_intersects(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        other = DateInterval(date(2024, 1, 5), date(2024, 1, 15))
        assert di.intersects(other) is True

    def test_not_intersects(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        other = DateInterval(date(2024, 1, 15), date(2024, 1, 20))
        assert di.intersects(other) is False

    def test_intersection(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        other = DateInterval(date(2024, 1, 5), date(2024, 1, 15))
        result = di.intersection(other)
        assert result == DateInterval(date(2024, 1, 5), date(2024, 1, 10))

    def test_days(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        assert di.days() == 10

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError):
            DateInterval(date(2024, 1, 10), date(2024, 1, 1))

    def test_str(self):
        di = DateInterval(date(2024, 1, 1), date(2024, 1, 10))
        assert str(di) == '[2024-01-01 → 2024-01-10]'


class TestStrToDateBR:
    def test_dd_mm_yyyy(self):
        assert str_to_dateBR('05/01/2024') == date(2024, 1, 5)

    def test_yyyy_mm_dd(self):
        assert str_to_dateBR('2024-01-05') == date(2024, 1, 5)

    def test_raises_on_invalid_date(self):
        with pytest.raises(ValueError):
            str_to_dateBR('99/99/9999')

    def test_raises_on_2_digit_year(self):
        with pytest.raises(ValueError):
            str_to_dateBR('05/01/24')


class TestDate2Datetime:
    def test_conversion(self):
        result = date2datetime(date(2024, 1, 5))
        assert result == datetime(2024, 1, 5, 0, 0, 0)


class TestStrptimeOrDefault:
    def test_valid_date(self):
        result = strptime_or_default('20240105', '%Y%m%d')
        assert result == datetime(2024, 1, 5, 0, 0)

    def test_invalid_date_returns_default(self):
        result = strptime_or_default('not-a-date', '%Y%m%d')
        assert result is None

    def test_custom_default(self):
        result = strptime_or_default('not-a-date', '%Y%m%d', default='fallback')
        assert result == 'fallback'


class TestStrptimeDateOrDefault:
    def test_valid_date(self):
        result = strptime_date_or_default('20240105', '%Y%m%d')
        assert result == date(2024, 1, 5)

    def test_invalid_returns_default(self):
        result = strptime_date_or_default('invalid', '%Y%m%d')
        assert result is None


class TestGetAge:
    def test_exact_years(self):
        begin = date(2000, 1, 1)
        end = date(2024, 1, 1)
        assert get_age(begin, end) == 24

    def test_before_birthday(self):
        begin = date(2000, 6, 15)
        end = date(2024, 1, 1)
        assert get_age(begin, end) == 23


class TestPrimeiroDiaDaSemana:
    def test_wednesday(self):
        d = date(2024, 1, 3)
        assert primeiro_dia_da_semana(d) == date(2024, 1, 1)

    def test_sunday(self):
        d = date(2024, 1, 7)
        assert primeiro_dia_da_semana(d) == date(2024, 1, 1)


class TestYearsBetween:
    def test_exact(self):
        assert years_between(date(2000, 1, 1), date(2024, 1, 1)) == 24

    def test_less_than_year(self):
        assert years_between(date(2024, 1, 1), date(2024, 6, 15)) == 0


class TestDaterange:
    def test_generates_range(self):
        result = list(daterange(date(2024, 1, 1), date(2024, 1, 5)))
        assert len(result) == 5
        assert result[0] == date(2024, 1, 1)
        assert result[-1] == date(2024, 1, 5)

    def test_single_day(self):
        result = list(daterange(date(2024, 1, 1), date(2024, 1, 1)))
        assert result == [date(2024, 1, 1)]


class TestAdicionarMes:
    def test_add_month(self):
        assert adicionar_mes(date(2024, 1, 15)) == date(2024, 2, 15)

    def test_add_multiple_months(self):
        assert adicionar_mes(date(2024, 1, 15), meses=3) == date(2024, 4, 15)

    def test_year_rollover(self):
        assert adicionar_mes(date(2024, 11, 15), meses=2) == date(2025, 1, 15)


class TestDatasEntre:
    def test_all_days(self):
        result = datas_entre(date(2024, 1, 1), date(2024, 1, 5))
        assert len(result) == 5

    def test_exclude_saturday(self):
        d = date(2024, 1, 5)
        result = datas_entre(d, d + timedelta(days=2), sabado=False)
        assert date(2024, 1, 6) not in result

    def test_exclude_sunday(self):
        d = date(2024, 1, 6)
        result = datas_entre(d, d + timedelta(days=2), domingo=False)
        assert date(2024, 1, 7) not in result


class TestGetQtdDiasPorAno:
    def test_same_year(self):
        result = get_qtd_dias_por_ano(date(2024, 1, 1), date(2024, 12, 31))
        assert result[2024] == 366


class TestGetDate:
    def test_valid_date(self):
        result, msg = get_date('05/01/2024', ['%d/%m/%Y'])
        assert result == date(2024, 1, 5)
        assert msg == ''

    def test_invalid_date(self):
        result, msg = get_date('', ['%d/%m/%Y'])
        assert result is None
        assert msg == 'Data não informada.'


class TestExtrairPeriodo:
    def test_format(self):
        result = extrair_periodo(date(2024, 1, 1), date(2024, 2, 1))
        assert result == '01/01/2024 até 01/02/2024'


class TestFormatarPeriodo:
    def test_only_start_date(self):
        assert formatar_periodo(date(2024, 1, 10)) == '10/01/2024'

    def test_start_and_end(self):
        assert formatar_periodo(date(2024, 1, 10), date(2024, 1, 15)) == '10/01/2024 até 15/01/2024'

    def test_same_day_with_hours(self):
        from datetime import time

        assert formatar_periodo(date(2024, 1, 10), date(2024, 1, 10), time(8, 0), time(18, 0)) == '10/01/2024 das 08:00 às 18:00'


class TestMesesEntre:
    def test_same_year(self):
        assert meses_entre(date(2024, 1, 1), date(2024, 3, 1)) == [1, 2, 3]

    def test_cross_year(self):
        result = meses_entre(date(2023, 11, 1), date(2024, 2, 1))
        assert result == [11, 12, 1, 2]


class TestMesesDoTrimestre:
    def test_q1(self):
        assert get_meses_do_trimestre(1) == {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março'}

    def test_q4(self):
        assert get_meses_do_trimestre(4) == {10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}

    def test_invalid_raises(self):
        with pytest.raises(IndexError):
            get_meses_do_trimestre(5)


class TestMesesDoSemestre:
    def test_s1(self):
        assert get_meses_do_semestre(1) == {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho'}

    def test_s2(self):
        assert get_meses_do_semestre(2) == {7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}

    def test_invalid_raises(self):
        with pytest.raises(IndexError):
            get_meses_do_semestre(3)


class TestMesesDaParcelaDoAno:
    def test_bimestre(self):
        # 1º bimestre: Jan, Fev
        assert get_meses_da_parcela_do_ano(1, 2) == {1: 'Janeiro', 2: 'Fevereiro'}
        # 6º bimestre: Nov, Dez
        assert get_meses_da_parcela_do_ano(6, 2) == {11: 'Novembro', 12: 'Dezembro'}

    def test_quadrimestre(self):
        # 2º quadrimestre: Mai, Jun, Jul, Ago
        assert get_meses_da_parcela_do_ano(2, 4) == {5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto'}

    def test_invalid_raises(self):
        with pytest.raises(IndexError):
            get_meses_da_parcela_do_ano(7, 2)


class TestGetTrimestre:
    def test_january(self):
        assert get_trimestre(date(2024, 1, 15)) == 1

    def test_december(self):
        assert get_trimestre(date(2024, 12, 25)) == 4


class TestGetSemestre:
    def test_january(self):
        assert get_semestre(date(2024, 1, 15)) == 1

    def test_july(self):
        assert get_semestre(date(2024, 7, 15)) == 2


class TestGetParcelaDoAno:
    def test_bimestre(self):
        assert get_parcela_do_ano(date(2024, 1, 15), 2) == 1
        assert get_parcela_do_ano(date(2024, 3, 15), 2) == 2
        assert get_parcela_do_ano(date(2024, 12, 15), 2) == 6

    def test_quadrimestre(self):
        assert get_parcela_do_ano(date(2024, 1, 15), 4) == 1
        assert get_parcela_do_ano(date(2024, 5, 15), 4) == 2
        assert get_parcela_do_ano(date(2024, 9, 15), 4) == 3


class TestFormataSegundos:
    def test_returns_dict_by_default(self):
        result = formata_segundos(3661)
        assert result == {'h': 1, 'm': 1, 's': 1}

    def test_with_format_strings(self):
        result = formata_segundos(3661, '{h}h ', '{m}min ', '{s}seg')
        assert '1h ' in result
        assert '1min ' in result
        assert '1seg' in result


class TestFormataSegundosHMinSeg:
    def test_format(self):
        result = formata_segundos_h_min_seg(3661)
        assert result == '1h 1min 1seg'


class TestGetHms:
    def test_conversion(self):
        assert get_hms(3661) == {'h': 1, 'm': 1, 's': 1}


class TestGetSegundos:
    def test_conversion(self):
        assert get_segundos('1:1:1') == 3661


class TestFormataTimedelta:
    def test_default_format(self):
        td = timedelta(days=1, hours=2, minutes=30)
        assert formata_timedelta(td) == '1d 2h 30m 0s'

    def test_hours_format(self):
        td = timedelta(days=1, hours=2)
        result = formata_timedelta(td, format_start='h')
        assert '26h' in result

    def test_seconds_format(self):
        td = timedelta(hours=1, minutes=30)
        result = formata_timedelta(td, format_start='s')
        assert '5400' in result


class TestProximoMes:
    def test_next_month(self):
        result = proximo_mes(date(2024, 1, 15))
        assert result.month == 2
        assert 1 <= result.day <= 31


class TestIntervaloIntersecao:
    def test_overlapping(self):
        result = intervalo_intersecao(date(2024, 1, 1), date(2024, 1, 15), date(2024, 1, 10), date(2024, 1, 20))
        assert result == (date(2024, 1, 10), date(2024, 1, 15))

    def test_non_overlapping(self):
        result = intervalo_intersecao(date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 15), date(2024, 1, 20))
        assert result == (None, None)

    def test_touching(self):
        result = intervalo_intersecao(date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 10), date(2024, 1, 20))
        assert result == (date(2024, 1, 10), date(2024, 1, 10))
