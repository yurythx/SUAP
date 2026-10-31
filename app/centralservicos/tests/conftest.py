import pytest

from centralservicos.tests.builders import criar_contexto_centralservicos
from comum.pytest_fixtures import api_auth_mocks


@pytest.fixture
def centralservicos_context(db, sync_permissions, suap_client):
    return criar_contexto_centralservicos(suap_client)
