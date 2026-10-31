import pytest

from unittest.mock import MagicMock, patch
import datetime

from django.contrib.admin.sites import site

from edu.admin.diarios import ConfiguracaoAvaliacaoAdmin
from edu.models.diarios import Falta
from edu.models.procedimentos import AbonoFaltas, MotivoAusenciaEscolar


@pytest.fixture
def motivo_com_previsao_normativa():
    return MotivoAusenciaEscolar(
        id=1,
        descricao='Motivo com previsao',
        possui_previsao_normativa=True,
        reposicao_obrigatoria=False,
        ativo=True,
    )


@pytest.fixture
def motivo_sem_previsao_normativa():
    return MotivoAusenciaEscolar(
        id=2,
        descricao='Motivo sem previsao',
        possui_previsao_normativa=False,
        reposicao_obrigatoria=False,
        ativo=True,
    )


def test_falta_com_abono_deferido_e_previsto_nao_deve_contabilizar(motivo_com_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_com_previsao_normativa)
    falta = Falta()
    falta.abono_faltas = abono
    falta.contabilizar = not falta.abono_faltas.deve_abonar_faltas()

    assert falta.contabilizar is False


def test_falta_com_abono_deferido_sem_previsao_deve_contabilizar(motivo_sem_previsao_normativa):
    abono = AbonoFaltas(deferido=True, motivo_ausencia_escolar=motivo_sem_previsao_normativa)
    falta = Falta()
    falta.abono_faltas = abono
    falta.contabilizar = not falta.abono_faltas.deve_abonar_faltas()

    assert falta.contabilizar is True


def test_falta_sem_abono_mantem_campo_abono_vazio():
    falta = Falta()
    falta.abono_faltas = None

    assert falta.abono_faltas is None


@pytest.mark.django_db
@patch('edu.admin.diarios.ItemConfiguracaoAvaliacao.objects.filter')
@patch('edu.models.AbonoFaltas.objects.filter')
def test_after_saving_model_and_related_inlines_gera_reposicao(mock_abono_filter, mock_item_filter):
    # Setup mocks
    mock_item = MagicMock()
    mock_item.data = datetime.date(2023, 5, 5)
    mock_item_filter.return_value = [mock_item]

    mock_abono = MagicMock()
    mock_abono_filter.return_value.distinct.return_value = [mock_abono]

    # Executa a funcao
    obj = MagicMock()
    admin_instance = ConfiguracaoAvaliacaoAdmin(model=MagicMock(), admin_site=site)
    admin_instance.after_saving_model_and_related_inlines(obj)

    # Verifica
    mock_abono.checar_solicitacoes_reposicao_atividade.assert_called_once()
