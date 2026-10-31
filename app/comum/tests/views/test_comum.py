import pytest


@pytest.mark.usefixtures('atores')
class TestComum:
    def test_index(self, client):
        response = client.get('/')
        assert response.status_code != 500

        client.login(username=self.servidor_a.get_user().username, password='123')
        response = client.get('/')
        assert self.servidor_a.get_user().username in response.content.decode()
        assert response.status_code == 200

        client.logout()
        client.login(username=self.prestador_1.matricula, password='123')
        response = client.get('/')
        assert self.prestador_1.pessoa_fisica.nome_usual in response.content.decode()
        assert response.status_code == 200
