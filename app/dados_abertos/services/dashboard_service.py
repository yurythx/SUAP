from datetime import date

from django.db.models import Count, F, OuterRef, Prefetch, Q, Subquery

from dados_abertos.enums import Periodicidade, ResultadoAtualizacao, SituacaoLAI, TipoEventoLAI
from dados_abertos.models import AtualizacaoBaseDados, DeliberacaoLAI, PDABaseDados, RecursoDados
from dados_abertos.services.ckan_api_service import is_ckan_configured
from dados_abertos.services.periodicidade import intervalo_em_dias, proxima_atualizacao


def _classificar_prazo(dias_restantes: int, intervalo_dias: int) -> tuple[str, str]:
    """Traduz os dias que faltam para o par (status, rótulo) exibido na aba CKAN."""
    if dias_restantes < 0:
        return 'atrasada', f'Atrasada em {abs(dias_restantes)} dia(s)'
    if intervalo_dias > 1 and dias_restantes <= max(1, round(intervalo_dias * 0.2)):
        return 'atencao', f'Próxima do vencimento ({dias_restantes} dia(s))'
    return 'em_dia', 'Periodicidade em dia'


def _avaliar_periodicidade_sync(rel, hoje):
    """Anota na relação o estado da periodicidade prometida.

    Usa a mesma régua da rotina de atualização automática (``services.periodicidade``), para que o
    farol da tela e o que o agendamento faz de fato não divirjam.
    """
    rel.proxima_sincronizacao = None
    frequencia = rel.frequencia_atualizacao
    ultima_sync = getattr(rel, 'ultima_sincronizacao_ckan', None)

    if frequencia == Periodicidade.EVENTUAL:
        rel.periodicidade_status = 'eventual'
        rel.periodicidade_label = 'Atualização eventual'
        return

    intervalo_dias = intervalo_em_dias(frequencia)
    if not intervalo_dias:
        rel.periodicidade_status = 'sem_frequencia'
        rel.periodicidade_label = 'Sem frequência definida'
        return

    if not ultima_sync:
        rel.periodicidade_status = 'sem_sync'
        rel.periodicidade_label = 'Sem histórico de sincronização'
        return

    proxima = proxima_atualizacao(ultima_sync, intervalo_dias)
    dias_restantes = (proxima - hoje).days
    rel.proxima_sincronizacao = proxima
    rel.dias_para_proxima_sync = dias_restantes
    rel.periodicidade_status, rel.periodicidade_label = _classificar_prazo(dias_restantes, intervalo_dias)


def falhas_consecutivas(bases_ids) -> dict:
    """Quantas execuções seguidas da rotina terminaram em falha técnica, por base.

    Conta as linhas posteriores ao último desfecho que **não** foi falha — por construção, todas
    elas são falhas, porque um não-falha posterior seria o corte. Bloqueio do LAI e ausência de
    fonte automática são estados do fluxo, não defeito: interrompem a sequência em vez de somar.

    Args:
        bases_ids: Ids das bases exibidas na tela.

    Returns:
        dict: ``{base_dados_id: quantidade}``, sem entrada para quem não está em falha.
    """
    if not bases_ids:
        return {}
    ultimo_nao_falha = (
        AtualizacaoBaseDados.objects.filter(base_dados_id=OuterRef('base_dados_id'))
        .exclude(resultado__in=ResultadoAtualizacao.FALHAS)
        .order_by('-data')
        .values('data')[:1]
    )
    contagens = (
        AtualizacaoBaseDados.objects.filter(base_dados_id__in=bases_ids)
        .annotate(_corte=Subquery(ultimo_nao_falha))
        .filter(Q(_corte__isnull=True) | Q(data__gt=F('_corte')))
        .values('base_dados_id')
        .annotate(total=Count('id'))
    )
    return {linha['base_dados_id']: linha['total'] for linha in contagens}


def _ultimas_atualizacoes(bases_ids) -> dict:
    """Última tentativa de atualização automática de cada base, numa só consulta."""
    if not bases_ids:
        return {}
    registros = AtualizacaoBaseDados.objects.filter(base_dados_id__in=bases_ids).order_by('base_dados_id', '-data').distinct('base_dados_id')
    return {registro.base_dados_id: registro for registro in registros}


def buscar_bases_relacionadas(pda):
    """Retorna o queryset de PDABaseDados com selects e anotações necessários."""
    return list(
        PDABaseDados.objects.filter(pda=pda)
        .select_related('base_dados', 'base_dados__organizacao', 'responsavel_abertura', 'unidade_responsavel_abertura')
        .prefetch_related(
            Prefetch(
                'base_dados__recursos',
                queryset=RecursoDados.objects.only('id', 'dataset_id', 'nome', 'url', 'arquivo', 'id_remoto', 'sincronizado_em').order_by(
                    'nome', 'id'
                ),
            )
        )
        .prefetch_related(Prefetch('eventos_lai', queryset=DeliberacaoLAI.objects.select_related('autor__pessoa').order_by('data', 'id')))
        .annotate(num_recursos=Count('base_dados__recursos', distinct=True))
        .order_by('base_dados__titulo')
    )


def _ultimo_evento(relacao, tipo: int):
    """Último evento do tipo na relação, usando o prefetch (sem consulta adicional por base)."""
    return next((e for e in reversed(list(relacao.eventos_lai.all())) if e.tipo == tipo), None)


def anotar_deliberacao_lai(bases_relacionadas: list) -> list:
    """Anexa a cada base devolvida o parecer que a devolveu, e devolve a lista das devolvidas.

    O gestor precisa ler o pedido de ajuste onde acompanha o PDA — até aqui o parecer só existia
    no admin de eventos, fora do menu.
    """
    devolvidas = []
    for relacao in bases_relacionadas:
        relacao.eventos_ordenados = list(relacao.eventos_lai.all())
        relacao.parecer_lai = _ultimo_evento(relacao, TipoEventoLAI.DEVOLUCAO)
        if relacao.situacao_lai == SituacaoLAI.DEVOLVIDO:
            devolvidas.append(relacao)
    return devolvidas


def montar_dados_bases_pda(bases_relacionadas, user, hoje=None):
    """
    Anota cada PDABaseDados com atributos de exibição: status CKAN, prazo,
    contagem de recursos e periodicidade de sincronização.
    Retorna também os dicts plano_pendencias e ckan_resumo para o contexto.
    """
    if hoje is None:
        hoje = date.today()

    ckan_configurado = is_ckan_configured()
    usuario_pode_sincronizar_ckan = user.has_perm('dados_abertos.change_basedados')
    ids_bases = [rel.base_dados_id for rel in bases_relacionadas]
    ultimas_atualizacoes = _ultimas_atualizacoes(ids_bases)
    falhas_por_base = falhas_consecutivas(ids_bases)

    for rel in bases_relacionadas:
        # Prazo de abertura
        if rel.meta_prazo_abertura:
            diff = (rel.meta_prazo_abertura - hoje).days
            if diff < 0:
                rel.prazo_status = 'vencido'
            elif diff <= 30:
                rel.prazo_status = 'proximo'
            else:
                rel.prazo_status = 'ok'
        else:
            rel.prazo_status = 'sem_prazo'

        # Recursos e sincronização CKAN
        recursos = list(rel.base_dados.recursos.all())
        rel.recursos_ckan = recursos
        rel.recursos_com_fonte = [r for r in recursos if r.url or r.arquivo]
        rel.recursos_sincronizados = [r for r in recursos if r.id_remoto]
        rel.num_recursos_com_fonte = len(rel.recursos_com_fonte)
        rel.num_recursos_sincronizados = len(rel.recursos_sincronizados)
        rel.ultimo_recurso_sincronizado_em = max((r.sincronizado_em for r in recursos if r.sincronizado_em), default=None)
        rel.ultima_sincronizacao_ckan = max(
            [dt for dt in [rel.base_dados.sincronizado_em, rel.ultimo_recurso_sincronizado_em] if dt],
            default=None,
        )
        rel.ckan_configurado = ckan_configurado
        rel.usuario_pode_sincronizar_ckan = usuario_pode_sincronizar_ckan
        rel.sincronizacao_configurada = ckan_configurado and rel.num_recursos_com_fonte > 0
        rel.pode_sincronizar_ckan = ckan_configurado and usuario_pode_sincronizar_ckan and rel.num_recursos_com_fonte > 0

        # Status CKAN
        if rel.base_dados.id_remoto and rel.num_recursos and rel.num_recursos_sincronizados == rel.num_recursos:
            rel.ckan_status = 'sincronizado'
            rel.ckan_status_label = 'Dataset e recursos sincronizados'
        elif rel.base_dados.id_remoto and rel.num_recursos_sincronizados:
            rel.ckan_status = 'parcial'
            rel.ckan_status_label = 'Sincronização parcial'
        elif rel.base_dados.id_remoto:
            rel.ckan_status = 'dataset'
            rel.ckan_status_label = 'Dataset sincronizado, recursos pendentes'
        else:
            rel.ckan_status = 'pendente'
            rel.ckan_status_label = 'Aguardando primeira sincronização'

        _avaliar_periodicidade_sync(rel, hoje)

        # Atualização automática: último desfecho e se ela sequer é possível nesta base.
        rel.ultima_atualizacao = ultimas_atualizacoes.get(rel.base_dados_id)
        rel.falhas_consecutivas = falhas_por_base.get(rel.base_dados_id, 0)
        rel.tem_fonte_automatica = any(r.url for r in recursos)
        rel.atualizacao_pendente = bool(rel.ultima_atualizacao and rel.ultima_atualizacao.resultado in ResultadoAtualizacao.PENDENTES)
        if rel.periodicidade_status == 'atrasada' and not rel.tem_fonte_automatica:
            # Atrasada e sem URL de origem: nenhuma rotina resolve, alguém precisa subir o arquivo.
            rel.periodicidade_status = 'manual_pendente'
            rel.periodicidade_label = 'Atualização manual pendente'

    plano_pendencias = {
        'sem_recurso': [r for r in bases_relacionadas if r.num_recursos == 0],
        'sem_ckan': [r for r in bases_relacionadas if not r.base_dados.id_remoto],
        'prazo_vencido': [r for r in bases_relacionadas if r.prazo_status == 'vencido'],
        'sem_responsavel': [r for r in bases_relacionadas if not r.responsavel_abertura_id],
        'sem_prazo': [r for r in bases_relacionadas if not r.meta_prazo_abertura],
    }

    ckan_resumo = {
        'configurado': ckan_configurado,
        'bases_sincronizadas': sum(1 for r in bases_relacionadas if r.ckan_status == 'sincronizado'),
        'bases_atrasadas': sum(1 for r in bases_relacionadas if r.periodicidade_status in ('atrasada', 'manual_pendente')),
        'bases_com_falha': sum(1 for r in bases_relacionadas if r.falhas_consecutivas),
        'bases_sem_configuracao': sum(1 for r in bases_relacionadas if not r.sincronizacao_configurada),
    }

    return bases_relacionadas, plano_pendencias, ckan_resumo
