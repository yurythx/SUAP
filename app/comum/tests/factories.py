# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``comum``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory).
"""

from __future__ import annotations

from uuid import uuid4

import factory
from django.db import connection
from django.db.models import Model
from factory.django import DjangoModelFactory

from comum.models import (
    Ano,
    AreaAtuacao,
    CategoriaNotificacao,
    ObjetivoDesenvolvimentoSustentavel,
    Municipio,
    PessoaEndereco,
    Predio,
    Preferencia,
    PreferenciaNotificacao,
    PrestadorServico,
    Sala,
    SubobjetivoDesenvolvimentoSustentavel,
    User,
)
from djtools.utils import get_datetime_now
from rh.tests.factories import PessoaFisicaFactory, SetorFactory


def _sincronizar_sequencia(model: type[Model]) -> None:
    """Avança a sequência de pk para além dos ids explícitos recém-inseridos.

    Inserir com id explícito não move a sequência; sem isto, o próximo INSERT sem id
    colide com uma linha existente.
    """
    if connection.vendor == 'postgresql':
        tabela = model._meta.db_table
        coluna = model._meta.pk.column
        maior = model.objects.order_by('-pk').values_list('pk', flat=True).first() or 1
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT setval(pg_get_serial_sequence('{tabela}', '{coluna}'), %s, true)", [maior])


class MunicipioFactory(DjangoModelFactory):
    """Município com identificação única, inclusive quando o banco é reusado."""

    class Meta:
        model = Municipio

    nome = factory.LazyFunction(lambda: f'Município {uuid4().hex}')
    uf = 'RN'


class PessoaEnderecoFactory(DjangoModelFactory):
    """Endereço de uma pessoa; município e pessoa podem ser informados pelo fluxo."""

    class Meta:
        model = PessoaEndereco

    pessoa = factory.SubFactory(PessoaFisicaFactory)
    municipio = factory.SubFactory(MunicipioFactory)
    logradouro = 'Rua de Teste'
    numero = '10'
    cep = '59000-000'


class AnoFactory(DjangoModelFactory):
    class Meta:
        model = Ano
        django_get_or_create = ('ano',)

    ano = factory.LazyFunction(lambda: get_datetime_now().year)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ('username',)

    username = factory.Sequence(lambda n: f'usuario_{n}')


class AreaAtuacaoFactory(DjangoModelFactory):
    """Área de atuação (o ``slug`` é preenchido pelo ``AutoSlugField`` a partir do nome)."""

    class Meta:
        model = AreaAtuacao
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Área de Atuação {n}')


class PessoaTelefoneFactory(DjangoModelFactory):
    """Telefone de uma pessoa; ``pessoa`` vem de quem chama."""

    class Meta:
        model = 'comum.PessoaTelefone'

    numero = '(84) 4005-0000'


class PrestadorServicoFactory(DjangoModelFactory):
    """Prestador de serviço. Informe ``setor``; sem ele o prestador fica sem lotação.

    O ``save`` do prestador troca a matrícula pelos dígitos do CPF: para o get-or-create pela
    matrícula valer entre sessões (``--reuse-db``), passe ``pessoa_fisica__cpf`` fixo e a
    ``matricula`` com os mesmos dígitos.
    """

    class Meta:
        model = PrestadorServico
        django_get_or_create = ('matricula',)
        skip_postgeneration_save = True

    matricula = factory.Sequence(lambda n: f'{50621364401 + n}')
    pessoa_fisica = factory.SubFactory(PessoaFisicaFactory)

    @factory.post_generation
    def pessoa_salva_depois_do_vinculo(obj: PrestadorServico, create: bool, extracted: object, **kwargs: object) -> None:
        """Salva a pessoa depois do prestador: é o ``save`` dela que marca ``eh_prestador`` e monta
        a busca do autocomplete a partir do vínculo, que só existe agora. Sem isso
        ``PessoaFisica.get_vinculo()`` quebra (500 na tela do NAPNE do edu)."""
        if create:
            obj.pessoa_fisica.save()


class PredioFactory(DjangoModelFactory):
    """Prédio de um campus — só existe para pendurar salas."""

    class Meta:
        model = Predio

    nome = factory.Sequence(lambda n: f'Prédio {n}')
    # Quem cria campus é o SetorFactory: a UnidadeOrganizacional exige o setor que a nomeia.
    uo = factory.LazyFunction(lambda: SetorFactory().uo)


class SalaFactory(DjangoModelFactory):
    """Sala. O campus da sala é o do prédio (``Sala.ativas`` filtra por ``predio__uo``)."""

    class Meta:
        model = Sala

    nome = factory.Sequence(lambda n: f'Sala {n}')
    predio = factory.SubFactory(PredioFactory)


class CategoriaNotificacaoFactory(DjangoModelFactory):
    """Categoria de notificação.

    ``forcar_habilitacao=False`` por padrão porque é esse o filtro das seis views de preferência
    (``comum/views.py``): com ele ligado, a ação roda e não muda nada.
    """

    class Meta:
        model = CategoriaNotificacao

    assunto = factory.Sequence(lambda n: f'Categoria de Notificação {n}')
    ativa = True
    forcar_habilitacao = False


class PreferenciaFactory(DjangoModelFactory):
    """Preferência padrão (tema e canais de envio) de um usuário. Informe ``usuario``."""

    class Meta:
        model = Preferencia


class PreferenciaNotificacaoFactory(DjangoModelFactory):
    """Preferência de notificação de um vínculo. Informe ``vinculo``; é ele o dono do registro."""

    class Meta:
        model = PreferenciaNotificacao

    categoria = factory.SubFactory(CategoriaNotificacaoFactory)
    via_suap = True
    via_email = True


class ObjetivoDesenvolvimentoSustentavelFactory(DjangoModelFactory):
    """Objetivo de Desenvolvimento Sustentável da ONU (ODS)."""

    class Meta:
        model = ObjetivoDesenvolvimentoSustentavel

    descricao = factory.Sequence(lambda n: f'ODS {n}')


class SubobjetivoDesenvolvimentoSustentavelFactory(DjangoModelFactory):
    """Subobjetivo (meta) de um ODS. ``numero`` é único."""

    class Meta:
        model = SubobjetivoDesenvolvimentoSustentavel

    descricao = factory.Sequence(lambda n: f'Meta {n}')
    numero = factory.Sequence(lambda n: f'M-{n}')
    objetivo = factory.SubFactory(ObjetivoDesenvolvimentoSustentavelFactory)
