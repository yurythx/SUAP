"""Flags ``eh_*`` do ``User`` seguem o vínculo do login, mesmo quando servidor e aluno são a mesma pessoa física."""

import pytest
from django.core.management import call_command

from comum.models import User
from edu.tests.factories import AlunoFactory
from rh.tests.factories import ServidorFactory

FLAGS = ('eh_servidor', 'eh_aluno', 'eh_prestador', 'eh_docente', 'eh_tecnico_administrativo')


def flags(user: User) -> dict[str, bool]:
    user.refresh_from_db()
    return {flag: getattr(user, flag) for flag in FLAGS}


@pytest.fixture
def servidor_que_tambem_e_aluno(sync_permissions: None) -> tuple[User, User]:
    servidor = ServidorFactory()
    aluno = AlunoFactory(pessoa_fisica=servidor.pessoa_fisica)
    return servidor.get_user(), aluno.get_vinculo().user


@pytest.mark.django_db
def test_comando_noturno_marca_cada_login_pelo_seu_vinculo(servidor_que_tambem_e_aluno: tuple[User, User]) -> None:
    login_servidor, login_aluno = servidor_que_tambem_e_aluno
    User.objects.filter(pk__in=[login_servidor.pk, login_aluno.pk]).update(eh_servidor=True, eh_aluno=True, eh_docente=True)

    call_command('atualizar_pessoa_fisica_sub_instances')

    assert flags(login_servidor) == {**dict.fromkeys(FLAGS, False), 'eh_servidor': True, 'eh_tecnico_administrativo': True}
    assert flags(login_aluno) == {**dict.fromkeys(FLAGS, False), 'eh_aluno': True}


@pytest.mark.django_db
def test_login_corrige_flags_trocadas(servidor_que_tambem_e_aluno: tuple[User, User], client) -> None:
    _, login_aluno = servidor_que_tambem_e_aluno
    User.objects.filter(pk=login_aluno.pk).update(eh_servidor=True, eh_aluno=False)
    login_aluno.refresh_from_db()  # o login carrega o usuário do banco, com as flags trocadas

    client.force_login(login_aluno)

    assert flags(login_aluno) == {**dict.fromkeys(FLAGS, False), 'eh_aluno': True}
