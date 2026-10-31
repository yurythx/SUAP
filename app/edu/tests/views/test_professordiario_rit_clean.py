from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from django.core.exceptions import ValidationError

from edu.forms.diarios import ProfessorDiarioForm
from edu.models.diarios import Diario, ProfessorDiario
from edu.models.professores import Professor
from pit_rit_v2.models import PlanoIndividualTrabalhoV2
from pit_rit_v3.models import PlanoIndividualTrabalhoV3


def _montar_form(periodo_letivo_ch: int | None = None, financiamento_externo: bool = False) -> ProfessorDiarioForm:
    diario = MagicMock()
    diario.pk = 100
    diario.ano_letivo_id = 2026
    diario.periodo_letivo = 1
    diario.situacao = Diario.SITUACAO_ABERTO
    diario.is_semestral_em_calendario_anual.return_value = False
    diario.is_anual.return_value = False
    diario.componente_curricular = None

    form = ProfessorDiarioForm.__new__(ProfessorDiarioForm)
    form.cleaned_data = {
        'diario': diario,
        'vinculo': MagicMock(pk=10),
        'periodo_letivo_ch': periodo_letivo_ch,
        'financiamento_externo': financiamento_externo,
    }
    form.instance = MagicMock()
    form.instance.get_diarios_choque_horario.return_value = []
    return form


class TestProfessorDiarioFormCleanRit:
    def test_clean_bloqueia_quando_rit_v3_publicado_sem_financiamento_externo(self) -> None:
        form = _montar_form(periodo_letivo_ch=1, financiamento_externo=False)
        mock_prof = MagicMock(id=42, tipo=Professor.TIPO_CURSO_REGULAR)

        with (
            patch.object(Professor.objects, 'filter') as mock_prof_filter,
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_prof_filter.return_value.first.return_value = mock_prof
            mock_v3_filter.return_value.exists.return_value = True
            mock_v2_filter.return_value.exists.return_value = False

            with pytest.raises(ValidationError, match=r'Esse professor já possui RIT publicado no período letivo selecionado\.'):
                form.clean()

    def test_clean_bloqueia_quando_rit_v2_publicado_sem_financiamento_externo(self) -> None:
        form = _montar_form(periodo_letivo_ch=2, financiamento_externo=False)
        mock_prof = MagicMock(id=42, tipo=Professor.TIPO_CURSO_REGULAR)

        with (
            patch.object(Professor.objects, 'filter') as mock_prof_filter,
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_prof_filter.return_value.first.return_value = mock_prof
            mock_v3_filter.return_value.exists.return_value = False
            mock_v2_filter.return_value.exists.return_value = True

            with pytest.raises(ValidationError, match=r'Esse professor já possui RIT publicado no período letivo selecionado\.'):
                form.clean()

    def test_clean_permite_quando_rit_v3_publicado_com_financiamento_externo(self) -> None:
        form = _montar_form(periodo_letivo_ch=1, financiamento_externo=True)
        mock_prof = MagicMock(id=42, tipo=Professor.TIPO_CURSO_REGULAR)

        with (
            patch.object(Professor.objects, 'filter') as mock_prof_filter,
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_prof_filter.return_value.first.return_value = mock_prof
            mock_v3_filter.return_value.exists.return_value = True
            mock_v2_filter.return_value.exists.return_value = False

            cleaned_data = form.clean()
            assert cleaned_data == form.cleaned_data

    def test_clean_permite_quando_rit_v2_publicado_com_financiamento_externo(self) -> None:
        form = _montar_form(periodo_letivo_ch=2, financiamento_externo=True)
        mock_prof = MagicMock(id=42, tipo=Professor.TIPO_CURSO_REGULAR)

        with (
            patch.object(Professor.objects, 'filter') as mock_prof_filter,
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_prof_filter.return_value.first.return_value = mock_prof
            mock_v3_filter.return_value.exists.return_value = False
            mock_v2_filter.return_value.exists.return_value = True

            cleaned_data = form.clean()
            assert cleaned_data == form.cleaned_data

    def test_clean_permite_quando_nenhum_rit_publicado(self) -> None:
        form = _montar_form(periodo_letivo_ch=None, financiamento_externo=False)
        mock_prof = MagicMock(id=42, tipo=Professor.TIPO_CURSO_REGULAR)

        with (
            patch.object(Professor.objects, 'filter') as mock_prof_filter,
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_prof_filter.return_value.first.return_value = mock_prof
            mock_v3_filter.return_value.exists.return_value = False
            mock_v2_filter.return_value.exists.return_value = False

            cleaned_data = form.clean()
            assert cleaned_data == form.cleaned_data


class TestProfessorDiarioIsRitPublicado:
    def test_is_rit_publicado_retorna_true_quando_v3_publicado(self) -> None:
        pd = ProfessorDiario(professor_id=15, financiamento_externo=False, periodo_letivo_ch=1)
        diario = MagicMock(ano_letivo_id=2026, periodo_letivo=1)
        diario.is_semestral_segundo_semestre.return_value = False

        with (
            patch.object(ProfessorDiario, 'diario', diario),
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_v3_filter.return_value.exists.return_value = True
            mock_v2_filter.return_value.exists.return_value = False

            assert pd.is_rit_publicado() is True

    def test_is_rit_publicado_retorna_true_quando_v2_publicado(self) -> None:
        pd = ProfessorDiario(professor_id=15, financiamento_externo=False, periodo_letivo_ch=None)
        diario = MagicMock(ano_letivo_id=2026, periodo_letivo=2)
        diario.is_semestral_segundo_semestre.return_value = False

        with (
            patch.object(ProfessorDiario, 'diario', diario),
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_v3_filter.return_value.exists.return_value = False
            mock_v2_filter.return_value.exists.return_value = True

            assert pd.is_rit_publicado() is True

    def test_is_rit_publicado_com_parametros_vinculo_e_diario(self) -> None:
        pd = ProfessorDiario(financiamento_externo=False)
        vinculo = MagicMock(id=99)
        diario = MagicMock(ano_letivo=MagicMock(id=2026), periodo_letivo=1)
        diario.is_semestral_segundo_semestre.return_value = True

        with (
            patch.object(PlanoIndividualTrabalhoV3.objects, 'filter') as mock_v3_filter,
            patch.object(PlanoIndividualTrabalhoV2.objects, 'filter') as mock_v2_filter,
        ):
            mock_v3_filter.return_value.exists.return_value = True
            mock_v2_filter.return_value.exists.return_value = False

            assert pd.is_rit_publicado(vinculo=vinculo, diario=diario) is True

    def test_is_rit_publicado_retorna_false_com_financiamento_externo(self) -> None:
        pd = ProfessorDiario(professor_id=15, financiamento_externo=True)
        assert pd.is_rit_publicado() is False
