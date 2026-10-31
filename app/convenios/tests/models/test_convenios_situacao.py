import datetime

import pytest

from convenios.models import Convenio, SituacaoConvenio, TipoConvenio
from djtools.utils import somar_dias
from rh.tests.factories import PessoaJuridicaFactory, SetorFactory


@pytest.mark.django_db(databases='__all__')
class TestSituacaoConvenio:
    databases = '__all__'

    @pytest.fixture(autouse=True)
    def _setup(self, db):
        self.setor_a0_suap = SetorFactory()
        self.pessoa_juridica = PessoaJuridicaFactory()
        self.tipo_convenio, _ = TipoConvenio.objects.get_or_create(descricao='Convênio')
        self.situacao_vigente, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VIGENTE, descricao='Vigente')
        self.situacao_vencendo, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VENCENDO, descricao='Vencendo')
        self.situacao_vencido, _ = SituacaoConvenio.objects.get_or_create(pk=SituacaoConvenio.VENCIDO, descricao='Vencido')
        self.hoje = datetime.datetime.today()

    def _novo_convenio(self, data_fim):
        convenio = Convenio.objects.create(
            numero=f'CNV-{Convenio.objects.count() + 1:04d}',
            tipo=self.tipo_convenio,
            situacao=self.situacao_vigente,
            uo=self.setor_a0_suap.uo,
            interveniente=self.pessoa_juridica,
            data_inicio=somar_dias(self.hoje, -120).date(),
            data_fim=data_fim,
            objeto='Parceria institucional para testes',
        )
        convenio.vinculos_conveniadas.add(self.pessoa_juridica.get_vinculo())
        return convenio

    def test_convenio_fica_vencendo_quando_vence_em_30_dias(self):
        convenio = self._novo_convenio(data_fim=somar_dias(self.hoje, 30).date())

        situacao = convenio.get_situacao()

        assert situacao.pk == self.situacao_vencendo.pk

    def test_convenio_fica_vencido_quando_data_final_ja_passou(self):
        convenio = self._novo_convenio(data_fim=somar_dias(self.hoje, -1).date())

        situacao = convenio.get_situacao()

        assert situacao.pk == self.situacao_vencido.pk
