"""Marcação automática de ações do checklist do PDA a partir do estado real.

Cada condição de ``CondicaoAcaoAutomatica`` tem um predicado ``f(pda) -> bool``. Ao sincronizar,
as ``PDAAcao`` cujas ``Acao`` têm ``condicao_automatica`` preenchida são marcadas como concluídas
(ou revertidas) conforme o predicado — as ações sem condição continuam manuais.

As três condições da etapa "Abertura e Publicação" (recurso, liberação do LAI e sincronização)
se satisfazem com **uma** base, não com todas: a abertura é incremental, e exigir o conjunto
inteiro travava o checklist do PDA por causa de uma única base atrasada.
"""

from django.utils import timezone

from dados_abertos.enums import CondicaoAcaoAutomatica, Situacao_GrupoTrabalho, SituacaoLAI


def _bases_vinculadas(pda) -> bool:
    return pda.bases_relacionadas.exists()


def _bases_com_recurso(pda) -> bool:
    """Ao menos uma base do PDA já tem recurso cadastrado."""
    return pda.bases_relacionadas.filter(base_dados__recursos__isnull=False).exists()


def _matriz_finalizada(pda) -> bool:
    from dados_abertos.models import AvaliacaoBaseDados

    base_ids = list(pda.bases_relacionadas.values_list('base_dados_id', flat=True))
    if not base_ids or pda.tem_base_sem_avaliacao():
        return False
    return not AvaliacaoBaseDados.objects.filter(base_dados_id__in=base_ids, finalizado=False).exists()


def _consulta_publica_realizada(pda) -> bool:
    return pda.consultas_publicas.exists()


def _bases_liberadas_lai(pda) -> bool:
    """Ao menos uma base do PDA já foi liberada pelo Responsável LAI."""
    return pda.bases_relacionadas.filter(situacao_lai=SituacaoLAI.LIBERADO).exists()


def _bases_sincronizadas_ckan(pda) -> bool:
    """Ao menos uma base do PDA foi efetivamente enviada ao CKAN.

    Exige ``sincronizado_em`` além do ``id_remoto``: o ID remoto sozinho não prova envio — pode ter
    sobrado de uma tentativa anterior ou ter sido preenchido à mão no admin.
    """
    return pda.bases_relacionadas.exclude(base_dados__id_remoto='').filter(base_dados__sincronizado_em__isnull=False).exists()


def _grupo_trabalho_definido(pda) -> bool:
    return pda.grupos_trabalho.filter(
        situacao=Situacao_GrupoTrabalho.ATIVO,
        responsavelgrupotrabalho__ativo=True,
    ).exists()


PREDICADOS = {
    CondicaoAcaoAutomatica.BASES_VINCULADAS: _bases_vinculadas,
    CondicaoAcaoAutomatica.BASES_COM_RECURSO: _bases_com_recurso,
    CondicaoAcaoAutomatica.MATRIZ_FINALIZADA: _matriz_finalizada,
    CondicaoAcaoAutomatica.CONSULTA_PUBLICA_REALIZADA: _consulta_publica_realizada,
    CondicaoAcaoAutomatica.BASES_LIBERADAS_LAI: _bases_liberadas_lai,
    CondicaoAcaoAutomatica.BASES_SINCRONIZADAS_CKAN: _bases_sincronizadas_ckan,
    CondicaoAcaoAutomatica.GRUPO_TRABALHO_DEFINIDO: _grupo_trabalho_definido,
}


def sincronizar_acoes_automaticas(pda) -> int:
    """Avalia as condições automáticas das ações do PDA e marca concluída/pendente conforme o estado real.

    Reavalia todas as ``PDAAcao`` com ``condicao_automatica``; recalcula a etapa atual uma única vez
    ao final (se algo mudou). Retorna quantas ações mudaram de estado.
    """
    mudou = 0
    puladas = pda.etapas_puladas_ids()
    pda_acoes = pda.acoes.select_related('acao').exclude(acao__condicao_automatica='')
    for pda_acao in pda_acoes:
        if pda_acao.acao.etapa_id in puladas:
            # etapa dispensada: não marca nem reverte suas ações automáticas
            continue
        predicado = PREDICADOS.get(pda_acao.acao.condicao_automatica)
        if predicado is None:
            continue
        deveria = bool(predicado(pda))
        if deveria != pda_acao.concluida:
            pda_acao.concluida = deveria
            pda_acao.data_conclusao = timezone.now() if deveria else None
            pda_acao.save(update_fields=['concluida', 'data_conclusao', 'data_atualizacao'])
            mudou += 1
    if mudou:
        pda.atualizar_etapa_atual()
    return mudou
