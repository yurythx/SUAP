"""Cópia das siglas de primeiro trâmite da Configuração para o cadastro próprio (migration 0022)."""

import importlib

import pytest
from django.apps import apps

from comum.models import Configuracao
from progressoes.models import SiglaSetorPrimeiroTramite

migracao = importlib.import_module('progressoes.migrations.0022_sigla_setor_primeiro_tramite')


@pytest.mark.django_db
def test_siglas_da_configuracao_viram_cadastro_e_voltam_no_reverso() -> None:
    Configuracao.objects.filter(app='progressoes').delete()
    Configuracao.objects.create(app='progressoes', chave='sigla_setor_primeiro_tramite_reitoria', valor='CODEPE')
    Configuracao.objects.create(app='progressoes', chave='sigla_setor_primeiro_tramite_campus', valor=f' COGPE, DIAPE,,COGPE,{"X" * 51}')

    migracao.copiar_siglas_da_configuracao(apps, None)

    cadastro = list(SiglaSetorPrimeiroTramite.objects.values_list('tipo', 'sigla', 'ordem'))
    assert cadastro == [('campus', 'COGPE', 1), ('campus', 'DIAPE', 2), ('reitoria', 'CODEPE', 1)]
    assert not Configuracao.objects.filter(app='progressoes', chave__startswith='sigla_setor_primeiro_tramite').exists()

    migracao.devolver_siglas_para_configuracao(apps, None)

    assert Configuracao.objects.get(app='progressoes', chave='sigla_setor_primeiro_tramite_campus').valor == 'COGPE,DIAPE'
    assert Configuracao.objects.get(app='progressoes', chave='sigla_setor_primeiro_tramite_reitoria').valor == 'CODEPE'
