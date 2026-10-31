"""Smoke do substrato de pessoal via factories (``rh.tests.factories``).

Protege o que faz um ``Servidor`` de factory ser usável num teste HTTP: usuário e vínculo
criados pelo ``save``, e setor com campus (sem campus o middleware desloga o servidor).
"""

from __future__ import annotations

import pytest

from rh.tests.factories import ServidorFactory, SetorFactory, cpf_valido


def test_cpf_valido_tem_digitos_verificadores_corretos() -> None:
    assert cpf_valido(861474078) == '861.474.078-64'


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_servidor_nasce_com_usuario_vinculo_e_setor_com_campus() -> None:
    servidor = ServidorFactory()

    assert servidor.get_user().username == servidor.matricula
    assert servidor.get_vinculo().setor == servidor.setor
    assert servidor.setor is not None
    assert servidor.setor.uo is not None


@pytest.mark.django_db
def test_setor_filho_herda_o_campus_do_superior() -> None:
    campus = SetorFactory()

    assert SetorFactory(superior=campus).uo == campus.uo


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_servidor_de_matricula_existente_e_reencontrado_sem_criar_pessoa() -> None:
    """Reuso (o ``--reuse-db`` dos e2e) não deixa ``PessoaFisica`` órfã nem CPF duplicado."""
    from rh.models import PessoaFisica

    primeiro = ServidorFactory(matricula='9876543', pessoa_fisica__cpf=cpf_valido(123456789))
    pessoas = PessoaFisica.objects.count()

    reencontrado = ServidorFactory(matricula='9876543', pessoa_fisica__cpf=cpf_valido(123456789))

    assert reencontrado.pk == primeiro.pk
    assert PessoaFisica.objects.count() == pessoas
