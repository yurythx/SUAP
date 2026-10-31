import factory
from factory.django import DjangoModelFactory

from gerenciador_projetos.models import Projeto, Tarefa
from rh.tests.factories import SetorFactory, UnidadeOrganizacionalFactory


class ProjetoFactory(DjangoModelFactory):
    """Projeto privado (o padrão do model). Informe `criado_por`: criar um servidor só para isso custa caro."""

    class Meta:
        model = Projeto

    titulo = factory.Sequence(lambda n: f'Projeto {n}')
    descricao = 'Descrição do projeto'
    uo = factory.LazyFunction(lambda: UnidadeOrganizacionalFactory(setor=SetorFactory(campus=False)))


class TarefaFactory(DjangoModelFactory):
    """Informe `projeto` e `criado_por`."""

    class Meta:
        model = Tarefa

    titulo = factory.Sequence(lambda n: f'Tarefa {n}')
