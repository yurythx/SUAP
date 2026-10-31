import pytest
from django.contrib import admin
from django.test import RequestFactory

from comum.admin import PrestadorServicoAdmin
from comum.models import PrestadorServico, User


def test_somente_coordenador_de_ti_sistemico_pode_alterar_situacao_do_prestador(rf: RequestFactory) -> None:
    usuario = User(username='usuario')
    request = rf.get('/')
    request.user = usuario
    model_admin = PrestadorServicoAdmin(PrestadorServico, admin.site)
    prestador = PrestadorServico()

    usuario.has_group_cached = lambda grupos: False
    assert 'ativo' not in model_admin.get_readonly_fields(request)
    assert 'ativo' in model_admin.get_readonly_fields(request, prestador)

    usuario.has_group_cached = lambda grupos: True
    assert 'ativo' not in model_admin.get_readonly_fields(request, prestador)


@pytest.mark.usefixtures('atores')
class TestAdmin:
    @pytest.fixture(autouse=True)
    def setup_client(self, client, atores):
        self.client = client
        self.client.force_login(self.admin.get_user())

    def test_acessos(self):
        paths_and_expected_content = [
            ('/admin/', '/admin/comum'),
            ('/admin/comum/', '/admin/comum/sessioninfo'),
            ('/admin/comum/sessioninfo/', 'Informações de Sessões'),
        ]
        for path, expected_content in paths_and_expected_content:
            response = self.client.get(path)
            assert expected_content in response.content.decode()
            assert response.status_code == 200
