import datetime

import pytest
from django.contrib.auth.models import Group

from comum.pytest_fixtures import assert_no_validation_errors, assert_redirects
from convenios.models import Convenio, SituacaoConvenio, TipoConvenio
from djtools.utils import somar_dias
from rh.tests.factories import PessoaJuridicaFactory, ServidorFactory, SetorFactory

SENHA = '123'


@pytest.mark.django_db(databases='__all__')
class TestFluxoConvenio:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, db, sync_permissions, suap_client):
        self.client = suap_client
        self.setor_a0_suap = SetorFactory()
        self.pessoa_juridica = PessoaJuridicaFactory()
        self.servidor_a = ServidorFactory(setor=self.setor_a0_suap)
        usuario = self.servidor_a.get_user()
        usuario.set_password(SENHA)
        usuario.save()
        self.servidor_a.get_user().groups.add(Group.objects.get(name='Operador de Convênios Sistêmico'))
        self.client.login(username=self.servidor_a.get_user().username, password=SENHA)

        self.tipo_convenio, _ = TipoConvenio.objects.get_or_create(descricao='Convênio')
        self.situacao_vigente, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VIGENTE, descricao='Vigente')
        self.situacao_vencendo, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VENCENDO, descricao='Vencendo')
        self.situacao_vencido, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VENCIDO, descricao='Vencido')
        self.hoje = datetime.datetime.today()

    def _payload_cadastro_convenio(self, data_inicio=None, data_fim=None):
        data_inicio = data_inicio or somar_dias(self.hoje, -120).date()
        data_fim = data_fim or somar_dias(self.hoje, 365).date()
        return {
            'numero': '99999/9999',
            'tipo': self.tipo_convenio.pk,
            'situacao': self.situacao_vigente.pk,
            'uo': self.setor_a0_suap.uo.pk,
            'interveniente': self.pessoa_juridica.pk,
            'data_inicio': f'{data_inicio.day}/{data_inicio.month}/{data_inicio.year}',
            'data_fim': f'{data_fim.day}/{data_fim.month}/{data_fim.year}',
            'objeto': 'Objetivo do contrato',
            'vinculos_conveniadas': self.pessoa_juridica.get_vinculo().pk,
        }

    def _criar_convenio(self):
        self.pessoa_juridica.save()
        resposta = self.client.post('/admin/convenios/convenio/add/', self._payload_cadastro_convenio())
        assert_no_validation_errors(resposta)
        return resposta, Convenio.objects.latest('id')

    def test_operador_cadastra_convenio_e_eh_redirecionado_para_detalhe(self):
        resposta_formulario = self.client.get('/admin/convenios/convenio/add/')
        assert resposta_formulario.status_code == 200
        assert 'Adicionar Convênio' in resposta_formulario.content.decode()

        quantidade_antes = Convenio.objects.count()
        resposta, convenio = self._criar_convenio()
        assert Convenio.objects.count() == quantidade_antes + 1
        assert_redirects(resposta, f'/convenios/convenio/{convenio.pk}/')

    def test_busca_retorna_convenio_quando_filtros_correspondem(self):
        _, convenio = self._criar_convenio()

        resposta_inicial = self.client.get('/convenios/convenios/')
        assert resposta_inicial.status_code == 200
        assert 'Buscar Convênios' in resposta_inicial.content.decode()

        data_inicio = somar_dias(self.hoje, -120).date()
        data_fim = somar_dias(self.hoje, 365).date()
        filtros = {
            'numero': convenio.numero,
            # O campo `conveniada` do form de busca tem queryset de `Vinculo`, ao contrário
            # do `interveniente`, que é FK para `PessoaJuridica`. Postar o pk da pessoa
            # jurídica só funcionava porque, com o `suap_data`, os dois ids coincidiam.
            'conveniada': self.pessoa_juridica.get_vinculo().pk,
            'interveniente': self.pessoa_juridica.pk,
            'situacao': self.situacao_vigente.pk,
            'tipo': self.tipo_convenio.pk,
            'uo': self.setor_a0_suap.uo.pk,
            'data_inicio': f'{data_inicio.day}/{data_inicio.month}/{data_inicio.year}',
            'data_fim': f'{data_fim.day}/{data_fim.month}/{data_fim.year}',
        }

        resposta = self.client.post('/convenios/convenios/', filtros)
        assert resposta.status_code == 200
        assert 'Convênios Encontrados' in resposta.content.decode()

    def test_aditivo_revalida_convenio_vencido_para_vigente(self):
        _, convenio = self._criar_convenio()
        convenio.data_fim = somar_dias(convenio.data_inicio, 1)
        convenio.save()
        assert convenio.get_situacao().pk == self.situacao_vencido.pk

        resposta_formulario = self.client.get(f'/convenios/adicionar_aditivo/{convenio.pk}/')
        assert resposta_formulario.status_code == 200
        assert 'Adicionar Aditivo' in resposta_formulario.content.decode()

        data_inicio = somar_dias(self.hoje, 180).date()
        data_fim = somar_dias(self.hoje, 365).date()
        payload = {
            'numero': '99999/9999',
            'objeto': 'Objetivo do aditivo',
            'data': f'{self.hoje.day}/{self.hoje.month}/{self.hoje.year}',
            'data_inicio': f'{data_inicio.day}/{data_inicio.month}/{data_inicio.year}',
            'data_fim': f'{data_fim.day}/{data_fim.month}/{data_fim.year}',
        }

        resposta = self.client.post(f'/convenios/adicionar_aditivo/{convenio.pk}/', payload)
        assert_no_validation_errors(resposta)
        convenio.refresh_from_db()
        assert convenio.get_situacao().pk == self.situacao_vigente.pk
