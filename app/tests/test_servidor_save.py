import pytest
from django.apps.registry import apps
from django.contrib.auth.models import Group
from django.db.models.signals import post_save

from comum.models import user_post_save

User = apps.get_model('comum', 'User')
PessoaFisica = apps.get_model('rh', 'PessoaFisica')
Servidor = apps.get_model('rh', 'Servidor')
Setor = apps.get_model('rh', 'Setor')
Situacao = apps.get_model('rh', 'Situacao')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')


@pytest.mark.django_db
class TestServidorSave:
    @pytest.fixture(autouse=True)
    def _setup(self):
        post_save.disconnect(user_post_save, sender=User, dispatch_uid='comum.models')
        for nome_grupo in (
            'Aposentado',
            'Servidor',
            'Professor',
            'Aluno',
            'Avaliador Interno',
            'Avaliador Externo',
            'Servidores Com Poder de Chefe',
        ):
            Group.objects.get_or_create(name=nome_grupo)

        self.setor_suap_1_campus_1 = Setor.objects.create(nome='Setor SUAP 1 - Campus 1', sigla='SUAP11')
        self.setor_suap_2_campus_1 = Setor.objects.create(
            nome='Setor SUAP 2 - Campus 1',
            sigla='SUAP21',
            superior=self.setor_suap_1_campus_1,
        )
        self.setor_suap_3_campus_2 = Setor.objects.create(nome='Setor SUAP 3 - Campus 2', sigla='SUAP32')

        self.uo_suap_1 = UnidadeOrganizacional.objects.suap().create(setor=self.setor_suap_1_campus_1)
        self.uo_suap_2 = UnidadeOrganizacional.objects.suap().create(setor=self.setor_suap_3_campus_2)

        self.setor_siape_1_campus_1 = Setor.objects.create(codigo='1', nome='Setor SIAPE - Campus 1', sigla='SIAPE11')
        self.setor_siape_3_campus_1 = Setor.objects.create(
            codigo='3',
            nome='Setor SIAPE - Campus 1',
            sigla='SIAPE31',
            superior=self.setor_siape_1_campus_1,
        )
        self.setor_siape_2_campus_2 = Setor.objects.create(codigo='2', nome='Setor SIAPE - Campus 2', sigla='SIAPE22')

        self.uo_siape_1 = UnidadeOrganizacional.objects.suap().create(setor=self.setor_siape_1_campus_1, equivalente=self.uo_suap_1)
        self.uo_siape_2 = UnidadeOrganizacional.objects.suap().create(setor=self.setor_siape_2_campus_2, equivalente=self.uo_suap_2)

        self.setor_suap_1_campus_1 = Setor.objects.get(id=self.setor_suap_1_campus_1.id)
        self.setor_suap_2_campus_1 = Setor.objects.get(id=self.setor_suap_2_campus_1.id)
        self.setor_suap_3_campus_2 = Setor.objects.get(id=self.setor_suap_3_campus_2.id)
        self.setor_siape_1_campus_1 = Setor.objects.get(id=self.setor_siape_1_campus_1.id)
        self.setor_siape_3_campus_1 = Setor.objects.get(id=self.setor_siape_3_campus_1.id)
        self.setor_siape_2_campus_2 = Setor.objects.get(id=self.setor_siape_2_campus_2.id)

    def teardown_method(self):
        post_save.connect(user_post_save, sender=User, dispatch_uid='comum.models')

    def test_move_servidor_between_uos_updates_setor_according_to_regra(self):
        pessoa_fisica = PessoaFisica.objects.get_or_create(nome='Servidor Teste', defaults={'cpf': '737.737.737-22'})[0]
        servidor = Servidor.objects.get_or_create(
            matricula='1000001',
            defaults={
                'setor_exercicio': self.setor_siape_1_campus_1,
                # get_or_create: a fixture class-scoped `siape_executado` (rh/tests/conftest.py)
                # roda fora de transação e deixa Situacao('02') persistente entre testes do worker.
                'situacao': Situacao.objects.get_or_create(codigo='02')[0],
                'pessoa_fisica': pessoa_fisica,
            },
        )[0]

        assert servidor.get_user().username == servidor.matricula

        servidor.save()
        assert servidor.setor is None
        assert servidor.setor_exercicio == self.setor_siape_1_campus_1

        servidor.setor = self.setor_suap_1_campus_1
        servidor.save()
        assert servidor.setor_exercicio == self.setor_siape_1_campus_1
        assert servidor.setor == self.setor_suap_1_campus_1

        servidor.setor_exercicio = self.setor_siape_3_campus_1
        servidor.save()
        assert servidor.setor_exercicio == self.setor_siape_3_campus_1
        assert servidor.setor == self.setor_suap_1_campus_1

        servidor.setor_exercicio = self.setor_siape_2_campus_2
        servidor.save()
        assert servidor.setor is None
        assert servidor.setor_exercicio == self.setor_siape_2_campus_2

        servidor.setor_exercicio = None
        servidor.save()
        assert servidor.setor is None
        assert servidor.setor_exercicio is None
