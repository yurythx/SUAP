from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from lxml_html_clean import Cleaner
from ninja import Schema
from pydantic import field_validator

if TYPE_CHECKING:
    from demandas.models import AmbienteHomologacao


class ErrorSchema(Schema):
    error: str
    hint: str
    context: dict


class EspecificacaoSchema(Schema):
    id: int
    nome: str
    atividades: str
    ordem: int
    gitlab_issue_url: str | None


class DodSchema(Schema):
    descricao: str | None
    especificacoes: list[EspecificacaoSchema]

    @staticmethod
    def resolve_especificacoes(obj):
        return list(obj.especificacao_set.order_by('ordem'))


class DecisaoEspecificacaoSchema(Schema):
    id: int
    autor: str
    criado_em: datetime
    decisao: str
    contexto: dict
    origem: str

    @staticmethod
    def resolve_autor(obj):
        return obj.autor.get_full_name() or obj.autor.username


class SubdemandaSchema(Schema):
    id: int
    titulo: str
    situacao: str
    percentual_conclusao: int

    @staticmethod
    def resolve_percentual_conclusao(obj):
        total = getattr(obj, '_total_sub', None)
        if total is None:
            return obj.percentual_conclusao
        if not total:
            return 0
        return round((getattr(obj, '_encerradas_sub', 0) / total) * 100)


class AgentContextSchema(Schema):
    id: int
    titulo: str
    situacao: str
    especificacao_tecnica: str
    branch: str | None
    id_merge_request: int | None
    subdemandas: list[SubdemandaSchema]
    dod: DodSchema | None
    decisoes_especificacao: list[DecisaoEspecificacaoSchema]

    @staticmethod
    def resolve_subdemandas(obj):
        from django.db.models import Count, Q

        from demandas.models import Situacao

        return list(
            obj.get_subdemandas().annotate(
                _total_sub=Count('subdemandas'),
                _encerradas_sub=Count(
                    'subdemandas',
                    filter=Q(subdemandas__situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO]),
                ),
            )
        )

    @staticmethod
    def resolve_dod(obj):
        return obj.dod_set.first()

    @staticmethod
    def resolve_decisoes_especificacao(obj):
        return list(obj.decisoes_especificacao.all())


class MRStatusSchema(Schema):
    demanda_id: int
    branch: str | None
    id_merge_request: int | None
    situacao: str
    mr_url: str | None

    @staticmethod
    def resolve_demanda_id(obj):
        return obj.pk

    @staticmethod
    def resolve_mr_url(obj):
        from comum.models import Configuracao

        if not obj.id_merge_request:
            return None
        gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
        gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')
        if not gitlab_url or not gitlab_suap_id:
            return None
        return f'{gitlab_url.rstrip("/")}/{gitlab_suap_id}/-/merge_requests/{obj.id_merge_request}'


class PipelineStatusSchema(Schema):
    entrega_id: int
    pipeline_id: int | None
    branch: str | None
    id_merge_request: int | None
    status: str

    @staticmethod
    def resolve_entrega_id(obj):
        return obj.pk


class OpenMRResponseSchema(Schema):
    demanda_id: int
    branch: str | None
    id_merge_request: int | None
    situacao: str
    mr_url: str | None
    already_exists: bool

    @staticmethod
    def resolve_demanda_id(obj):
        return obj.pk

    @staticmethod
    def resolve_mr_url(obj):
        from comum.models import Configuracao

        if not obj.id_merge_request:
            return None
        gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
        gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')
        if not gitlab_url or not gitlab_suap_id:
            return None
        return f'{gitlab_url.rstrip("/")}/{gitlab_suap_id}/-/merge_requests/{obj.id_merge_request}'


class SpecDecisionInputSchema(Schema):
    decisao: str
    contexto: dict = {}
    origem: str = 'agente'

    @field_validator('decisao')
    @classmethod
    def decisao_nao_vazia(cls, v):
        if not v or not v.strip():
            raise ValueError('decisao não pode ser vazio')
        return v

    @field_validator('origem')
    @classmethod
    def origem_valida(cls, v):
        from demandas.models import DecisaoEspecificacao

        choices = [c[0] for c in DecisaoEspecificacao.ORIGEM_CHOICES]
        if v not in choices:
            raise ValueError(f'origem deve ser um de: {choices}')
        return v


class SpecDecisionResponseSchema(Schema):
    id: int
    demanda_id: int
    autor: str
    criado_em: datetime
    decisao: str
    contexto: dict
    origem: str

    @staticmethod
    def resolve_demanda_id(obj):
        return obj.demanda_id

    @staticmethod
    def resolve_autor(obj):
        return obj.autor.get_full_name() or obj.autor.username


class ByMrResponseSchema(Schema):
    id: int
    titulo: str
    branch: str | None
    id_merge_request: int | None
    situacao: str


class RevisaoEspecificacaoInputSchema(Schema):
    """Proposta de alteração numa especificação já aprovada.

    Sem ``especificacao_id`` propõe uma especificação nova (``nome`` e ``atividades``
    obrigatórios). Com ele, revisa a existente: o campo omitido mantém o valor atual. Com
    ``remocao_solicitada``, propõe remover a especificação e ignora ``nome``/``atividades``.
    """

    especificacao_id: int | None = None
    nome: str | None = None
    atividades: str | None = None
    remocao_solicitada: bool = False
    solicitar_validacao: bool = False

    @field_validator('atividades')
    @classmethod
    def atividades_sem_html_ativo(cls, v):
        # A tela exibe ``atividades`` com ``|safe`` aos demandantes: tira script, handlers e afins.
        if v is None or not v.strip():
            return v
        return Cleaner().clean_html(v)


class RevisaoEspecificacaoSchema(Schema):
    id: int
    demanda_id: int
    especificacao_id: int | None
    titulo: str
    nome: str
    atividades: str
    remocao_solicitada: bool
    validacao_solicitada: bool

    @staticmethod
    def resolve_demanda_id(obj):
        return obj.dod.demanda_id

    @staticmethod
    def resolve_titulo(obj):
        return obj.get_titulo()

    @staticmethod
    def resolve_validacao_solicitada(obj):
        return obj.dod.validacao_revisao_solicitada


class SituacaoDeploySchema(Schema):
    """Job ``deploy-suapdev`` no GitLab; ``etapa``/``progresso`` só existem depois que ele rodou."""

    status: str | None
    job_url: str | None
    progresso: int | None
    etapa: str | None


class AmbienteHomologacaoSchema(Schema):
    """Ambiente de homologação vinculado à demanda. A senha fica de fora: ela entra como qualquer usuário do ambiente."""

    id: int
    demanda_id: int
    branch: str
    banco: str
    criador: str
    data_criacao: date
    data_expiracao: date
    ativo: bool
    pipeline_id: int
    pipeline_url: str
    url: str | None
    deploy: SituacaoDeploySchema | None

    @staticmethod
    def resolve_criador(obj: AmbienteHomologacao) -> str:
        return obj.criador.usuario.username

    @staticmethod
    def resolve_pipeline_id(obj: AmbienteHomologacao) -> int:
        return obj.pipeline

    @staticmethod
    def resolve_pipeline_url(obj: AmbienteHomologacao) -> str:
        return obj.url_gitlab

    @staticmethod
    def resolve_url(obj: AmbienteHomologacao) -> str | None:
        return obj.get_url_homologacao() if obj.ativo else None

    @staticmethod
    def resolve_deploy(obj: AmbienteHomologacao) -> dict | None:
        return obj.get_situacao_deploy()
