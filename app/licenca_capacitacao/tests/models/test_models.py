from licenca_capacitacao.models import CalculoAquisitivoUsofrutoServidorEdital


class TestCalculoAquisitivoUsofrutoServidorEdital:
    """Tests for CalculoAquisitivoUsofrutoServidorEdital model."""

    def test_seach_fields_defined(self):
        assert hasattr(CalculoAquisitivoUsofrutoServidorEdital, 'SEARCH_FIELDS')

    def test_search_fields_content(self):
        expected = ['edital__titulo', 'servidor__pessoa_fisica__nome']
        assert expected == CalculoAquisitivoUsofrutoServidorEdital.SEARCH_FIELDS
