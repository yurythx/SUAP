"""Testes do command que reconfigura as etapas/ações padrão do PDA."""

import datetime

import pytest
from django.core.management import call_command

from dados_abertos.models import Etapa, PDAEtapa, PlanoDadosAbertos


@pytest.fixture
def pda(db):
    return PlanoDadosAbertos.objects.create(
        titulo='PDA 2026-2027',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2027, 12, 31),
    )


@pytest.mark.django_db
def test_preserva_as_dispensas_de_etapa_ao_reconfigurar(pda):
    """Reconfigurar as etapas não pode apagar a dispensa registrada de uma etapa pulável.

    A dispensa guarda auditoria (justificativa, autor, IP) e define por onde o fluxo passa; como
    ``PDAEtapa.etapa`` é ``CASCADE``, recriar as etapas apagaria o registro e faria o PDA regredir
    para a etapa que havia sido legitimamente dispensada.
    """
    call_command('configurar_etapas_padrao')
    etapa_pulavel = Etapa.objects.filter(pulavel=True).first()
    assert etapa_pulavel, 'a estrutura padrão precisa ter ao menos uma etapa pulável'

    PDAEtapa.objects.create(
        pda=pda,
        etapa=etapa_pulavel,
        justificativa='Consulta passou do prazo',
        ip='10.0.0.1',
        user_agent='Firefox',
    )

    call_command('configurar_etapas_padrao')

    dispensa = PDAEtapa.objects.filter(pda=pda).select_related('etapa').first()
    assert dispensa is not None, 'a dispensa da etapa foi perdida na reconfiguração'
    assert dispensa.etapa.ordem == etapa_pulavel.ordem
    assert dispensa.justificativa == 'Consulta passou do prazo'
    assert dispensa.ip == '10.0.0.1'
