"""Vínculo Entrega ↔ Especificação (rastreabilidade)."""

from datetime import date
from unittest import mock

import pytest

from demandas.forms import EntregaForm
from demandas.models import Situacao
from demandas.services import EntregaService
from demandas.tests.factories import DemandaFactory, DoDFactory, EntregaFactory, EspecificacaoFactory


@pytest.mark.django_db(databases='__all__')
def test_entrega_vincula_e_lista_especificacoes(demanda, usuario):
    dod = DoDFactory(demanda=demanda, descricao='DoD')
    e1 = EspecificacaoFactory(dod=dod, nome='Login', ordem=1)
    e2 = EspecificacaoFactory(dod=dod, nome='Relatório', ordem=2)

    entrega = EntregaFactory(demanda=demanda, titulo='Pacote 1', cadastrada_por=usuario)
    entrega.especificacoes.set([e1, e2])

    assert set(entrega.especificacoes.all()) == {e1, e2}
    assert list(e1.entregas.all()) == [entrega]


@pytest.mark.django_db(databases='__all__')
def test_service_criar_vincula_especificacoes(demanda, usuario):
    demanda.situacao = Situacao.ESTADO_EM_DESENVOLVIMENTO
    demanda.save()
    dod = DoDFactory(demanda=demanda, descricao='DoD')
    e1 = EspecificacaoFactory(dod=dod, nome='Login', ordem=1)

    with mock.patch('demandas.services.adicionar_comentario'):
        entrega = EntregaService.criar(
            demanda=demanda,
            titulo='Pacote',
            usuario=usuario,
            prazo_feedback=date.today(),
            especificacoes=[e1],
        )

    assert list(entrega.especificacoes.all()) == [e1]


@pytest.mark.django_db(databases='__all__')
def test_service_criar_sem_especificacoes_nao_vincula(demanda, usuario):
    demanda.situacao = Situacao.ESTADO_EM_DESENVOLVIMENTO
    demanda.save()

    with mock.patch('demandas.services.adicionar_comentario'):
        entrega = EntregaService.criar(demanda=demanda, titulo='Pacote', usuario=usuario, prazo_feedback=date.today())

    assert entrega.especificacoes.count() == 0


@pytest.mark.django_db(databases='__all__')
def test_form_especificacoes_escopadas_a_demanda(demanda):
    dod = DoDFactory(demanda=demanda, descricao='DoD')
    e1 = EspecificacaoFactory(dod=dod, nome='Login', ordem=1)
    outra = DemandaFactory(titulo='Outra')
    dod2 = DoDFactory(demanda=outra, descricao='DoD2')
    EspecificacaoFactory(dod=dod2, nome='Fora', ordem=1)

    form = EntregaForm(demanda=demanda, request=None)

    assert 'especificacoes' in form.fields
    assert form.fields['especificacoes'].required is False
    assert list(form.fields['especificacoes'].queryset) == [e1]


@pytest.mark.django_db(databases='__all__')
def test_form_remove_campo_sem_especificacoes(demanda):
    form = EntregaForm(demanda=demanda, request=None)
    assert 'especificacoes' not in form.fields
