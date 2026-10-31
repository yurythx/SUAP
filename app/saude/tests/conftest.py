"""Fixtures de fluxo da Avaliação Biomédica (saúde).

Montam o estado mínimo por ORM: um aluno matriculado, o profissional de saúde
(com todos os grupos de especialidade necessários para preencher as fichas) e
um atendimento de avaliação biomédica já aberto. Os testes apenas exercitam os
endpoints que representam cada etapa do atendimento.
"""

import datetime

import pytest
from django.contrib.auth.models import Group

# `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest raiz);
# não as importamos aqui para poder usá-las como parâmetro de fixture.
from edu.tests.factories import AlunoFactory
from rh.models import CargoEmprego
from rh.tests.factories import GrupoCargoEmpregoFactory, ServidorFactory
from saude.models import Atendimento, Doenca, ExameFisico, Odontograma, Prontuario, SinaisVitais, SituacaoClinica, TipoAtendimento

# Especialidades exigidas pelos @group_required das fichas (enfermagem, odontologia, medicina).
GRUPOS_PROFISSIONAL = ['Médico', 'Odontólogo', 'Enfermeiro', 'Técnico em Enfermagem']
# Código de cargo médico mapeado em Especialidades.CARGO_ESPECIALIDADE_GRUPO_ID;
# é o que permite registrar a especialidade do profissional ao preencher cada ficha.
CODIGO_CARGO_SAUDE = '701047'


@pytest.fixture
def aluno(db):
    """Aluno matriculado — único vínculo elegível à avaliação biomédica."""
    return AlunoFactory()


@pytest.fixture
def servidor_profissional(db, sync_permissions):
    """Servidor de saúde com todas as especialidades exigidas pelas fichas.

    Pede `db` explicitamente: o `suap_data` fazia o conftest raiz marcar o teste com
    `django_db` automaticamente, e sem ele esta fixture tocaria o banco antes de qualquer
    marcação — os testes que a pedem primeiro na assinatura morriam no setup.
    """
    cargo = CargoEmprego.objects.get_or_create(
        codigo=CODIGO_CARGO_SAUDE,
        defaults={'nome': 'MEDICO-AREA', 'grupo_cargo_emprego': GrupoCargoEmpregoFactory(), 'sigla_escolaridade': 'NS'},
    )[0]
    servidor = ServidorFactory(cargo_emprego=cargo)
    user = servidor.get_user()
    for nome in GRUPOS_PROFISSIONAL:
        user.groups.add(Group.objects.get(name=nome))
    return servidor


@pytest.fixture
def profissional(suap_client, servidor_profissional):
    """Client autenticado como o servidor de saúde (login por objeto, sem senha)."""
    suap_client.login(user=servidor_profissional.get_user())
    return suap_client


@pytest.fixture
def prontuario(aluno):
    return Prontuario.get_prontuario(aluno.get_vinculo())


@pytest.fixture
def atendimento_aberto(profissional, aluno, prontuario, servidor_profissional):
    """Avaliação biomédica já aberta (pré-condição das fichas e do fechamento)."""
    return Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, servidor_profissional.get_user())


@pytest.fixture
def atendimento_completo(atendimento_aberto, servidor_profissional):
    """Avaliação sem pendências (Sinais Vitais, Exame Físico e Odontograma) — pronta para fechar."""
    user = servidor_profissional.get_user()
    for modelo in (SinaisVitais, ExameFisico, Odontograma):
        modelo.objects.create(atendimento=atendimento_aberto, profissional=user)
    return atendimento_aberto


@pytest.fixture
def doencas(db):
    return (
        Doenca.objects.create(nome='Doença A', ativo=True),
        Doenca.objects.create(nome='Doença B', ativo=True),
    )


@pytest.fixture
def situacao_clinica(db):
    return SituacaoClinica.objects.get_or_create(descricao='Cárie', categoria='red', preenchimento='1', cpod='C')[0]
