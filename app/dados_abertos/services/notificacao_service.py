"""Notificação das pendências de dados abertos, roteada por responsabilidade.

Resumo periódico, não notificação por evento: o agendamento monta o que está pendente e avisa
cada papel do que é dele. A cadência mora no agendamento (Celery Beat, em ``dados_abertos/beat.py``),
não no código — por isso o módulo não guarda estado de "última notificação enviada".

Quem recebe o quê:

* **pessoal** — uma notificação por pessoa, só com o que está sob responsabilidade dela;
* **coletiva** — o agregado do plano, indo inteiro ao Gestor de Dados Abertos Sistêmico e, sem as
  pendências técnicas (:data:`~dados_abertos.services.pendencias_service.SOMENTE_GESTOR`), ao grupo
  de trabalho. URL de origem fora do ar não é assunto do grupo de trabalho.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass

from django.conf import settings

from comum.models import Vinculo
from dados_abertos.enums import Situacao_GrupoTrabalho, SituacaoPDA
from dados_abertos.models import PDABaseDados, ResponsavelGrupoTrabalho
from dados_abertos.services import pendencias_service
from djtools.utils import send_notification

logger = logging.getLogger(__name__)

GRUPO_GESTOR = 'Gestor de Dados Abertos Sistêmico'
GRUPO_MEMBROS_GT = 'Membros do Grupo de Trabalho'
GRUPO_LAI = 'Responsável LAI'

ASSUNTO_PESSOAL = 'Dados Abertos: pendências sob sua responsabilidade'
ASSUNTO_COLETIVO = 'Dados Abertos: pendências do Plano de Dados Abertos'


@dataclass(frozen=True)
class ResumoNotificacao:
    """Contagens de uma execução da notificação."""

    pessoais: int = 0
    coletivas: int = 0
    sem_vinculo: int = 0


def _vinculos_do_grupo(nome: str):
    return Vinculo.objects.filter(user__groups__name=nome, ativo=True).select_related('user').distinct()


def _vinculos_do_grupo_de_trabalho(hoje: datetime.date):
    """União, sem duplicar, dos GTs designados nos PDAs vigentes com o grupo de permissão."""
    designados = ResponsavelGrupoTrabalho.objects.filter(
        ativo=True,
        grupo_trabalho__situacao=Situacao_GrupoTrabalho.ATIVO,
        grupo_trabalho__pda__vigencia_fim__gte=hoje,
    ).exclude(grupo_trabalho__pda__situacao=SituacaoPDA.ENCERRADO)
    ids = set(designados.values_list('responsavel_id', flat=True))
    ids.update(_vinculos_do_grupo(GRUPO_MEMBROS_GT).values_list('id', flat=True))
    ids.discard(None)
    return Vinculo.objects.filter(id__in=ids).select_related('user')


def _responsaveis_pela_abertura(hoje: datetime.date) -> tuple[list, int]:
    """Vínculos dos responsáveis pela abertura nos PDAs vigentes, e quantos não têm vínculo.

    O ``prefetch_related`` da GenericRelation é o que evita um N+1: ``Servidor.get_vinculo()``
    lê ``self.vinculos.all()`` e reaproveita o cache do prefetch quando ele existe.
    """
    servidores = {
        relacao.responsavel_abertura
        for relacao in PDABaseDados.objects.filter(pda__vigencia_fim__gte=hoje, responsavel_abertura__isnull=False)
        .exclude(pda__situacao=SituacaoPDA.ENCERRADO)
        .select_related('responsavel_abertura')
        .prefetch_related('responsavel_abertura__vinculos')
    }
    vinculos = []
    sem_vinculo = 0
    for servidor in servidores:
        vinculo = servidor.get_vinculo()
        if vinculo:
            vinculos.append(vinculo)
        else:
            sem_vinculo += 1
            logger.info('Notificação de dados abertos: servidor %s sem vínculo ativo, ignorado.', servidor.pk)
    return vinculos, sem_vinculo


def _destinatarios_pessoais(hoje: datetime.date) -> tuple[list, int]:
    """Quem pode ter pendência pessoal: responsáveis pela abertura e o Responsável LAI."""
    vinculos, sem_vinculo = _responsaveis_pela_abertura(hoje)
    por_id = {vinculo.pk: vinculo for vinculo in vinculos}
    for vinculo in _vinculos_do_grupo(GRUPO_LAI):
        por_id.setdefault(vinculo.pk, vinculo)
    return list(por_id.values()), sem_vinculo


def montar_mensagem(pendencias: list[pendencias_service.Pendencia]) -> str:
    """Texto da notificação: uma linha por pendência, com link absoluto."""
    linhas = [f'<li><a href="{settings.SITE_URL}{p.url}">{p.qtd} {p.titulo.lower()} {p.subtitulo}</a></li>' for p in pendencias]
    return '<ul>' + ''.join(linhas) + '</ul>'


def _enviar(assunto: str, pendencias: list, vinculos: list, dry_run: bool) -> bool:
    """Envia uma notificação, ou apenas relata quando ``dry_run``. ``False`` se não havia o que enviar."""
    if not pendencias or not vinculos:
        return False
    if dry_run:
        logger.info('[dry-run] %s → %s destinatário(s): %s', assunto, len(vinculos), [p.chave for p in pendencias])
        return True
    send_notification(assunto, montar_mensagem(pendencias), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=assunto)
    return True


def notificar(hoje: datetime.date | None = None, dry_run: bool = False) -> ResumoNotificacao:
    """Envia o resumo de pendências a cada papel responsável.

    Args:
        hoje: Data de referência; o padrão é a data corrente.
        dry_run: Quando ``True``, apenas registra no log o que seria enviado.

    Returns:
        ResumoNotificacao: Quantas notificações pessoais e coletivas saíram, e quantos responsáveis
        foram ignorados por não terem vínculo ativo.
    """
    hoje = hoje or datetime.date.today()

    destinatarios, sem_vinculo = _destinatarios_pessoais(hoje)
    pessoais = 0
    for vinculo in destinatarios:
        if _enviar(ASSUNTO_PESSOAL, pendencias_service.pessoais(vinculo, hoje=hoje), [vinculo], dry_run):
            pessoais += 1

    coletivas = 0
    pendencias_coletivas = pendencias_service.coletivas(hoje=hoje)
    gestores = list(_vinculos_do_grupo(GRUPO_GESTOR))
    if _enviar(ASSUNTO_COLETIVO, pendencias_coletivas, gestores, dry_run):
        coletivas += 1

    # Quem já recebeu como gestor não recebe de novo pelo grupo de trabalho — a versão do gestor é
    # a mais completa, e duplicar a mesma cobrança em duas mensagens só gera ruído.
    ids_gestores = {vinculo.pk for vinculo in gestores}
    grupo_trabalho = [vinculo for vinculo in _vinculos_do_grupo_de_trabalho(hoje) if vinculo.pk not in ids_gestores]
    if _enviar(ASSUNTO_COLETIVO, pendencias_service.do_grupo_de_trabalho(pendencias_coletivas), grupo_trabalho, dry_run):
        coletivas += 1

    return ResumoNotificacao(pessoais=pessoais, coletivas=coletivas, sem_vinculo=sem_vinculo)
