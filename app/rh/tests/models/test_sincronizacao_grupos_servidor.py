import pytest
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rh.tests.factories import ServidorFactory


@pytest.mark.usefixtures('sync_permissions')
def test_save_de_servidor_sem_chefia_remove_permissoes_do_chefe_em_lote() -> None:
    """Regressão: a remoção das permissões de 'Chefe de Setor' fazia um DELETE por permissão do grupo."""
    permissoes_chefe = list(Group.objects.get(name='Chefe de Setor').permissions.all())
    assert len(permissoes_chefe) > 2
    outra_permissao = Permission.objects.exclude(pk__in=[p.pk for p in permissoes_chefe]).first()

    servidor = ServidorFactory()
    user = servidor.get_user()
    user.user_permissions.add(*permissoes_chefe[:2], outra_permissao)

    with CaptureQueriesContext(connection) as ctx:
        servidor.save()

    queries_permissao_usuario = [q['sql'] for q in ctx.captured_queries if 'auth_user_user_permissions' in q['sql']]
    assert len(queries_permissao_usuario) <= 2, queries_permissao_usuario
    assert list(user.user_permissions.all()) == [outra_permissao]
