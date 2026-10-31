"""Fixtures compartilhadas dos testes do app ``pgd2``."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

import pytest

from pgd2.models import (
    PitSetores,
    PitSolicitacaoAnalise,
    PlanoIndividualTrabalho,
    PlanoIndividualTrabalhoAtendimento,
    PlanoIndividualTrabalhoEntregas,
)
from pgd2.tests.models.test_workflow_pgd2 import (
    aprovar_pes,
    completar_pes_para_aprovacao,
    criar_periodos,
    criar_pes_em_cadastro,
    deferir_adesao_pes,
    deferir_adesao_pgd,
    workflow_pgd2,
)
from rh.models import Servidor, Setor


@dataclass
class CadeiaRit:
    """Cadeia mínima ``adesão → PIT homologado → entrega_pit homologada`` pronta para receber RITs."""

    servidor: Servidor
    pit: PlanoIndividualTrabalho
    entrega_pit: PlanoIndividualTrabalhoEntregas


@pytest.fixture
def cadeia_rit_pgd2(workflow_pgd2) -> CadeiaRit:
    """Monta um PIT homologado em ``EM_CADASTRO_RIT`` com uma entrega homologada.

    Reaproveita os helpers do fluxo real (``test_workflow_pgd2``) para garantir
    que todos os campos obrigatórios, configurações e períodos estejam
    consistentes com o domínio do PGD2.
    """
    periodo_pes, periodo_pit_rit = criar_periodos(workflow_pgd2)
    pes = aprovar_pes(criar_pes_em_cadastro(workflow_pgd2, periodo_pes), workflow_pgd2)
    entrega_pes = completar_pes_para_aprovacao(pes, workflow_pgd2)
    adesao_pgd = deferir_adesao_pgd(workflow_pgd2)
    deferir_adesao_pes(workflow_pgd2, adesao_pgd)

    pit = PlanoIndividualTrabalho.objects.create(
        adesao=adesao_pgd,
        periodo_pit_rit=periodo_pit_rit,
        data_inicio=workflow_pgd2.inicio,
        data_fim=workflow_pgd2.fim,
        regime_execucacao=PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
        percentual_teletrabalho=100,
        situacao=PlanoIndividualTrabalho.EM_CADASTRO,
    )
    PitSetores.objects.create(pit=pit, pes=pes, setor=workflow_pgd2.setor, pode_homologar=True)
    PlanoIndividualTrabalhoAtendimento.objects.create(
        pit=pit,
        data=workflow_pgd2.inicio,
        hora_inicio=datetime.time(10),
        hora_final=datetime.time(11),
    )
    entrega_pit = PlanoIndividualTrabalhoEntregas.objects.create(
        pit=pit,
        entrega_pes=entrega_pes,
        titulo='Executar entrega institucional',
        descricao='Trabalho planejado para a entrega institucional.',
        tempo_planejado=Decimal('8'),
        data_prazo=workflow_pgd2.fim,
    )

    pit.gerar_solicitacao_aprovacao_homologacao_pit_rit(PitSolicitacaoAnalise.PIT)
    pit.homologar_pit(Setor.objects.filter(pk=workflow_pgd2.setor.pk), workflow_pgd2.chefe)
    pit.refresh_from_db()
    entrega_pit.refresh_from_db()

    assert pit.situacao_rit == PlanoIndividualTrabalho.EM_CADASTRO_RIT
    assert entrega_pit.homologado

    return CadeiaRit(servidor=workflow_pgd2.servidor, pit=pit, entrega_pit=entrega_pit)
