from datetime import date

import pytest

from djtools.utils.python import (
    agrupar_em_pares,
    b64decode,
    b64encode,
    dict_from_keys_n_values,
    diferenca_listas,
    djtools_max,
    djtools_min,
    existe_conflito_entre_intervalos,
    get_values_from_choices,
    getattr_coalesce,
    ha_choque_de_periodo,
    random_with_N_digits,
    rgetattr,
    rhasattr,
    silenciar,
    similaridade,
)
from djtools.utils.python import randomic as randomic_func


class TestSimilaridade:
    def test_identical_strings(self):
        assert similaridade('abc', 'abc') == 1.0

    def test_completely_different(self):
        assert similaridade('abc', 'xyz') == 0.0

    def test_partial_similarity(self):
        assert similaridade('abc', 'abd') > 0


class TestDjtoolsMax:
    def test_basic(self):
        assert djtools_max(1, 2, 3) == 3

    def test_with_none(self):
        assert djtools_max(1, None, 3) == 3

    def test_all_none(self):
        with pytest.raises(ValueError):
            djtools_max(None, None)

    def test_single_value(self):
        assert djtools_max(42) == 42


class TestDjtoolsMin:
    def test_basic(self):
        assert djtools_min(3, 1, 2) == 1

    def test_with_none(self):
        assert djtools_min(3, None, 1) == 1

    def test_single_value(self):
        assert djtools_min(42) == 42


class TestSilenciar:
    def test_silenced_returns_default(self):
        @silenciar(silenciar_debug=True, return_on_error='default')
        def failing():
            raise ValueError('erro')

        assert failing() == 'default'

    def test_successful_call_returns_value(self):
        @silenciar(silenciar_debug=True)
        def working():
            return 42

        assert working() == 42


class TestGetattrCoalesce:
    def test_dotted_attr(self):
        obj = type('A', (), {'b': type('B', (), {'c': 42})()})()
        assert getattr_coalesce(obj, 'b.c') == 42

    def test_missing_attr_returns_default(self):
        obj = type('A', (), {})()
        assert getattr_coalesce(obj, 'missing', 'fallback') == 'fallback'


class TestRgetattr:
    def test_nested_attr(self):
        obj = type('A', (), {'b': type('B', (), {'c': 42})()})()
        assert rgetattr(obj, 'b.c') == 42

    def test_missing_returns_none(self):
        obj = type('A', (), {})()
        assert rgetattr(obj, 'missing') is None

    def test_top_level(self):
        obj = type('A', (), {'x': 10})()
        assert rgetattr(obj, 'x') == 10


class TestRhasattr:
    def test_single_level_exists(self):
        obj = type('A', (), {'b': 42})()
        assert rhasattr(obj, 'b') is True

    def test_single_level_not_exists(self):
        obj = type('A', (), {})()
        assert rhasattr(obj, 'missing') is False


class TestRandomWithNDigits:
    def test_correct_number_of_digits(self):
        result = random_with_N_digits(4)
        assert 1000 <= result <= 9999

    def test_1_digit(self):
        result = random_with_N_digits(1)
        assert 1 <= result <= 9


class TestRandomic:
    def test_correct_length(self):
        assert len(randomic_func(10)) == 10

    def test_custom_length(self):
        assert len(randomic_func(20)) == 20


class TestDictFromKeysNValues:
    def test_basic(self):
        result = dict_from_keys_n_values(['a', 'b'], [1, 2])
        assert result == {'a': 1, 'b': 2}

    def test_empty(self):
        assert dict_from_keys_n_values([], []) == {}


class TestB64EncodeDecode:
    def test_string_roundtrip(self):
        original = 'hello world'
        encoded = b64encode(original)
        decoded = b64decode(encoded)
        assert decoded == original

    def test_bytes_roundtrip(self):
        original = b'hello world'
        encoded = b64encode(original)
        decoded = b64decode(encoded)
        assert decoded == original

    def test_raises_on_invalid_input(self):
        with pytest.raises(Exception):  # noqa
            b64encode(42)


class TestDiferencaListas:
    def test_basic(self):
        assert set(diferenca_listas([1, 2, 3], [2, 3, 4])) == {1}

    def test_identical(self):
        assert diferenca_listas([1, 2], [1, 2]) == []


class TestAgruparEmPares:
    def test_even_count(self):
        assert agrupar_em_pares([0, 1, 2, 3, 4, 5]) == [[0, 1], [2, 3], [4, 5]]

    def test_odd_count(self):
        assert agrupar_em_pares([0, 1, 2, 3, 4]) == [[0, 1], [2, 3], [4]]

    def test_empty(self):
        assert agrupar_em_pares([]) == []


class TestExisteConflitoEntreIntervalos:
    def test_no_conflict(self):
        assert existe_conflito_entre_intervalos([date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 15), date(2024, 1, 20)]) is False

    def test_with_conflict(self):
        assert existe_conflito_entre_intervalos([date(2024, 1, 1), date(2024, 1, 15), date(2024, 1, 10), date(2024, 1, 20)]) is True


class TestHaChoqueDePeriodo:
    def test_no_choque(self):
        periodos = [(date(2024, 1, 1), date(2024, 1, 10))]
        teste = (date(2024, 1, 15), date(2024, 1, 20))
        assert ha_choque_de_periodo(periodos, teste) is False

    def test_with_choque(self):
        periodos = [(date(2024, 1, 5), date(2024, 1, 15))]
        teste = (date(2024, 1, 10), date(2024, 1, 20))
        assert ha_choque_de_periodo(periodos, teste) is True

    def test_touching_edges(self):
        periodos = [(date(2024, 1, 1), date(2024, 1, 10))]
        teste = (date(2024, 1, 10), date(2024, 1, 20))
        assert ha_choque_de_periodo(periodos, teste) is True


class TestGetValuesFromChoices:
    def test_single_key(self):
        choices = [(1, 'Um'), (2, 'Dois'), (3, 'Três')]
        assert get_values_from_choices(1, choices) == 'Um'

    def test_multiple_keys(self):
        choices = [(1, 'Um'), (2, 'Dois'), (3, 'Três')]
        assert get_values_from_choices([1, 3], choices) == ['Um', 'Três']
