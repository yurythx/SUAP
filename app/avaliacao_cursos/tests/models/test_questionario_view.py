from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError

from avaliacao_cursos.models import Avaliacao, Questionario, Respondente, Segmento
from comum.models import Ano
from djtools.crosstab.bidimensional import TabelaBidimensional
from rh.models import Setor, UnidadeOrganizacional
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
class TabelaBidimensionalVerticalKeyTest:
    fixtures = ['initial_data']

    @pytest.fixture(autouse=True)
    def _setup(self, sync_permissions):
        self.ano, _ = Ano.objects.get_or_create(ano=2026)
        self.avaliacao = Avaliacao.objects.create(ano=self.ano, descricao='Avaliação Teste')
        self.segmento = Segmento.objects.create(descricao='Servidor', forma_identificacao='teste')
        self.questionario = Questionario.objects.create(
            avaliacao=self.avaliacao,
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
        )
        self.questionario.segmentos.add(self.segmento)

        self.setor_uo = Setor.objects.create(sigla='CT', nome='Setor Campus')
        self.uo = UnidadeOrganizacional.objects.create(sigla='CT', nome='Campus Teste', setor=self.setor_uo)
        self.setor_sem_uo = Setor.objects.create(sigla='SC', nome='Setor Sem UO')

    def test_values_list_setor_uo_resolves(self):
        qs = Respondente.objects.all()
        list(qs.values_list('setor__uo', flat=True).distinct())

    def test_values_list_uo_raises_field_error(self):
        qs = Respondente.objects.all()
        with pytest.raises(FieldError):
            list(qs.values_list('uo', flat=True).distinct())

    def test_tabela_bidimensional_setor_uo_with_respondentes(self):
        from rh.models import Servidor
        from comum.models import Vinculo

        ct_servidor = ContentType.objects.get(app_label='rh', model='servidor')
        # Constrói o servidor em vez de garimpar um do banco. O `Servidor.objects.first()`
        # que havia aqui só achava alguém porque uma fixture commitada de outro módulo
        # deixava servidores para trás; sem isso o teste se auto-pulava e não testava nada.
        pessoa = ServidorFactory()
        vinculo = pessoa.get_vinculo() or Vinculo.objects.create(
            tipo_relacionamento=ct_servidor,
            id_relacionamento=pessoa.pk,
            secret=0,
            pessoa_id=pessoa.pessoa_id,
        )
        Respondente.objects.create(
            questionario=self.questionario,
            segmento=self.segmento,
            vinculo=vinculo,
            setor=self.setor_uo,
            finalizado=False,
        )
        qs = self.questionario.respondente_set.all()
        tabela = TabelaBidimensional(
            'Quadro Resumo',
            qs=qs,
            vertical_key='setor__uo',
            vertical_source=UnidadeOrganizacional,
            horizontal_key='segmento',
            horizontal_source=Segmento,
            vertical_header_name='Unidade Organizacional',
            vertical_include_null_value=True,
        )
        assert len(tabela.registros) >= 1
