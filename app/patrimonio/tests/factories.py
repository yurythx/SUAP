"""Factories dos models do patrimônio.

Nada aqui reproduz operação de domínio: factory cria linha. Gerar tombamento continua
sendo efeito do ``EntradaPermanente.save()`` (um ``Inventario`` por unidade de ``qtd``),
e baixar/transferir continua sendo ``Inventario.efetuar_baixa()`` /
``efetuar_transferencia()``, que são quem mantém os invariantes.

``django_get_or_create`` nas tabelas de referência (status, tipos de movimento, tipo de
baixa): elas são populadas por carga inicial em produção e são consultadas por nome
(``InventarioStatus.ATIVO()``), então duplicá-las quebra os testes em vez de isolá-los.
"""

from __future__ import annotations

from datetime import date, datetime

import factory
from factory.django import DjangoModelFactory

from almoxarifado.models import EntradaTipo, MaterialTipo
from almoxarifado.tests.factories import EntradaFactory as EntradaAlmoxarifadoFactory
from patrimonio.models import (
    Baixa,
    BaixaTipo,
    CategoriaMaterialPermanente,
    Cautela,
    CautelaInventario,
    ConferenciaItem,
    ConferenciaSala,
    EntradaPermanente,
    InventarioRotulo,
    InventarioStatus,
    InventarioTipoUsoPessoal,
    InventarioValor,
    MovimentoPatrimTipo,
    PlanoContas,
    Requisicao,
    RequisicaoItem,
)
from rh.tests.factories import SetorFactory


class InventarioStatusFactory(DjangoModelFactory):
    """Status do tombamento. Os três nomes são fixos: pendente, ativo e baixado."""

    class Meta:
        model = InventarioStatus
        django_get_or_create = ('nome',)

    nome = 'pendente'


class MovimentoPatrimTipoFactory(DjangoModelFactory):
    """Tipo de movimento: pendência, transferência, baixa ou estorno."""

    class Meta:
        model = MovimentoPatrimTipo
        django_get_or_create = ('nome',)

    nome = 'pendência'


class PlanoContasFactory(DjangoModelFactory):
    class Meta:
        model = PlanoContas
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'{n:02d}')
    descricao = factory.Sequence(lambda n: f'Plano de Contas {n}')


class CategoriaMaterialPermanenteFactory(DjangoModelFactory):
    """Elemento de despesa: é dele que saem vida útil e residual da depreciação.

    O código começa em 0100 de propósito: vários pontos do módulo tratam códigos curtos
    como reservados ('00', '05', '90', '94', '99', '9907'), excluindo-os da depreciação e
    das totalizações. Uma sequência de dois dígitos cairia neles e o teste passaria a
    medir a exclusão em vez do fluxo.
    """

    class Meta:
        model = CategoriaMaterialPermanente
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'{n + 100:04d}')
    nome = factory.Sequence(lambda n: f'Elemento de Despesa Permanente {n}')
    plano_contas = factory.SubFactory(PlanoContasFactory)


class EntradaPermanenteFactory(DjangoModelFactory):
    """Item de entrada de material permanente.

    Salvar cria ``qtd`` inventários pendentes (``item.inventario_set``) — é o caminho
    normal de nascimento de um tombamento, e por isso os testes constroem inventário
    por aqui em vez de instanciar ``Inventario`` direto.
    """

    class Meta:
        model = EntradaPermanente

    entrada = factory.SubFactory(
        EntradaAlmoxarifadoFactory,
        # Doação para não exigir empenho; quem cria campus é o SetorFactory.
        tipo_entrada=factory.LazyFunction(EntradaTipo.DOACAO),
        tipo_material=factory.LazyFunction(MaterialTipo.PERMANENTE),
        uo=factory.LazyFunction(lambda: SetorFactory().uo),
    )
    categoria = factory.SubFactory(CategoriaMaterialPermanenteFactory)
    descricao = factory.Sequence(lambda n: f'Item permanente {n}')
    qtd = 1
    valor = 100


class InventarioRotuloFactory(DjangoModelFactory):
    """Rótulo de inventário. ``unidade_organizacional`` tem ``default=get_uo`` (threadlocal),
    então o campus precisa vir explícito fora de um request."""

    class Meta:
        model = InventarioRotulo

    nome = factory.Sequence(lambda n: f'Rótulo {n}')
    descricao = 'Rótulo de teste'


class InventarioTipoUsoPessoalFactory(DjangoModelFactory):
    class Meta:
        model = InventarioTipoUsoPessoal

    descricao = factory.Sequence(lambda n: f'Notebook {n}')


class BaixaTipoFactory(DjangoModelFactory):
    class Meta:
        model = BaixaTipo
        django_get_or_create = ('nome',)

    nome = 'doacao'


class BaixaFactory(DjangoModelFactory):
    """Portaria de baixa. Os itens entram por ``Inventario.efetuar_baixa()``."""

    class Meta:
        model = Baixa

    tipo = factory.SubFactory(BaixaTipoFactory)
    data = factory.LazyFunction(datetime.now)
    numero = factory.Sequence(lambda n: f'{n:05d}/2026')
    observacao = 'Baixa de teste'


class CautelaFactory(DjangoModelFactory):
    class Meta:
        model = Cautela

    responsavel = factory.Sequence(lambda n: f'Responsável {n}')
    data_inicio = factory.LazyFunction(date.today)
    data_fim = factory.LazyFunction(date.today)
    descricao = factory.Sequence(lambda n: f'Cautela {n}')


class CautelaInventarioFactory(DjangoModelFactory):
    class Meta:
        model = CautelaInventario

    cautela = factory.SubFactory(CautelaFactory)


class ConferenciaSalaFactory(DjangoModelFactory):
    """Conferência de uma sala. O ``token`` do QRCode é calculado no ``save()``."""

    class Meta:
        model = ConferenciaSala

    observacao = ''


class ConferenciaItemFactory(DjangoModelFactory):
    class Meta:
        model = ConferenciaItem

    conferencia = factory.SubFactory(ConferenciaSalaFactory)
    dh_coleta = factory.LazyFunction(datetime.now)


class RequisicaoFactory(DjangoModelFactory):
    """Requisição de transferência. Nasce aguardando o servidor de destino, como na tela."""

    class Meta:
        model = Requisicao

    status = Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO


class RequisicaoItemFactory(DjangoModelFactory):
    """Item da requisição: o bem que muda de mãos."""

    class Meta:
        model = RequisicaoItem

    requisicao = factory.SubFactory(RequisicaoFactory)


class InventarioValorFactory(DjangoModelFactory):
    """Depreciação mensal de um bem — uma linha por mês fechado (``data`` = último dia)."""

    class Meta:
        model = InventarioValor

    percentual_residual = 0.1
    vida_util_em_anos = 10
    valor = 100
