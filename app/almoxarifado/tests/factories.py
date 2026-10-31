"""Factories do almoxarifado, compartilhadas entre a suíte unitária e a de e2e.

Substituem a construção imperativa de dado que estava duplicada nos dois conftests (os
tipos de movimento, por exemplo, eram criados em `tests/conftest.py` e de novo em
`tests/e2e/conftest.py`).

``django_get_or_create`` em quase todas: a suíte e2e **nunca dá flush**, então cada factory
tem de reencontrar a linha em vez de duplicá-la a cada run. A exceção é
``RequisicaoAlmoxUserFactory`` — ver a docstring dela.

Nada aqui reproduz operação de domínio. Factory cria linha; dar entrada em estoque continua
sendo ``EmpenhoConsumo.efetuar_entrada()`` e atender requisição continua sendo
``avaliar()``, porque são eles que mantêm os invariantes de saldo.
"""

from __future__ import annotations

from datetime import datetime

import factory
from factory.django import DjangoModelFactory

from almoxarifado.models import (
    CategoriaMaterialConsumo,
    Empenho,
    EmpenhoConsumo,
    Entrada,
    EntradaTipo,
    MaterialConsumo,
    MaterialEstoque,
    MaterialTipo,
    MovimentoAlmoxEntradaTipo,
    MovimentoAlmoxSaidaTipo,
    RequisicaoAlmoxUser,
    RequisicaoAlmoxUserMaterial,
)


class MovimentoAlmoxEntradaTipoFactory(DjangoModelFactory):
    """Tipo de movimento de entrada. Em produção vem do ``carga_inicial_almoxarifado``."""

    class Meta:
        model = MovimentoAlmoxEntradaTipo
        django_get_or_create = ('nome',)

    nome = 'entrada'


class MovimentoAlmoxSaidaTipoFactory(DjangoModelFactory):
    """Tipo de movimento de saída — sem ele, atender requisição estoura ``DoesNotExist``.

    A view engole a exceção num redirect com mensagem, então a falta desta linha aparece
    como "o usuário volta para a fila sem entender". Os dois nomes são fixos, consultados por
    ``MovimentoAlmoxSaidaTipo.REQUISICAO_USER_MATERIAL()`` e ``..._UO_MATERIAL()``.
    """

    class Meta:
        model = MovimentoAlmoxSaidaTipo
        django_get_or_create = ('nome',)

    nome = 'requisicao_user_material'


class CategoriaMaterialConsumoFactory(DjangoModelFactory):
    """Elemento de despesa de material de consumo."""

    class Meta:
        model = CategoriaMaterialConsumo
        django_get_or_create = ('codigo',)

    codigo = factory.Sequence(lambda n: f'{n:02d}')
    nome = factory.Sequence(lambda n: f'Elemento de Despesa {n}')


class MaterialConsumoFactory(DjangoModelFactory):
    class Meta:
        model = MaterialConsumo
        django_get_or_create = ('nome',)

    categoria = factory.SubFactory(CategoriaMaterialConsumoFactory)
    nome = factory.Sequence(lambda n: f'Material de Consumo {n}')


class EmpenhoFactory(DjangoModelFactory):
    """Empenho de consumo. O ``numero`` respeita o formato validado na UI: 9999NE123456."""

    class Meta:
        model = Empenho
        django_get_or_create = ('numero',)

    numero = factory.Sequence(lambda n: f'2019NE{n:06d}')
    tipo_material = factory.LazyFunction(MaterialTipo.CONSUMO)


class EmpenhoConsumoFactory(DjangoModelFactory):
    """Item de empenho — a origem de todo material que entra no estoque.

    ``qtd_empenhada`` alta de propósito: é dela que sai o saldo para as entradas, e a suíte
    não dá flush, então o empenhado vai sendo consumido ao longo das runs.
    """

    class Meta:
        model = EmpenhoConsumo
        django_get_or_create = ('empenho', 'material')

    empenho = factory.SubFactory(EmpenhoFactory)
    material = factory.SubFactory(MaterialConsumoFactory)
    qtd_empenhada = 5000
    valor = 10


class MaterialEstoqueFactory(DjangoModelFactory):
    """Saldo do material num campus. Começa zerado — quem credita é ``efetuar_entrada``."""

    class Meta:
        model = MaterialEstoque
        django_get_or_create = ('material', 'uo')

    material = factory.SubFactory(MaterialConsumoFactory)
    valor_medio = 0
    quantidade = 0


class EntradaFactory(DjangoModelFactory):
    """Entrada de compra. Não credita estoque por si — isso é ``efetuar_entrada(entrada, qtd)``."""

    class Meta:
        model = Entrada

    data = factory.LazyFunction(datetime.now)
    tipo_entrada = factory.LazyFunction(EntradaTipo.COMPRA)
    tipo_material = factory.LazyFunction(MaterialTipo.CONSUMO)


class RequisicaoAlmoxUserFactory(DjangoModelFactory):
    """Requisição de saída de material por um servidor.

    **Sem** ``django_get_or_create``, ao contrário das outras: uma requisição atendida deixa
    de estar pendente, então reaproveitá-la entre testes (ou entre runs, já que não há
    flush) faria o teste seguinte encontrar a requisição já respondida.
    """

    class Meta:
        model = RequisicaoAlmoxUser


class RequisicaoAlmoxUserMaterialFactory(DjangoModelFactory):
    """Item da requisição: qual material e quanto."""

    class Meta:
        model = RequisicaoAlmoxUserMaterial

    requisicao = factory.SubFactory(RequisicaoAlmoxUserFactory)
    material = factory.SubFactory(MaterialConsumoFactory)
    qtd = 3
