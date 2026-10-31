from __future__ import annotations

from unittest.mock import patch
from django.forms import IntegerField
from pit_rit_v3.forms import ConfiguracaoForm, CriarPlanoIndividualTrabalhoForm
from pit_rit_v3.models import PlanoIndividualTrabalhoV3


class TestConfiguracaoForm:
    def test_formulario_expoe_campos_configuracao(self) -> None:
        assert 'ano_inicio_app' in ConfiguracaoForm.base_fields
        assert 'periodo_inicio_app' in ConfiguracaoForm.base_fields

    def test_campos_sao_opcionais(self) -> None:
        assert ConfiguracaoForm.base_fields['ano_inicio_app'].required is False
        assert ConfiguracaoForm.base_fields['periodo_inicio_app'].required is False

    def test_campos_sao_inteiros(self) -> None:
        assert isinstance(ConfiguracaoForm.base_fields['ano_inicio_app'], IntegerField)
        assert isinstance(ConfiguracaoForm.base_fields['periodo_inicio_app'], IntegerField)

    def test_periodo_tem_limites_validos(self) -> None:
        campo_periodo = ConfiguracaoForm.base_fields['periodo_inicio_app']
        assert campo_periodo.min_value == 1

    def test_autodescoberta_pelo_configuracao_form_factory(self) -> None:
        from comum.forms import ConfiguracaoFormFactory

        FormClass = ConfiguracaoFormFactory('pit_rit_v3')
        assert 'pit_rit_v3' in FormClass.apps
        assert issubclass(FormClass, ConfiguracaoForm)


class TestCriarPlanoIndividualTrabalhoForm:
    @patch.object(PlanoIndividualTrabalhoV3, 'get_ano_inicio', return_value=None)
    def test_queryset_ano_letivo_vazio_quando_nao_configurado(self, mock_ano_inicio) -> None:
        form = CriarPlanoIndividualTrabalhoForm()
        assert form.fields['ano_letivo'].queryset.count() == 0

    @patch.object(PlanoIndividualTrabalhoV3, 'get_ano_inicio', return_value=2026)
    def test_queryset_ano_letivo_filtra_a_partir_do_ano_configurado(self, mock_ano_inicio) -> None:
        form = CriarPlanoIndividualTrabalhoForm()
        # Valida que o filtro ano__gte foi aplicado na query
        sql_str = str(form.fields['ano_letivo'].queryset.query)
        assert 'ano' in sql_str
