"""Setor do primeiro trâmite do processo de progressão (``ProcessoProgressao.calcular_setor_primeiro_tramite``)."""

import pytest
from django.core.exceptions import ValidationError

from comum.utils import get_sigla_reitoria
from progressoes.models import ProcessoProgressao, SiglaSetorPrimeiroTramite
from progressoes.tests.factories import SiglaSetorPrimeiroTramiteFactory
from rh.tests.factories import SetorFactory

pytestmark = pytest.mark.django_db

REITORIA = SiglaSetorPrimeiroTramite.TIPO_REITORIA


def test_campus_usa_a_primeira_sigla_que_encontra_setor_no_campus() -> None:
    SiglaSetorPrimeiroTramiteFactory(sigla='ABC', ordem=1)
    SiglaSetorPrimeiroTramiteFactory(sigla='COGPE', ordem=2)
    SiglaSetorPrimeiroTramiteFactory(sigla='DIAPE', ordem=3)
    campus = SetorFactory(sigla='CAMPUS1')
    SetorFactory(sigla='DIAPE/CAMPUS1', superior=campus)
    cogpe = SetorFactory(sigla='COGPE/CAMPUS1', superior=campus)

    assert ProcessoProgressao.calcular_setor_primeiro_tramite(SetorFactory(sigla='XYZ', superior=campus)) == cogpe


def test_campus_sem_setor_cadastrado_cai_na_reitoria_pela_precedencia() -> None:
    SiglaSetorPrimeiroTramiteFactory(sigla='ABC')
    SiglaSetorPrimeiroTramiteFactory(tipo=REITORIA, sigla='INEXISTENTE', ordem=1)
    SiglaSetorPrimeiroTramiteFactory(tipo=REITORIA, sigla='CODEPE', ordem=2)
    codepe = SetorFactory(sigla='CODEPE', superior=SetorFactory(sigla=get_sigla_reitoria()))
    setor_avaliado = SetorFactory(sigla='XYZ', superior=SetorFactory(sigla='CAMPUS1'))

    assert ProcessoProgressao.calcular_setor_primeiro_tramite(setor_avaliado) == codepe


@pytest.mark.parametrize('cenario', ['sem_unidade_da_reitoria', 'reitoria_sem_setor_configurado', 'avaliado_na_reitoria_sem_setor_configurado'])
def test_sem_setor_de_destino_levanta_erro_de_configuracao(cenario: str) -> None:
    SiglaSetorPrimeiroTramiteFactory(tipo=REITORIA, sigla='CODEPE')
    SiglaSetorPrimeiroTramiteFactory(sigla='ABC')
    reitoria = SetorFactory(sigla=get_sigla_reitoria()) if cenario != 'sem_unidade_da_reitoria' else None
    superior = reitoria if cenario == 'avaliado_na_reitoria_sem_setor_configurado' else SetorFactory(sigla='CAMPUS1')
    setor_avaliado = SetorFactory(sigla='XYZ', superior=superior)

    with pytest.raises(ValidationError, match='inexistente ou mau configurada'):
        ProcessoProgressao.calcular_setor_primeiro_tramite(setor_avaliado)


def test_ordem_repetida_no_mesmo_tipo_e_recusada() -> None:
    SiglaSetorPrimeiroTramiteFactory(sigla='COGPE', ordem=1)
    SiglaSetorPrimeiroTramiteFactory(tipo=REITORIA, sigla='CODEPE', ordem=1)

    with pytest.raises(ValidationError):
        SiglaSetorPrimeiroTramiteFactory.build(sigla='DIAPE', ordem=1).full_clean()
