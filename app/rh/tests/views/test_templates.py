from datetime import datetime

from django.apps.registry import apps
from django.contrib.auth.models import Group

from rh.tests.test_base import RHBase

Log = apps.get_model('comum', 'log')


class IndexBoxTest(RHBase):
    def test_ultima_importacao(self, client):
        client_servidor = client

        # O ideal seria criar dois logs com datas diferentes,
        # e depois testar se a exibida é realmente a maior
        # Mas como o Log tem o atributo horario com auto_now_add=True
        # isso não é trivial
        Log.objects.create(app='rh', titulo='Importação do arquivo 2')
        horario = datetime.now()

        # Login com usuario não Coordenador de Gestão de Pessoas
        #        Acesso a pagina do RH não é permitida pelo usuario comum
        #        client_servidor.login(username=self.servidor_a.get_user().username, password='123')
        #        response = client_servidor.get('/rh/')
        #        self.assertNotContains(response, 'Última importação SIAPE em:' , status_code=200)

        # Login com usario do grupo Coordenador de Gestão de Pessoas
        self.servidor_a.get_user().groups.add(Group.objects.get_or_create(name='Coordenador de Gestão de Pessoas Sistêmico')[0])
        client_servidor.login(username=self.servidor_a.get_user().username, password='123')
        response = client_servidor.get('/rh/')
        # Possivelmente isso seria melhor com uma expressão regular
        assert 'Última importação SIAPE em:' in response.content.decode()
        assert response.status_code == 200
        assert horario.strftime('%d/%m/%Y') in response.content.decode()
        assert response.status_code == 200
