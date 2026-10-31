"""Contexto das páginas de visualização da base de dados e do recurso (``get_absolute_url``).

Cada seção relacionada só é montada para quem pode ver o model dela: o membro do grupo de trabalho
consulta a base, mas não lê os pareceres do Responsável LAI. Seção ``None`` não é exibida; lista
vazia é exibida com a mensagem de vazio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dados_abertos.enums import ODS, SituacaoLAI
from dados_abertos.models import DeliberacaoLAI
from dados_abertos.services.ckan_api_service import get_ckan_service
from dados_abertos.services.lai_service import preview_recurso
from dados_abertos.services.metadados import extras_dcat

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    from dados_abertos.models import AtualizacaoBaseDados, AvaliacaoBaseDados, BaseDados, PDABaseDados, RecursoDados

#: Registros de histórico exibidos na página: o histórico completo continua no admin.
ULTIMAS_ATUALIZACOES = 20
ULTIMOS_EVENTOS_LAI = 20


def _pode_ver(user: AbstractUser, model: str) -> bool:
    return user.has_perm(f'dados_abertos.view_{model}')


def _url_portal(caminho: str) -> str:
    """Endereço público no CKAN, ou vazio quando a integração está inativa."""
    servico = get_ckan_service()
    return f'{servico.base_url}/{caminho}' if servico else ''


@dataclass
class ResumoLAI:
    """Situação da base no LAI para o cabeçalho (não confundir com o enum ``SituacaoLAI``)."""

    classe: str
    rotulo: str
    motivo: str


@dataclass
class VisualizacaoBase:
    pode_editar: bool
    url_portal: str
    situacao_lai: ResumoLAI
    ods: list[str]
    extras: dict[str, str]
    recursos: list[RecursoDados] | None
    relacoes: list[PDABaseDados] | None
    avaliacoes: list[AvaliacaoBaseDados] | None
    eventos_lai: list[DeliberacaoLAI] | None
    atualizacoes: list[AtualizacaoBaseDados] | None


def _situacao_lai(base: BaseDados) -> ResumoLAI:
    """A situação mais grave entre os PDAs da base: a devolução pede ação do gestor, não do LAI.

    Base fora de PDA nunca vai ser analisada, e por isso tem rótulo próprio.
    """
    situacoes = set(base.relacoes_pda.values_list('situacao_lai', flat=True))
    if not situacoes:
        return ResumoLAI('status-default', 'Fora de PDA', base.motivo_bloqueio_lai())
    if situacoes == {SituacaoLAI.LIBERADO}:
        return ResumoLAI('status-success', 'Liberada pelo LAI', '')
    mais_grave = next(s for s in (SituacaoLAI.DEVOLVIDO, SituacaoLAI.EM_ANALISE, SituacaoLAI.PENDENTE) if s in situacoes)
    return ResumoLAI(SituacaoLAI.CLASSES[mais_grave], SituacaoLAI.LABELS[mais_grave], base.motivo_bloqueio_lai())


def _relacoes(base: BaseDados) -> list[PDABaseDados]:
    return list(
        base.relacoes_pda.select_related('pda', 'unidade_responsavel_abertura', 'responsavel_abertura__pessoa_fisica').order_by(
            '-pda__vigencia_inicio'
        )
    )


def _atualizacoes(base: BaseDados) -> list[AtualizacaoBaseDados]:
    return list(base.atualizacoes.order_by('-data')[:ULTIMAS_ATUALIZACOES])


def _eventos_lai(base: BaseDados) -> list[DeliberacaoLAI]:
    # O template mostra `autor.pessoa.nome`, que vem no select_related: `str(Vinculo)` passaria pela
    # relação genérica, uma consulta por evento. O teto segura o histórico, que cresce a cada
    # reabertura por edição.
    eventos = DeliberacaoLAI.objects.filter(pda_base_dados__base_dados=base).select_related('autor__pessoa', 'pda_base_dados__pda')
    return list(eventos.order_by('-data')[:ULTIMOS_EVENTOS_LAI])


def visualizacao_base(base: BaseDados, user: AbstractUser) -> VisualizacaoBase:
    pode = {m: _pode_ver(user, m) for m in ('recursodados', 'pdabasedados', 'avaliacaobasedados', 'deliberacaolai', 'atualizacaobasedados')}
    return VisualizacaoBase(
        pode_editar=user.has_perm('dados_abertos.change_basedados'),
        url_portal=_url_portal(f'dataset/{base.nome}') if base.id_remoto else '',
        situacao_lai=_situacao_lai(base),
        ods=[ODS.rotulo(n) for n in sorted(base.ods or [])],
        extras=extras_dcat(base),
        recursos=list(base.recursos.select_related('derivado_de').order_by('nome')) if pode['recursodados'] else None,
        relacoes=_relacoes(base) if pode['pdabasedados'] else None,
        avaliacoes=list(base.avaliacoes_base_dados.select_related('criterio_matriz').order_by('criterio_matriz__nome'))
        if pode['avaliacaobasedados']
        else None,
        eventos_lai=_eventos_lai(base) if pode['deliberacaolai'] else None,
        atualizacoes=_atualizacoes(base) if pode['atualizacaobasedados'] else None,
    )


@dataclass
class VisualizacaoRecurso:
    pode_editar: bool
    url_portal: str
    previa: dict[str, list | str | None]
    espelhos: list[RecursoDados]


def visualizacao_recurso(recurso: RecursoDados, user: AbstractUser) -> VisualizacaoRecurso:
    tem_portal = bool(recurso.id_remoto and recurso.dataset.id_remoto)
    return VisualizacaoRecurso(
        pode_editar=user.has_perm('dados_abertos.change_recursodados'),
        url_portal=_url_portal(f'dataset/{recurso.dataset.nome}/resource/{recurso.id_remoto}') if tem_portal else '',
        previa=preview_recurso(recurso),
        espelhos=list(recurso.derivados.all()),
    )
