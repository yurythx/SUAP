# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``rsc``."""

from datetime import date
from uuid import uuid4

import factory
from factory.django import DjangoModelFactory

from djtools.utils import get_datetime_now

from rh.tests.factories import ServidorFactory
from rsc.models import ArquivosExigidos, Avaliacao, CategoriaMemorialDescritivo, Criterio, Diretriz, ProcessoAvaliador, ProcessoRSC, TipoRsc, Unidade


class TipoRscFactory(DjangoModelFactory):
    class Meta:
        model = TipoRsc
        django_get_or_create = ('nome', 'categoria')

    nome = 'RSC-III'
    categoria = 'Docente'


class ProcessoRSCFactory(DjangoModelFactory):
    """Processo aguardando a seleção da banca. O ``ServidorFactory`` exige a fixture ``sync_permissions``."""

    class Meta:
        model = ProcessoRSC

    servidor = factory.SubFactory(ServidorFactory)
    tipo_rsc = factory.SubFactory(TipoRscFactory)
    status = ProcessoRSC.STATUS_AGUARDANDO_AVALIADORES


class UnidadeFactory(DjangoModelFactory):
    class Meta:
        model = Unidade
        django_get_or_create = ('nome',)

    nome = 'Unidade'
    sigla = 'UN'


class CategoriaMemorialDescritivoFactory(DjangoModelFactory):
    class Meta:
        model = CategoriaMemorialDescritivo

    nome = 'Itinerário de formação'


class DiretrizFactory(DjangoModelFactory):
    class Meta:
        model = Diretriz

    tipo_rsc = factory.SubFactory(TipoRscFactory)
    nome = factory.Sequence(lambda n: f'Diretriz {n}')
    descricao = 'Diretriz'
    peso = 1
    teto = 10


class CriterioFactory(DjangoModelFactory):
    class Meta:
        model = Criterio

    diretriz = factory.SubFactory(DiretrizFactory)
    numero = factory.Sequence(lambda n: n)
    nome = 'Critério'
    status = Criterio.STATUS_ATIVO
    fator = 1
    unidade = factory.SubFactory(UnidadeFactory)
    teto = 10
    categoria_memorial_descritivo = factory.SubFactory(CategoriaMemorialDescritivoFactory)


class ConfiguracaoRSCFactory(DjangoModelFactory):
    """A configuração única do módulo; os textos de e-mail só precisam existir."""

    class Meta:
        model = 'rsc.ConfiguracaoRSC'
        django_get_or_create = ('descricao',)

    descricao = 'CONFIG_RSC'
    dias_para_aceite = 7
    dias_para_avaliacao = 15
    pontos_soma_rsc = 50
    pontos_rsc_pretendido = 25
    email_professor_sorteado = '<p>Prezado(a) {{ NOME_AVALIADOR }}</p>'
    email_sem_avaliador_reserva = '<p>Processo {{ PROCESSO_RSC }} sem reserva</p>'
    email_professor_perdeu_prazo = '<p>Prazo perdido</p>'
    email_lembrete_avaliacao = '<p>Lembrete de avaliação</p>'
    instrucoes_gerais = '<p>Instruções gerais</p>'
    instrucoes_gerais_avaliador = '<p>Instruções ao avaliador</p>'


class ArquivoFactory(DjangoModelFactory):
    """Documento comprobatório de um critério; o PDF do ``diretorio`` é gravado por quem chama."""

    class Meta:
        model = 'rsc.Arquivo'

    processo = factory.SubFactory(ProcessoRSCFactory)
    criterio = factory.SubFactory(CriterioFactory)
    nome = 'comprovante.pdf'
    diretorio = factory.Sequence(lambda n: f'private-media/rsc/e2e/{uuid4().hex}-{n}.pdf')
    qtd_itens = 1
    nota_pretendida = 1
    data_referencia = factory.LazyFunction(lambda: date(2015, 1, 1))
    tamanho = 1
    descricao = 'Descrição do comprovante'


class ArquivosExigidosFactory(DjangoModelFactory):
    class Meta:
        model = ArquivosExigidos

    processo = factory.SubFactory(ProcessoRSCFactory)
    nome = 'documento.pdf'
    diretorio = factory.Sequence(lambda n: f'private-media/rsc/e2e/{uuid4().hex}-exigido-{n}.pdf')
    tamanho = 1
    tipo = ArquivosExigidos.TITULO_MESTRADO_ESPECIALIZACAO_GRADUACAO


class ProcessoAvaliadorFactory(DjangoModelFactory):
    """Avaliador interno convidado; ``avaliador`` vem de quem chama."""

    class Meta:
        model = ProcessoAvaliador

    processo = factory.SubFactory(ProcessoRSCFactory)
    status = ProcessoAvaliador.AGUARDANDO_ACEITE
    tipo_avaliador = ProcessoAvaliador.AVALIADOR_INTERNO
    data_convite = factory.LazyFunction(get_datetime_now)


class AvaliacaoFactory(DjangoModelFactory):
    class Meta:
        model = Avaliacao

    processo = factory.SubFactory(ProcessoRSCFactory)
    status = Avaliacao.EM_AVALIACAO
    motivo_indeferimento = ''
    tipo_avaliador = Avaliacao.AVALIADOR_INTERNO


class AvaliacaoItemFactory(DjangoModelFactory):
    class Meta:
        model = 'rsc.AvaliacaoItem'

    avaliacao = factory.SubFactory(AvaliacaoFactory)
    arquivo = factory.SubFactory(ArquivoFactory)


class ParametroPagamentoFactory(DjangoModelFactory):
    class Meta:
        model = 'rsc.ParametroPagamento'

    valor_por_avaliacao = 100.0
    hora_por_avaliacao = 2
