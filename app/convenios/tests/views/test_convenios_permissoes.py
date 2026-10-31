import datetime

import pytest
from django.contrib.auth.models import Group

from convenios.models import Convenio, SituacaoConvenio, TipoConvenio
from djtools.utils import somar_dias
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory, SetorFactory

SENHA = '123'


@pytest.mark.django_db(databases='__all__')
class TestPermissoesConvenio:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, db, sync_permissions, suap_client):
        self.client = suap_client
        self.setor_a0_suap = SetorFactory()
        self.pessoa_juridica = PessoaJuridicaFactory()
        self.servidor_a = ServidorFactory(setor=self.setor_a0_suap)
        self.user = self.servidor_a.get_user()
        self.user.set_password(SENHA)
        self.user.save()
        self.client.login(username=self.user.username, password=SENHA)

        self.operador_sistemico = Group.objects.get(name='Operador de Convênios Sistêmico')
        self.operador = Group.objects.get(name='Operador de Convênios')
        self.visualizador = Group.objects.get(name='Visualizador de Convênios')
        self.servidor = Group.objects.get(name='Servidor')

        self.tipo_convenio, _ = TipoConvenio.objects.get_or_create(descricao='Convênio')
        self.situacao_vigente, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VIGENTE, descricao='Vigente')

    def _trocar_grupos(self, grupos):
        self.user.groups.clear()
        for grupo in grupos:
            self.user.groups.add(grupo)
        self.client.logout()
        self.client.login(username=self.user.username, password='123')

    def _criar_convenio(self):
        convenio = Convenio.objects.create(
            numero=f'CNV-{Convenio.objects.count() + 1:04d}',
            tipo=self.tipo_convenio,
            situacao=self.situacao_vigente,
            uo=self.setor_a0_suap.uo,
            interveniente=self.pessoa_juridica,
            data_inicio=somar_dias(datetime.datetime.today(), -90).date(),
            data_fim=somar_dias(datetime.datetime.today(), 120).date(),
            objeto='Convênio para teste de permissão',
        )
        convenio.vinculos_conveniadas.add(self.pessoa_juridica.get_vinculo())
        return convenio

    def test_busca_de_convenios_exige_papel_do_modulo(self):
        self._trocar_grupos([self.servidor])
        resposta_sem_permissao = self.client.get('/convenios/convenios/')
        assert resposta_sem_permissao.status_code == 403

        self._trocar_grupos([self.visualizador])
        resposta_com_permissao = self.client.get('/convenios/convenios/')
        assert resposta_com_permissao.status_code == 200

    def test_adicionar_aditivo_exige_perfil_operador(self):
        convenio = self._criar_convenio()

        self._trocar_grupos([self.visualizador])
        resposta_sem_permissao = self.client.get(f'/convenios/adicionar_aditivo/{convenio.pk}/')
        assert resposta_sem_permissao.status_code == 403

        self._trocar_grupos([self.operador])
        resposta_operador = self.client.get(f'/convenios/adicionar_aditivo/{convenio.pk}/')
        assert resposta_operador.status_code == 200

        self._trocar_grupos([self.operador_sistemico])
        resposta_operador_sistemico = self.client.get(f'/convenios/adicionar_aditivo/{convenio.pk}/')
        assert resposta_operador_sistemico.status_code == 200
