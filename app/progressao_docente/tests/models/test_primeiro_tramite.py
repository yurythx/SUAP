"""Setor do primeiro trâmite do processo de progressão (``ProgressaoDocente.calcular_setor_primeiro_tramite``)."""

import pytest
from django.core.exceptions import ValidationError

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from progressao_docente.models import ProgressaoDocente
from rh.tests.factories import SetorFactory


@pytest.mark.django_db
@pytest.mark.parametrize('siglas_campus', ['ABC,', None])
def test_sigla_vazia_ou_ausente_cai_no_tramite_da_reitoria(siglas_campus: str | None) -> None:
    Configuracao.objects.filter(app='progressao_docente').delete()
    Configuracao.objects.create(app='progressao_docente', chave='pd_sigla_setor_primeiro_tramite_reitoria', valor='CODEPE')
    if siglas_campus is not None:
        Configuracao.objects.create(app='progressao_docente', chave='pd_sigla_setor_primeiro_tramite_campus', valor=siglas_campus)
    Configuracao.clear_cache()
    codepe = SetorFactory(sigla='CODEPE', superior=SetorFactory(sigla=get_sigla_reitoria()))
    setor_avaliado = SetorFactory(sigla='XYZ', superior=SetorFactory(sigla='CAMPUS1'))

    assert ProgressaoDocente.calcular_setor_primeiro_tramite(setor_avaliado) == codepe


@pytest.mark.django_db
def test_sigla_configurada_encontra_setor_do_campus() -> None:
    Configuracao.objects.filter(app='progressao_docente').delete()
    Configuracao.objects.create(app='progressao_docente', chave='pd_sigla_setor_primeiro_tramite_campus', valor='ABC, COGPE,')
    Configuracao.clear_cache()
    cogpe = SetorFactory(sigla='COGPE/CAMPUS1', superior=SetorFactory(sigla='CAMPUS1'))

    assert ProgressaoDocente.calcular_setor_primeiro_tramite(cogpe) == cogpe


@pytest.mark.django_db
@pytest.mark.parametrize('cenario', ['sem_unidade_da_reitoria', 'reitoria_sem_setor_configurado', 'avaliado_na_reitoria_sem_setor_configurado'])
def test_sem_setor_de_destino_levanta_erro_de_configuracao(cenario: str) -> None:
    Configuracao.objects.filter(app='progressao_docente').delete()
    Configuracao.objects.create(app='progressao_docente', chave='pd_sigla_setor_primeiro_tramite_reitoria', valor='CODEPE')
    Configuracao.objects.create(app='progressao_docente', chave='pd_sigla_setor_primeiro_tramite_campus', valor='ABC')
    Configuracao.clear_cache()
    reitoria = SetorFactory(sigla=get_sigla_reitoria()) if cenario != 'sem_unidade_da_reitoria' else None
    superior = reitoria if cenario == 'avaliado_na_reitoria_sem_setor_configurado' else SetorFactory(sigla='CAMPUS1')
    setor_avaliado = SetorFactory(sigla='XYZ', superior=superior)

    with pytest.raises(ValidationError, match='inexistente ou mau configurada'):
        ProgressaoDocente.calcular_setor_primeiro_tramite(setor_avaliado)
