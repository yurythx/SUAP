"""Número de PA (Processo Administrativo): máscara, widget e validação.

Tudo aqui é lógica de formulário pura — nenhum teste precisa de banco.
"""

import pytest
from django.forms import ValidationError

from patrimonio.utils import NumeroPAField, NumeroPAWidget, mask_numeropa


class TestMaskNumeroPA:
    def test_insere_o_literal_pa_depois_do_ano(self):
        assert mask_numeropa('1234123456') == '1234PA123456'

    def test_aceita_valor_nao_string(self):
        assert mask_numeropa(1234123456) == '1234PA123456'


class TestNumeroPAWidget:
    def test_renderiza_o_valor_cru_com_mascara(self):
        html = NumeroPAWidget().render('numero_pa', '1234123456')
        assert 'value="1234PA123456"' in html

    def test_renderiza_o_valor_ja_mascarado_sem_alterar(self):
        html = NumeroPAWidget().render('numero_pa', '1234PA123456')
        assert 'value="1234PA123456"' in html

    def test_renderiza_vazio_quando_nao_ha_valor(self):
        html = NumeroPAWidget().render('numero_pa', '')
        assert 'numeropa-widget' in html


class TestNumeroPAField:
    def test_valor_vazio_vira_string_vazia(self):
        assert NumeroPAField(required=False).clean('') == ''

    def test_valor_cru_e_normalizado_para_o_formato_com_pa(self):
        assert NumeroPAField().clean('1234123456') == '1234PA123456'

    def test_valor_ja_no_formato_e_preservado(self):
        assert NumeroPAField().clean('1234PA123456') == '1234PA123456'

    @pytest.mark.parametrize(
        'valor',
        [
            '123',  # curto demais
            '1234PA1234567',  # longo demais
            'ABCDPA123456',  # ano não numérico
            '1234PA12345X',  # sequência não numérica
        ],
    )
    def test_formato_invalido_e_recusado(self, valor):
        with pytest.raises(ValidationError):
            NumeroPAField().clean(valor)

    def test_help_text_orienta_o_formato_esperado(self):
        assert NumeroPAField().help_text == 'Formato: "9999PA123456"'
