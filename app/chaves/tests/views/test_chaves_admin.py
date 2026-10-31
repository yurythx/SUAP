import pytest
from django.apps import apps
from django.contrib.auth.models import Group

Chave = apps.get_model('chaves', 'Chave')
Predio = apps.get_model('comum', 'Predio')
Sala = apps.get_model('comum', 'Sala')


class TestAdminChaves:
    @pytest.fixture(autouse=True)
    def _setup(self, client, operador):
        self.client = client
        self.user = operador.get_user()
        self.client.login(username=self.user.username, password='123')

        self.grupo_operador = Group.objects.get(name='Operador de Chaves')

        # O prédio fica no campus do próprio operador: a sala é o que liga chave a pessoa.
        self.predio = Predio.objects.create(uo=operador.setor.uo)
        self.sala = Sala.objects.create(predio=self.predio)
        self.sala.avaliadores_de_agendamentos.add(self.user)

    def test_listagem_de_chaves_exige_grupo_operador(self):
        resposta_sem_grupo = self.client.get('/admin/chaves/chave/')
        assert resposta_sem_grupo.status_code == 403

        self.user.groups.add(self.grupo_operador)
        resposta_com_grupo = self.client.get('/admin/chaves/chave/')
        assert resposta_com_grupo.status_code == 200

    def test_operador_consegue_cadastrar_chave(self):
        assert Chave.objects.filter(identificacao='T1').count() == 0

        self.user.groups.add(self.grupo_operador)
        resposta = self.client.post('/admin/chaves/chave/add/', {'identificacao': 'T1', 'sala': self.sala.id})

        assert resposta.status_code == 302
        assert Chave.objects.filter(identificacao='T1').count() == 1

    def test_cadastro_chave_nao_sobrescreve_template_de_pessoafisica(self):
        from rh.models import PessoaFisica

        metodo_original = PessoaFisica.get_ext_combo_template
        self.user.groups.add(self.grupo_operador)
        self.client.get('/admin/chaves/chave/add/')
        assert PessoaFisica.get_ext_combo_template is metodo_original
