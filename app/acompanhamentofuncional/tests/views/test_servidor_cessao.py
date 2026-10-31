from datetime import datetime, timedelta

from django.contrib.auth.models import Group

from rh.tests.test_base import RHBase


class TestServidorCessao(RHBase):
    """
    Caso de Uso:
        Adicionar Processo de Cessão de Servidor
    Atores:
        RH Sistêmico
        RH Campus
    Fluxo principal:
        1-logar com um usuário
        2-acessar "/admin/acompanhamentofuncional/servidorcessao/add/"
        3-preencher os dados: servidor cedido, numero da portaria, data limite
        4-submeter os dados
    Fluxo 2.1 (exceção):
        1-usuário não tem permissão para acessar a url
    Fluxo 4.1 (exceção):
        1-usuário RH Campus não tem permissão para informar o servidor, pois o mesmo não pertence ao seu campus
    Fluxo 4.2 (exceção):
        1-já existe um processo ativo para o servidor infomado
    Fluxo 4.3 (alternativo):
        1-listar o processo adicionado
    Fluxo 4.3.1 (exceção):
        1-o processo não foi encontrado

    Caso de Uso:
        Atualizar Prazos dos Processos
    Atores:
        RH Sistêmico
        RH Campus
    Fluxo principal:
        1-logar com um usuário
        2-acessar "/rh/atualiza_prazos_servidor_cessao/"
    Fluxo 2.1 (exceção):
        1-usuário não tem permissão para acessar a url
    Fluxo 2.2 (alternativo):
        1-listar processos com prazo esgotando/esgotado
    """

    def test_adicionar_processo_cessao_servidor(self, client):
        #
        # usuários
        #
        usuario_rh_sistemico = self.servidor_a
        usuario_rh_campus = self.servidor_b
        usuario_servidor = self.servidor_c

        #
        # grupos
        #
        usuario_rh_sistemico.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
        usuario_rh_campus.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas'))
        usuario_servidor.get_user().groups.add(Group.objects.get(name='Servidor'))

        #
        # "browser"
        #
        cliente = client

        #
        # Fluxo principal
        #
        cliente.login(username=usuario_rh_sistemico.get_user().username, password='123')
        response = cliente.get('/admin/acompanhamentofuncional/servidorcessao/add/')
        assert response.status_code == 200
        form_data = {
            'servidor_cedido': usuario_servidor.id,
            'numero_portaria': '123',
            'data_limite': (datetime.now() + timedelta(90)).strftime('%d/%m/%Y'),
        }
        response = cliente.post('/admin/acompanhamentofuncional/servidorcessao/add/', form_data)
        assert response.status_code == 200
