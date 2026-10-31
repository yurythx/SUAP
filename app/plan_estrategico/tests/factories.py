"""Factories do plan_estrategico: PDI, plano de atividade, planos internos, requisições e execução orçamentária."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from comum.tests.factories import AnoFactory
from financeiro.tests.factories import AcaoFactory, CategoriaApropriacaoFactory, GrupoNaturezaDespesaFactory
from plan_estrategico import models
from rh.tests.factories import SetorFactory


class PDIFactory(DjangoModelFactory):
    class Meta:
        model = models.PDI
        django_get_or_create = ('ano_inicial_pdi', 'ano_final_pdi')

    ano_inicial_pdi = factory.SubFactory(AnoFactory)
    ano_final_pdi = factory.SubFactory(AnoFactory, ano=factory.LazyFunction(lambda: date.today().year + 4))
    qtd_anos = 5
    documento = 'plan_estrategico/anexos/pdi.pdf'


class UnidadeGestoraFactory(DjangoModelFactory):
    """UG do PDI; ``codigo_ug`` é o código SIAFI pelo qual os empenhos do tesouro voltam à unidade."""

    class Meta:
        model = models.UnidadeGestora

    pdi = factory.SubFactory(PDIFactory)
    setor_equivalente = factory.SubFactory(SetorFactory)
    tipo = models.UnidadeGestora.TIPO_CAMPUS
    codigo_macroprocesso = '01'
    codigo_ug = '999001'


class ProjetoEstrategicoFactory(DjangoModelFactory):
    """Macroprocesso: o ``save`` copia o ``codigo`` de ``unidade_gestora.codigo_macroprocesso``."""

    class Meta:
        model = models.ProjetoEstrategico

    pdi = factory.SelfAttribute('unidade_gestora.pdi')
    unidade_gestora = factory.SubFactory(UnidadeGestoraFactory)
    nome = 'Manutenção do campus'


class PlanoInternoFactory(DjangoModelFactory):
    class Meta:
        model = models.PlanoInterno

    codigo = 'DOCCT'
    projeto_estrategico = factory.SubFactory(ProjetoEstrategicoFactory)
    pdi = factory.SelfAttribute('projeto_estrategico.pdi')
    acao = factory.SubFactory(AcaoFactory)
    categoria_apropriacao = factory.SubFactory(CategoriaApropriacaoFactory)
    gnd = factory.SubFactory(GrupoNaturezaDespesaFactory)
    descricao = 'Manutenção'


class PlanoAtividadeFactory(DjangoModelFactory):
    """Plano do ano corrente com todas as janelas de cadastro abertas hoje."""

    class Meta:
        model = models.PlanoAtividade
        django_get_or_create = ('pdi', 'ano_base')

    pdi = factory.SubFactory(PDIFactory)
    ano_base = factory.SubFactory(AnoFactory)
    data_geral_inicial = factory.LazyFunction(lambda: date(date.today().year, 1, 1))
    data_geral_final = factory.LazyFunction(lambda: date(date.today().year, 12, 31))
    data_orcamentario_preloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_orcamentario_preloa_final = factory.SelfAttribute('data_geral_final')
    data_projetos_preloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_projetos_preloa_final = factory.SelfAttribute('data_geral_final')
    data_atividades_preloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_atividades_preloa_final = factory.SelfAttribute('data_geral_final')
    data_orcamentario_posloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_orcamentario_posloa_final = factory.SelfAttribute('data_geral_final')
    data_projetos_posloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_projetos_posloa_final = factory.SelfAttribute('data_geral_final')
    data_atividades_posloa_inicial = factory.SelfAttribute('data_geral_inicial')
    data_atividades_posloa_final = factory.SelfAttribute('data_geral_final')


class PlanoInternoPlanoAtividadeFactory(DjangoModelFactory):
    class Meta:
        model = models.PlanoInternoPlanoAtividade

    plano_interno = factory.SubFactory(PlanoInternoFactory)
    plano_atividade = factory.SubFactory(PlanoAtividadeFactory, pdi=factory.SelfAttribute('..plano_interno.pdi'))


class ProjetoPlanoAtividadeFactory(DjangoModelFactory):
    class Meta:
        model = models.ProjetoPlanoAtividade

    projeto = factory.SubFactory(ProjetoEstrategicoFactory)
    plano_atividade = factory.SubFactory(PlanoAtividadeFactory, pdi=factory.SelfAttribute('..projeto.pdi'))


class EtapaProjetoFactory(DjangoModelFactory):
    class Meta:
        model = models.EtapaProjeto

    projeto = factory.SubFactory(ProjetoEstrategicoFactory)
    codigo = factory.Sequence(lambda n: n)
    descricao = factory.Sequence(lambda n: f'Componente funcional {n}')


class EtapaProjetoPlanoAtividadeFactory(DjangoModelFactory):
    class Meta:
        model = models.EtapaProjetoPlanoAtividade

    projeto_plano_atividade = factory.SubFactory(ProjetoPlanoAtividadeFactory)
    etapa = factory.SubFactory(EtapaProjetoFactory, projeto=factory.SelfAttribute('..projeto_plano_atividade.projeto'))


class AtividadeEtapaFactory(DjangoModelFactory):
    class Meta:
        model = models.AtividadeEtapa

    etapa_projeto_plano_atividade = factory.SubFactory(EtapaProjetoPlanoAtividadeFactory)
    unidade_gestora = factory.SelfAttribute('etapa_projeto_plano_atividade.projeto_plano_atividade.projeto.unidade_gestora')
    nome = factory.Sequence(lambda n: f'Atividade {n}')
    descricao = 'Atividade do plano.'
    valor_rateio = Decimal(0)
    valor_reserva_tecnica = Decimal(0)
    valor_realocado = Decimal(0)


class RequisicaoDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.RequisicaoDespesa

    atividade = factory.SubFactory(AtividadeEtapaFactory)
    plano_atividade = factory.SelfAttribute('macroprocesso.plano_atividade')
    macroprocesso = factory.SelfAttribute('atividade.etapa_projeto_plano_atividade.projeto_plano_atividade')
    unidade_gestora = factory.SelfAttribute('atividade.unidade_gestora')
    tipo_requisicao = models.RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
    status = models.RequisicaoDespesa.STATUS_CONCLUIDA
    numero = factory.Sequence(lambda n: f'{n:05d}/{date.today().year}')
    valor = Decimal(0)


class NotaEmpenhoFactory(DjangoModelFactory):
    """Linha de empenho informada numa requisição: ``numero_empenho`` (NE) e, no reforço/anulação, ``numero_ro``."""

    class Meta:
        model = models.NotaEmpenho

    requisicao = factory.SubFactory(RequisicaoDespesaFactory)
    numero_empenho = factory.LazyFunction(lambda: f'{date.today().year}NE900001')
    status = models.NotaEmpenho.STATUS_CONFIRMADA


class MovimentacaoCreditoFactory(DjangoModelFactory):
    class Meta:
        model = models.MovimentacaoCredito

    projeto_estrategico = factory.SubFactory(ProjetoPlanoAtividadeFactory)
    plano_atividade = factory.SelfAttribute('projeto_estrategico.plano_atividade')
    tipo_requisicao = models.MovimentacaoCredito.TIPO_MOVIMENTACAO_CREDITO
    status = models.MovimentacaoCredito.STATUS_CONCLUIDA


class MovimentacaoCreditoUnidadeFactory(DjangoModelFactory):
    class Meta:
        model = models.MovimentacaoCreditoUnidade

    movimentacao = factory.SubFactory(MovimentacaoCreditoFactory)
    unidade = factory.SelfAttribute('movimentacao.projeto_estrategico.projeto.unidade_gestora')
    valor = Decimal(0)


class RequisicaoRealocacaoFactory(DjangoModelFactory):
    class Meta:
        model = models.RequisicaoRealocacao

    plano_atividade = factory.SubFactory(PlanoAtividadeFactory)
    status = models.RequisicaoRealocacao.STATUS_AGUARDANDO_APROVACAO_GESTOR_UA_CONCEDENTE
    valor_requisicao = Decimal(0)
