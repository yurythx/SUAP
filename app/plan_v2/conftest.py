import pytest
from django.contrib.auth.models import Group

from rh.tests.factories import ServidorFactory

SENHA = '123'


@pytest.fixture
def administrador(suap_client, sync_permissions):
    """Client autenticado como Administrador de Planejamento Institucional.

    `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest
    raiz): importá-las aqui as redefiniria no módulo e quebraria o uso como parâmetro.
    """
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Administrador de Planejamento Institucional'))
    user.set_password(SENHA)
    user.save()
    suap_client.login(username=user.username, password=SENHA)
    return suap_client
