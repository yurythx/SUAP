import pytest
from django.contrib.auth.models import Group


@pytest.mark.usefixtures('atores')
class TestIndexQuadrosCalendario:
    def test_prestador_com_grupo_servidor_nao_quebra(self, client):
        prestador_user = self.prestador_1.get_user()
        servidor_group = Group.objects.filter(name='Servidor').first()
        if servidor_group:
            prestador_user.groups.add(servidor_group)

        client.login(username=prestador_user.username, password='123')
        response = client.get('/comum/index/meus_quadros_por_coluna/esquerda/')
        assert response.status_code != 500

    def test_servidor_happy_path(self, client):
        client.login(username=self.servidor_a.get_user().username, password='123')
        response = client.get('/comum/index/meus_quadros_por_coluna/esquerda/')
        assert response.status_code != 500

    def test_prestador_sem_grupo_servidor(self, client):
        client.login(username=self.prestador_1.matricula, password='123')
        response = client.get('/comum/index/meus_quadros_por_coluna/esquerda/')
        assert response.status_code != 500

    def test_servidor_sem_grupo_servidor(self, client):
        servidor_user = self.servidor_b.get_user()
        servidor_group = Group.objects.filter(name='Servidor').first()
        if servidor_group:
            servidor_user.groups.remove(servidor_group)

        client.login(username=servidor_user.username, password='123')
        response = client.get('/comum/index/meus_quadros_por_coluna/esquerda/')
        assert response.status_code != 500

    def test_servidor_que_tambem_e_aluno_entrando_como_aluno(self, rf):
        # depois da deduplicação, servidor e aluno são a mesma pessoa física (eh_servidor=True): o vínculo do login decide
        from django.contrib.sessions.backends.db import SessionStore

        from djtools.layout import get_quadro_by_name
        from edu.tests.factories import AlunoFactory

        aluno = AlunoFactory(pessoa_fisica=self.servidor_a.pessoa_fisica)
        request = rf.get('/comum/index/meus_quadros_por_coluna/esquerda/')
        request.user, request.session = aluno.get_vinculo().user, SessionStore()
        assert request.user.get_relacionamento() == aluno
        assert aluno.pessoa_fisica.eh_servidor

        quadro = get_quadro_by_name('CALENDÁRIO ADMINISTRATIVO', request)

        assert not quadro.items  # o aluno não tem calendário administrativo; antes, o filtro de servidor recebia o Aluno
