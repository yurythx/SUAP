# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``centralservicos``. ``AreaAtuacao`` vem de ``comum.tests.factories``."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from centralservicos.models import CategoriaServico, Comunicacao, GestorAreaServico, GrupoServico, Servico, Tag, Tarefa
from comum.tests.factories import AreaAtuacaoFactory


class CategoriaServicoFactory(DjangoModelFactory):
    class Meta:
        model = CategoriaServico

    nome = factory.Sequence(lambda n: f'Categoria de Serviço {n}')
    area = factory.SubFactory(AreaAtuacaoFactory)


class GrupoServicoFactory(DjangoModelFactory):
    """Grupo de serviço. ``categorias`` recebe a lista de categorias (de uma ou mais áreas)."""

    class Meta:
        model = GrupoServico
        skip_postgeneration_save = True

    nome = factory.Sequence(lambda n: f'Grupo de Serviço {n}')
    detalhamento = 'Detalhamento do grupo'

    @factory.post_generation
    def categorias(obj: GrupoServico, create: bool, extracted: list[CategoriaServico] | None, **kwargs: object) -> None:
        if create and extracted:
            obj.categorias.add(*extracted)


class ServicoFactory(DjangoModelFactory):
    class Meta:
        model = Servico

    nome = factory.Sequence(lambda n: f'Serviço {n}')
    tipo = Servico.TIPO_REQUISICAO
    area = factory.SubFactory(AreaAtuacaoFactory)
    grupo_servico = factory.SubFactory(GrupoServicoFactory)


class GestorAreaServicoFactory(DjangoModelFactory):
    """Gestor de uma área. O ``post_save`` do model põe o usuário no grupo "Gestor da Central de Serviços"."""

    class Meta:
        model = GestorAreaServico

    area = factory.SubFactory(AreaAtuacaoFactory)


class TagFactory(DjangoModelFactory):
    class Meta:
        model = Tag

    nome = factory.Sequence(lambda n: f'Tag {n}')
    area = factory.SubFactory(AreaAtuacaoFactory)


class ComunicacaoFactory(DjangoModelFactory):
    """Comunicação (nota interna) de um chamado, sem notificar ninguém. Exige ``chamado`` e ``remetente``."""

    class Meta:
        model = Comunicacao

    texto = factory.Sequence(lambda n: f'Comunicação {n}')
    tipo = Comunicacao.TIPO_NOTA_INTERNA

    @classmethod
    def _create(cls, model_class: type[Comunicacao], *args: object, **kwargs: object) -> Comunicacao:
        obj = model_class(*args, **kwargs)
        obj.save(suspender_notificacao=True)
        return obj


class TarefaFactory(DjangoModelFactory):
    """Cadastro prévio de tarefa de um serviço. Exige ``servico``."""

    class Meta:
        model = Tarefa

    titulo = factory.Sequence(lambda n: f'Tarefa {n}')
    descricao = 'Descrição da tarefa'
