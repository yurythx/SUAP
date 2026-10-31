"""Pendências de dados abertos, chaveadas por responsabilidade.

Fonte única de "quem deve o quê": alimenta tanto os indicadores de *Minhas pendências* e
*Pendências coletivas* no index do SUAP quanto o resumo notificado pelo agendamento. Tratar as
duas saídas com a mesma função evita que a tela e a cobrança por notificação discordem.

As consultas consideram apenas PDAs **em vigência** — prazo vencido em plano encerrado não é
acionável, e cobrá-lo seria ruído permanente.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db.models import Count, Q

from dados_abertos.enums import Periodicidade, ResultadoAtualizacao, SituacaoLAI, SituacaoPDA
from dados_abertos.models import AtualizacaoBaseDados, PDABaseDados
from dados_abertos.services.periodicidade import intervalo_mais_estrito, proxima_atualizacao

DASHBOARD_PLANO_ACAO = '/dados_abertos/dashboard/?tab=tab1'
DASHBOARD_CKAN = '/dados_abertos/dashboard/?tab=tab2'
DELIBERACAO_LAI = '/dados_abertos/deliberacao_lai/'
ADMIN_DEVOLVIDAS = f'/admin/dados_abertos/pdabasedados/?situacao_lai__exact={SituacaoLAI.DEVOLVIDO}'

# Pendências coletivas que são assunto exclusivo do gestor — falha técnica não é do grupo de trabalho.
SOMENTE_GESTOR = frozenset({'falha_rotina'})


@dataclass(frozen=True)
class Pendencia:
    """Uma cobrança endereçável, na forma que o índice do SUAP e a notificação consomem."""

    chave: str
    titulo: str
    subtitulo: str
    qtd: int
    url: str
    prazo: datetime.date | None = None


def como_indicadores(pendencias: list[Pendencia]) -> list[dict]:
    """Adapta as pendências ao contrato de ``djtools/templates/components/atribuidos.html``."""
    indicadores = []
    for pendencia in pendencias:
        indicador = {'titulo': pendencia.titulo, 'subtitulo': pendencia.subtitulo, 'qtd': pendencia.qtd, 'url': pendencia.url}
        if pendencia.prazo:
            indicador['prazo'] = pendencia.prazo.strftime('%d/%m/%Y')
        indicadores.append(indicador)
    return indicadores


def _relacoes_vigentes(hoje: datetime.date):
    """``PDABaseDados`` de PDAs ainda em vigência e não encerrados."""
    return PDABaseDados.objects.filter(pda__vigencia_fim__gte=hoje).exclude(pda__situacao=SituacaoPDA.ENCERRADO)


def _pluralizar(qtd: int, singular: str, plural: str) -> str:
    return singular if qtd == 1 else plural


def _pendencia_lai(hoje: datetime.date) -> Pendencia | None:
    qtd = _relacoes_vigentes(hoje).filter(situacao_lai=SituacaoLAI.EM_ANALISE, base_dados__recursos__isnull=False).distinct().count()
    if not qtd:
        return None
    return Pendencia(
        chave='lai_a_deliberar',
        titulo=f'Conjunto{_pluralizar(qtd, "", "s")} de dados',
        subtitulo='aguardando sua deliberação como Responsável LAI',
        qtd=qtd,
        url=DELIBERACAO_LAI,
    )


def _minhas_relacoes(vinculo, hoje: datetime.date):
    """Relações vigentes em que este vínculo é o responsável pela abertura da base."""
    return _relacoes_vigentes(hoje).filter(responsavel_abertura__vinculos=vinculo)


def _pendencia_devolvidas(vinculo, hoje: datetime.date) -> Pendencia | None:
    qtd = _minhas_relacoes(vinculo, hoje).filter(situacao_lai=SituacaoLAI.DEVOLVIDO).count()
    if not qtd:
        return None
    return Pendencia(
        chave='devolvidas_lai',
        titulo=f'Base{_pluralizar(qtd, "", "s")} de dados',
        subtitulo=f'devolvida{_pluralizar(qtd, "", "s")} pelo LAI para ajuste',
        qtd=qtd,
        url=ADMIN_DEVOLVIDAS,
    )


def _pendencia_prazo_vencido(vinculo, hoje: datetime.date) -> Pendencia | None:
    vencidas = (
        _minhas_relacoes(vinculo, hoje)
        .filter(meta_prazo_abertura__lt=hoje, base_dados__id_remoto='')
        .order_by('meta_prazo_abertura')
        .values_list('meta_prazo_abertura', flat=True)
    )
    prazos = list(vencidas)
    if not prazos:
        return None
    return Pendencia(
        chave='prazo_vencido',
        titulo=f'Base{_pluralizar(len(prazos), "", "s")} de dados',
        subtitulo='com prazo de abertura vencido',
        qtd=len(prazos),
        url=DASHBOARD_PLANO_ACAO,
        prazo=prazos[0],
    )


def _pendencia_atualizacao_manual(vinculo, hoje: datetime.date) -> Pendencia | None:
    """Bases minhas com periodicidade vencida e sem nenhum recurso de URL.

    O vencimento não é filtrável em SQL (a régua mistura a frequência mais estrita com a última
    sincronização), então o banco estreita — minhas relações, com frequência, sem fonte automática —
    e o vencimento é avaliado em Python sobre o punhado de linhas que sobra.
    """
    candidatas = (
        _minhas_relacoes(vinculo, hoje)
        .filter(frequencia_atualizacao__isnull=False)
        .exclude(frequencia_atualizacao=Periodicidade.EVENTUAL)
        .annotate(com_url=Count('base_dados__recursos', filter=~Q(base_dados__recursos__url=''), distinct=True))
        .filter(com_url=0)
        .select_related('base_dados')
        .prefetch_related('base_dados__recursos')
    )
    atrasadas = 0
    for relacao in candidatas:
        intervalo = intervalo_mais_estrito([relacao.frequencia_atualizacao])
        sincronizacoes = [relacao.base_dados.sincronizado_em, *(r.sincronizado_em for r in relacao.base_dados.recursos.all())]
        proxima = proxima_atualizacao(max([dt for dt in sincronizacoes if dt], default=None), intervalo)
        if proxima and proxima <= hoje:
            atrasadas += 1
    if not atrasadas:
        return None
    return Pendencia(
        chave='atualizacao_manual',
        titulo=f'Base{_pluralizar(atrasadas, "", "s")} de dados',
        subtitulo='com atualização manual atrasada',
        qtd=atrasadas,
        url=DASHBOARD_CKAN,
    )


def pessoais(vinculo, hoje: datetime.date | None = None) -> list[Pendencia]:
    """Pendências sob responsabilidade direta desta pessoa.

    Args:
        vinculo: ``comum.Vinculo`` de quem está sendo consultado.
        hoje: Data de referência; o padrão é a data corrente.

    Returns:
        list[Pendencia]: Vazia quando a pessoa nada deve ao módulo.
    """
    hoje = hoje or datetime.date.today()
    if not vinculo:
        return []
    candidatas = []
    if vinculo.user and vinculo.user.has_perm('dados_abertos.deliberar_lai'):
        candidatas.append(_pendencia_lai(hoje))
    # Estes receivers rodam a cada carga do index, para todo usuário do SUAP. Um `exists()` decide
    # em uma consulta se vale investigar as três pendências de quem responde por bases.
    if _minhas_relacoes(vinculo, hoje).exists():
        candidatas.append(_pendencia_devolvidas(vinculo, hoje))
        candidatas.append(_pendencia_prazo_vencido(vinculo, hoje))
        candidatas.append(_pendencia_atualizacao_manual(vinculo, hoje))
    return [pendencia for pendencia in candidatas if pendencia]


def _pendencia_falha_rotina(hoje: datetime.date) -> Pendencia | None:
    """Bases cuja última execução da rotina automática terminou em falha."""
    ultimas = AtualizacaoBaseDados.objects.order_by('base_dados_id', '-data').distinct('base_dados_id')
    falhas = [
        registro.base_dados_id for registro in ultimas if registro.resultado in (ResultadoAtualizacao.FALHA_DOWNLOAD, ResultadoAtualizacao.FALHA_CKAN)
    ]
    qtd = _relacoes_vigentes(hoje).filter(base_dados_id__in=falhas).values('base_dados_id').distinct().count()
    if not qtd:
        return None
    return Pendencia(
        chave='falha_rotina',
        titulo=f'Base{_pluralizar(qtd, "", "s")} de dados',
        subtitulo='com falha na última atualização automática',
        qtd=qtd,
        url=DASHBOARD_CKAN,
    )


def _pendencia_sem_recurso(hoje: datetime.date) -> Pendencia | None:
    qtd = _relacoes_vigentes(hoje).filter(base_dados__recursos__isnull=True).values('base_dados_id').distinct().count()
    if not qtd:
        return None
    return Pendencia(
        chave='sem_recurso',
        titulo=f'Base{_pluralizar(qtd, "", "s")} de dados',
        subtitulo='sem recurso cadastrado',
        qtd=qtd,
        url=DASHBOARD_PLANO_ACAO,
    )


def _pendencia_cronograma_incompleto(hoje: datetime.date) -> Pendencia | None:
    qtd = _relacoes_vigentes(hoje).filter(Q(responsavel_abertura__isnull=True) | Q(meta_prazo_abertura__isnull=True)).count()
    if not qtd:
        return None
    return Pendencia(
        chave='cronograma_incompleto',
        titulo=f'Base{_pluralizar(qtd, "", "s")} de dados',
        subtitulo='sem responsável ou sem prazo de abertura',
        qtd=qtd,
        url=DASHBOARD_PLANO_ACAO,
    )


def coletivas(hoje: datetime.date | None = None) -> list[Pendencia]:
    """Pendências do plano, iguais para todos que respondem por ele.

    Args:
        hoje: Data de referência; o padrão é a data corrente.

    Returns:
        list[Pendencia]: Vazia quando o plano não tem pendência coletiva.
    """
    hoje = hoje or datetime.date.today()
    candidatas = [_pendencia_falha_rotina(hoje), _pendencia_sem_recurso(hoje), _pendencia_cronograma_incompleto(hoje)]
    return [pendencia for pendencia in candidatas if pendencia]


def do_grupo_de_trabalho(pendencias: list[Pendencia]) -> list[Pendencia]:
    """Recorta as coletivas que são assunto do grupo de trabalho (tira a falha técnica)."""
    return [pendencia for pendencia in pendencias if pendencia.chave not in SOMENTE_GESTOR]
