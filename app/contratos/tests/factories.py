"""Factories de contratos: tabelas de apoio, contrato, fiscal, cronograma e empenho vinculado."""

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from contratos.models import BaseLegal, Contrato, Cronograma, DocumentoEmpenhoContrato, Fiscal, Parcela, SubtipoContrato, TipoContrato, TipoFiscal
from rh.tests.factories import PessoaJuridicaFactory, SetorFactory
from tesouro_gerencial.tests.factories import DocumentoEmpenhoFactory


class TipoContratoFactory(DjangoModelFactory):
    class Meta:
        model = TipoContrato
        django_get_or_create = ('descricao',)

    descricao = 'Contrato'


class SubtipoContratoFactory(DjangoModelFactory):
    class Meta:
        model = SubtipoContrato
        django_get_or_create = ('descricao', 'tipo')

    descricao = 'Serviço de manutenção'
    tipo = factory.SubFactory(TipoContratoFactory)


class BaseLegalFactory(DjangoModelFactory):
    class Meta:
        model = BaseLegal
        django_get_or_create = ('titulo',)

    titulo = 'Base legal de demonstração'
    vigencia = 12
    prorrogacao = 48


class ContratoFactory(DjangoModelFactory):
    """Contrato de despesa vigente, gerenciado e atendido pelo campus de ``campus_gerenciador``.

    Exige empenho na medição (``permite_medicao_sem_empenho=False``), como o padrão do model.
    Sem ``processo``: o ``Processo.save`` exige ``vinculo_cadastro`` com setor, então quem precisa
    (ex.: o form de medição) informa ``processo=ProcessoFactory(vinculo_cadastro=..., setor_origem=...)``.
    """

    class Meta:
        model = Contrato
        skip_postgeneration_save = True

    tipo = factory.SubFactory(TipoContratoFactory)
    numero = factory.Sequence(lambda n: f'{n + 1:05d}/{date.today().year}')
    valor = Decimal('100000.00')
    data_inicio = factory.LazyFunction(lambda: date.today() - timedelta(days=30))
    data_fim = factory.LazyFunction(lambda: date.today() + timedelta(days=335))
    objeto = 'Manutenção predial de demonstração'
    processo = None
    campus_gerenciador = factory.LazyFunction(lambda: SetorFactory().uo)
    contratada = factory.SubFactory(PessoaJuridicaFactory)
    vinculo_contratado = factory.LazyAttribute(lambda o: o.contratada.get_vinculo())

    @factory.post_generation
    def campi(obj: Contrato, create: bool, extracted: object, **kwargs: object) -> None:
        if create:
            obj.campi.add(*(extracted or [obj.campus_gerenciador]))


class TipoFiscalFactory(DjangoModelFactory):
    class Meta:
        model = TipoFiscal

    descricao = 'Fiscal Técnico'


class FiscalFactory(DjangoModelFactory):
    """Fiscal ativo do contrato. O ``servidor`` é obrigatório: crie-o com ``ServidorFactory``."""

    class Meta:
        model = Fiscal

    contrato = factory.SubFactory(ContratoFactory)
    tipo = factory.SubFactory(TipoFiscalFactory)
    numero_portaria = factory.Sequence(lambda n: f'{n + 1}/{date.today().year}')
    campus = factory.SelfAttribute('contrato.campus_gerenciador')


class CronogramaFactory(DjangoModelFactory):
    class Meta:
        model = Cronograma

    numero = factory.Sequence(lambda n: f'CR{n + 1}')
    contrato = factory.SubFactory(ContratoFactory)


class ParcelaFactory(DjangoModelFactory):
    class Meta:
        model = Parcela

    cronograma = factory.SubFactory(CronogramaFactory)
    data_prevista_inicio = factory.LazyFunction(lambda: date.today().replace(day=1))
    data_prevista_fim = factory.LazyFunction(date.today)
    valor_previsto = Decimal('5000.00')


class DocumentoEmpenhoContratoFactory(DjangoModelFactory):
    """Empenho do Tesouro Gerencial vinculado ao contrato (aba Empenhos)."""

    class Meta:
        model = DocumentoEmpenhoContrato

    contrato = factory.SubFactory(ContratoFactory)
    empenho = factory.SubFactory(DocumentoEmpenhoFactory)
    descricao = ''
