# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy do app auditoria (domínio de monitoramento).

Cobre relatório, recomendação, monitoramento, solicitação de providência,
manifestação, posicionamento e dados de referência.

As factories de modelos de **outros apps** moram no app dono (e são reusadas
aqui): ``AnoFactory`` em ``comum.tests.factories``; ``Funcao``/``ServidorFuncaoHistorico``
em ``rh.tests.factories``. O substrato pesado (``Setor``, ``Servidor``, ``Vinculo``)
vem do fixture ``suap_data`` (ver ``comum.pytest_fixtures``).
"""

from __future__ import annotations

from datetime import date, timedelta

import factory
from factory.django import DjangoModelFactory

from comum.tests.factories import AnoFactory
from djtools.utils import get_datetime_now
from rh.tests.factories import FuncaoChefiaFactory, ServidorFuncaoChefiaFactory  # reexportadas para os testes

from auditoria.models import (
    Acao,
    AlcanceEstrategico,
    ClasseBeneficio,
    UnidadeAfetada,
    AfastamentoPlanejado,
    Manifestacao,
    Monitoramento,
    Motivacao,
    NucleoAuditoria,
    Paint,
    PlanejamentoAnual,
    PlanejamentoMensal,
    Posicionamento,
    Recomendacao,
    Relatorio,
    SolicitacaoProvidencia,
    TipoAfastamento,
    TipoPosicionamentoValido,
    TipoServico,
)
from auditoria.models.afastamento import StatusAfastamento
from auditoria.models.manifestacao import ManifestacaoStatus, TipoManifestacao
from auditoria.models.monitoramento import IndicacaoServidorMonitoramento, MonitoramentoStatus
from auditoria.models.posicionamento import PosicionamentoStatus, TipoPosicionamento


def hoje() -> date:
    return get_datetime_now().date()


class TipoServicoFactory(DjangoModelFactory):
    class Meta:
        model = TipoServico
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Tipo de Serviço {n}')


class AcaoFactory(DjangoModelFactory):
    class Meta:
        model = Acao
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Ação {n}')
    tipo_servico = factory.SubFactory(TipoServicoFactory)


class NucleoAuditoriaFactory(DjangoModelFactory):
    class Meta:
        model = NucleoAuditoria
        django_get_or_create = ('nome',)

    # max_length=25
    nome = factory.Sequence(lambda n: f'Núcleo {n}')
    # coordenador: Vinculo, informado pelo chamador.


class RelatorioFactory(DjangoModelFactory):
    class Meta:
        model = Relatorio

    numero = factory.Sequence(lambda n: n + 1)
    ano = factory.SubFactory(AnoFactory)
    ano_paint = factory.SubFactory(AnoFactory)
    acao = factory.SubFactory(AcaoFactory)
    # nucleo: informado pelo chamador (precisa de coordenador Vinculo).
    data_inicio = factory.LazyFunction(lambda: hoje() - timedelta(days=365))
    data_fim = factory.LazyFunction(hoje)


class RecomendacaoFactory(DjangoModelFactory):
    class Meta:
        model = Recomendacao

    relatorio = factory.SubFactory(RelatorioFactory)
    nucleo = factory.SelfAttribute('relatorio.nucleo')
    data_limite = factory.LazyFunction(lambda: hoje() + timedelta(days=365))
    # monitor: Vinculo, informado pelo chamador.
    # numero/ano: gerados em Recomendacao.save() (exigem Ano do ano corrente).


class MonitoramentoFactory(DjangoModelFactory):
    class Meta:
        model = Monitoramento

    status = MonitoramentoStatus.REGISTRADO
    # recomendacao, unidade: informados pelo chamador.


class SolicitacaoProvidenciaFactory(DjangoModelFactory):
    class Meta:
        model = SolicitacaoProvidencia

    motivo = 'Solicitação de providências.'
    prazo_atendimento = factory.LazyFunction(lambda: hoje() + timedelta(days=30))
    # monitoramento, setor: informados pelo chamador.


class ManifestacaoFactory(DjangoModelFactory):
    class Meta:
        model = Manifestacao

    tipo = TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS
    texto = 'Providências adotadas conforme recomendação.'
    status = ManifestacaoStatus.REGISTRADA
    # monitoramento, solicitacao_providencia, incluido_por: informados pelo chamador
    # (incluido_por é CurrentUserField null=False — sem request, deve ser passado).


class IndicacaoServidorMonitoramentoFactory(DjangoModelFactory):
    """Servidor indicado pela chefia para redigir a manifestação do monitoramento."""

    class Meta:
        model = IndicacaoServidorMonitoramento

    # monitoramento, servidor (Vinculo), indicado_por (User): informados pelo chamador
    # (indicado_por é CurrentUserField — sem request, deve ser passado).


class MotivacaoAtendimentoFactory(DjangoModelFactory):
    class Meta:
        model = Motivacao
        django_get_or_create = ('tipo_posicionamento', 'motivo')

    tipo_posicionamento = TipoPosicionamento.ATENDIMENTO
    motivo = 'Providências atendidas'


class TipoPosicionamentoValidoAtendimentoFactory(DjangoModelFactory):
    """Vincula manifestação de encaminhamento de providências ao posicionamento de atendimento."""

    class Meta:
        model = TipoPosicionamentoValido
        django_get_or_create = ('tipo_manifestacao', 'tipo_posicionamento')

    tipo_manifestacao = TipoManifestacao.ENCAMINHAMENTO_PROVIDENCIAS
    tipo_posicionamento = TipoPosicionamento.ATENDIMENTO


class PosicionamentoFactory(DjangoModelFactory):
    class Meta:
        model = Posicionamento

    tipo = TipoPosicionamento.ATENDIMENTO
    motivacao = factory.SubFactory(MotivacaoAtendimentoFactory)
    parecer = 'Parecer favorável ao atendimento.'
    status = PosicionamentoStatus.REGISTRADO
    # manifestacao, incluido_por: informados pelo chamador.


class PaintFactory(DjangoModelFactory):
    """Plano Anual de Auditoria Interna de um ano."""

    class Meta:
        model = Paint
        django_get_or_create = ('ano',)

    ano = factory.SubFactory(AnoFactory)


class PlanejamentoAnualFactory(DjangoModelFactory):
    """Planejamento anual de um auditor dentro de um PAINT.

    ``auditor`` vem do substrato (``suap_data``); ``paint`` costuma ser informado
    junto, para que ambos apontem para o mesmo ano.
    """

    class Meta:
        model = PlanejamentoAnual
        django_get_or_create = ('auditor', 'paint')

    paint = factory.SubFactory(PaintFactory)


class PlanejamentoMensalFactory(DjangoModelFactory):
    class Meta:
        model = PlanejamentoMensal
        django_get_or_create = ('planejamento_anual', 'mes')

    planejamento_anual = factory.SubFactory(PlanejamentoAnualFactory)
    mes = 1


class TipoAfastamentoFactory(DjangoModelFactory):
    class Meta:
        model = TipoAfastamento
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Tipo de Afastamento {n}')


class AfastamentoPlanejadoFactory(DjangoModelFactory):
    """Afastamento declarado no planejamento mensal.

    ``status`` é FSM protegido: só aceita atribuição na construção, que é
    exatamente o que o factory_boy faz. O padrão é ``HOMOLOGADO`` porque é esse
    o estado que entra no cálculo de carga horária.
    """

    class Meta:
        model = AfastamentoPlanejado

    planejamento = factory.SubFactory(PlanejamentoMensalFactory)
    tipo_afastamento = factory.SubFactory(TipoAfastamentoFactory)
    motivo = 'Afastamento de teste'
    status = StatusAfastamento.HOMOLOGADO
    importado = False
    # data_inicio / data_fim: informados pelo chamador.


class ClasseBeneficioFactory(DjangoModelFactory):
    class Meta:
        model = ClasseBeneficio
        django_get_or_create = ('tipo', 'descricao')

    tipo = 1
    descricao = factory.Sequence(lambda n: f'Classe de benefício {n}')


class AlcanceEstrategicoFactory(DjangoModelFactory):
    class Meta:
        model = AlcanceEstrategico
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Alcance estratégico {n}')


class UnidadeAfetadaFactory(DjangoModelFactory):
    class Meta:
        model = UnidadeAfetada
        django_get_or_create = ('nome',)

    nome = factory.Sequence(lambda n: f'Unidade afetada {n}')
