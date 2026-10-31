"""Dados pessoais (CPF, RG, endereço...) do professor prestador na tela ``/edu/professor/<pk>/``.

O campus do prestador é o do setor do vínculo, como o do servidor: vê a gestão acadêmica desse
campus, os papéis sistêmicos e o próprio prestador. Prestador sem setor: só os sistêmicos e ele.
"""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import Group

from comum.models import Ocupacao, OcupacaoPrestador, PrestadorServico, User, Vinculo
from comum.tests.factories import PrestadorServicoFactory
from edu.models import Professor
from rh.models import Setor
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory, SetorFactory


@pytest.fixture
def cliente(db, sync_permissions, suap_client):
    return suap_client


def _professor_prestador(setor: Setor | None) -> tuple[Professor, PrestadorServico]:
    """Como o ``ProfessorExternoForm``: o setor vem da ocupação ativa, gravada no vínculo pelo ``save``."""
    prestador = PrestadorServicoFactory()
    if setor:
        OcupacaoPrestador.objects.create(
            prestador=prestador,
            ocupacao=Ocupacao.objects.get_or_create(codigo='', defaults={'descricao': 'Professor Externo'})[0],
            empresa=PessoaJuridicaFactory(),
            data_inicio=datetime.date(2010, 1, 1),
            data_fim=datetime.date(2100, 1, 1),
            setor_suap=setor,
        )
        prestador.save()
    vinculo = Vinculo.objects.get(pk=prestador.get_vinculo().pk)
    assert vinculo.setor == setor
    return Professor.objects.create(vinculo=vinculo), prestador


def _usuario(grupo: str, setor: Setor) -> User:
    user = ServidorFactory(setor=setor).get_user()
    user.groups.add(Group.objects.get(name=grupo))
    return user


def _ve_cpf(cliente, user: User, professor: Professor, prestador: PrestadorServico) -> bool:
    cliente.login(user=user)
    resposta = cliente.get(f'/edu/professor/{professor.pk}/')
    assert resposta.status_code == 200
    return prestador.pessoa_fisica.cpf in resposta.content.decode()


@pytest.mark.parametrize(
    ('grupo', 'mesmo_campus', 've'),
    [
        ('Professor', True, False),
        ('Secretário Acadêmico', True, True),
        ('Secretário Acadêmico', False, False),
        ('Administrador Acadêmico', False, True),
    ],
)
def test_prestador_com_setor(cliente, grupo: str, mesmo_campus: bool, ve: bool) -> None:
    setor = SetorFactory()
    professor, prestador = _professor_prestador(setor)
    user = _usuario(grupo, setor if mesmo_campus else SetorFactory())

    assert _ve_cpf(cliente, user, professor, prestador) is ve


@pytest.mark.parametrize(('grupo', 've'), [('Secretário Acadêmico', False), ('Administrador Acadêmico', True)])
def test_prestador_sem_setor(cliente, grupo: str, ve: bool) -> None:
    professor, prestador = _professor_prestador(None)
    user = _usuario(grupo, SetorFactory())

    assert _ve_cpf(cliente, user, professor, prestador) is ve


def test_prestador_ve_os_proprios_dados(cliente) -> None:
    professor, prestador = _professor_prestador(None)

    assert _ve_cpf(cliente, prestador.get_user(), professor, prestador)
