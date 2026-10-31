from decimal import Decimal

import pytest

from djtools.templatetags.filters.utils import format_bool, format_money, format_money_almox, format_profile, format_quantity
from djtools.utils import normalizar_nome_proprio
from rh.models import Pessoa
from rh.tests.factories import PessoaFisicaFactory, PessoaJuridicaFactory


class FormatMoneyAlmoxTestCase:
    def test_none(self):
        assert format_money_almox(None) == '-'

    def test_vazio(self):
        assert format_money_almox('') == '-'

    def test_zero(self):
        assert format_money_almox(Decimal('0')) == '0,00'

    def test_inteiro(self):
        assert format_money_almox(1) == '1,00'

    def test_milhar(self):
        assert format_money_almox(Decimal('1000.50000')) == '1.000,50'

    def test_mantem_seis_casas_decimais(self):
        assert format_money_almox(Decimal('900.975458')) == '900,975458'

    def test_trunca_alem_de_seis_casas_decimais(self):
        # total do item: qtd (5 casas) x valor unitário (6 casas) = até 11 casas
        assert format_money_almox(Decimal('900.98446775458')) == '900,984467'

    def test_negativo(self):
        assert format_money_almox(Decimal('-1234.5')) == '-1.234,50'

    def test_zero_em_notacao_cientifica(self):
        assert format_money_almox(Decimal('0E-11')) == '0,00'

    def test_valor_pequeno_em_notacao_cientifica(self):
        assert format_money_almox(Decimal('1.23E-9')) == '0,00'


class FormatMoneyTestCase:
    def test_zero_em_notacao_cientifica(self):
        # regressão: 0E-11 virava '-0.E11,00' no balancete de elemento de despesa
        assert format_money(Decimal('0E-11')) == '0,00'

    def test_valor_pequeno_em_notacao_cientifica(self):
        assert format_money(Decimal('1.23E-9')) == '0,00'

    def test_expoente_positivo(self):
        assert format_money(Decimal('1E+3')) == '1.000,00'


class FormatQuantityTestCase:
    def test_zero_em_notacao_cientifica(self):
        assert format_quantity(Decimal('0E-11')) == '0'

    def test_valor_pequeno_em_notacao_cientifica(self):
        assert format_quantity(Decimal('1.23E-9')) == '0,00000000123'

    def test_expoente_positivo(self):
        assert format_quantity(Decimal('1E+3')) == '1.000'


class FormatBoolTestCase:
    def test_true_with_html(self):
        result = format_bool(True)
        assert 'Sim' in result
        assert 'success' in result

    def test_false_with_html(self):
        result = format_bool(False)
        assert 'N\u00e3o' in result
        assert 'error' in result

    def test_true_without_html(self):
        assert format_bool(True, html=False) == 'Sim'

    def test_false_without_html(self):
        assert format_bool(False, html=False) == 'N\u00e3o'

    def test_html_structure_true(self):
        result = format_bool(True)
        assert result == '<span class="status status-success">Sim</span>'

    def test_html_structure_false(self):
        result = format_bool(False)
        assert result == '<span class="status status-error">N\u00e3o</span>'

    def test_truthy_value(self):
        result = format_bool(1)
        assert 'Sim' in result

    def test_falsy_value(self):
        result = format_bool(0)
        assert 'N\u00e3o' in result

    def test_truthy_value_no_html(self):
        assert format_bool(1, html=False) == 'Sim'

    def test_falsy_value_no_html(self):
        assert format_bool(0, html=False) == 'N\u00e3o'


@pytest.mark.django_db
def test_format_profile_de_pessoa_fisica_e_juridica_nao_consulta_o_banco(django_assert_num_queries) -> None:
    """A própria PessoaFisica/PessoaJuridica é o perfil: nada de ir ao banco pelo descritor reverso (#17700)."""
    pessoa_fisica = PessoaFisicaFactory(nome='MARIA DA SILVA', nome_usual='Maria Silva')
    pessoa_juridica = PessoaJuridicaFactory(nome='ACME LTDA')

    with django_assert_num_queries(0):
        html_fisica = format_profile(pessoa_fisica)
        html_juridica = format_profile(pessoa_juridica)

    assert f'data-profile-id="{pessoa_fisica.uuid}">Maria Silva</a>' in html_fisica
    assert f'data-profile-id="{pessoa_juridica.uuid}">{normalizar_nome_proprio(str(pessoa_juridica))}</a>' in html_juridica
    # Mesma saída da Pessoa genérica, que resolve o perfil concreto pelo descritor reverso.
    assert html_fisica == format_profile(Pessoa.objects.get(pk=pessoa_fisica.pk))
    assert html_juridica == format_profile(Pessoa.objects.get(pk=pessoa_juridica.pk))
