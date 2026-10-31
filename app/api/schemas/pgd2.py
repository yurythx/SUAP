"""Schemas ninja para o lançamento de execuções (RIT) do PGD via GitLab."""

import datetime
from decimal import Decimal

from ninja import Schema
from pydantic import model_validator


class EntregaDisponivelSchema(Schema):
    """Entrega do PIT em que o servidor pode lançar RIT, com o contexto da Entrega PES e do período."""

    id: int
    titulo: str
    descricao: str
    pit_id: int
    # Conteúdo da Entrega PES — é contra isto que a skill casa a issue (significado da categoria).
    pes_titulo: str | None = None
    pes_descricao: str | None = None
    pes_criterios_avaliacao: str | None = None
    metrica: int | None = None  # 1=PERCENTUAL, 2=QUANTIDADE — guia o quantidade_progresso do RIT
    meta: Decimal | None = None
    # Período do PIT — a skill casa o label de mês/ano da issue (ex.: '2026-06') com data_inicio/data_fim.
    periodo_titulo: str
    pit_data_inicio: datetime.date | None = None
    pit_data_fim: datetime.date | None = None
    eh_periodo_corrente: bool = False


class EntregasDisponiveisOutput(Schema):
    """Lista de entregas disponíveis para lançamento de RIT."""

    entregas: list[EntregaDisponivelSchema]


class LancarRitInput(Schema):
    """Dados de entrada para criar/atualizar um RIT a partir de um MR do GitLab, ou sem MR (deploy, investigação).

    Com MR, o RIT é único por ``(gitlab_project_id, gitlab_mr_iid)``; sem MR, cada lançamento cria um RIT novo.
    """

    gitlab_username: str
    gitlab_project_id: int | None = None
    gitlab_mr_iid: int | None = None
    entrega_pit_id: int
    titulo: str
    descricao: str
    tempo_executado: Decimal
    perc_executada_em_teletrabalho: Decimal = Decimal('0')
    data_inicio: datetime.date | None = None
    data_fim: datetime.date | None = None
    quantidade_progresso: Decimal = Decimal('1')  # 1 por MR (um MR = um trabalho); soma vira o total da categoria

    @model_validator(mode='after')
    def _mr_exige_projeto(self) -> LancarRitInput:
        # o UNIQUE de (projeto, MR) não barra projeto nulo: MR sem projeto duplicaria o RIT
        if self.gitlab_mr_iid is not None and self.gitlab_project_id is None:
            raise ValueError('gitlab_mr_iid exige gitlab_project_id.')
        return self


class RitLancadoOutput(Schema):
    """Resultado do lançamento do RIT; ``gitlab_mr_iid`` é nulo no RIT sem MR."""

    rit_id: int
    entrega_pit_id: int
    gitlab_mr_iid: int | None = None
    criado: bool


class RitDoMrOutput(Schema):
    """Status do RIT lançado para um MR — alimenta o comentário de confirmação no merge."""

    rit_id: int
    situacao_rit: int
    entrega_titulo: str
    tempo_executado: Decimal


class HorasPitSchema(Schema):
    """Horas de um PIT aberto a RIT: a CH prevista do período, o que já foi lançado e o que falta."""

    pit_id: int
    periodo_titulo: str
    pit_data_inicio: datetime.date | None = None
    pit_data_fim: datetime.date | None = None
    eh_periodo_corrente: bool = False
    # CH prevista do servidor no período, vinda do ponto (já desconta afastamentos e férias).
    tempo_previsto: Decimal
    # Soma do tempo executado dos RITs do PIT; o PGD recalcula a cada RIT lançado.
    tempo_executado_total: Decimal
    # Quanto falta lançar para chegar ao previsto; nunca negativo.
    tempo_restante: Decimal
    # % de teletrabalho pactuado no PIT; padrão do perc_executada_em_teletrabalho de cada RIT.
    percentual_teletrabalho: Decimal


class HorasPitOutput(Schema):
    """Horas dos PITs do servidor que ainda aceitam RIT."""

    pits: list[HorasPitSchema]
