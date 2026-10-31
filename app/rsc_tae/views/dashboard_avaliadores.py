"""Métricas de avaliadores do dashboard RSC-TAE.

As funções de métrica são puras: recebem o mapa de rótulos e devolvem listas de dicts prontas para
o template, sem tocar em ``request``. Só ``rotulos_avaliadores`` e ``montar_painel_avaliadores``
dependem do usuário logado, porque a exibição de nomes é restrita à comissão.
"""

import json
from datetime import date, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Min, Q

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import AvaliacaoProcessoRSCTae

# Prazo, em dias, a partir do qual uma avaliação em aberto entra em alerta.
DIAS_ALERTA_SLA = 3

SEM_VALOR = '—'


def rotulos_avaliadores(request) -> dict:
    """Mapa ``vinculo_id -> rótulo``: nome real para membro ativo da CRSC, ``Avaliador N`` para os demais.

    Espelha a regra de ``rotulos_anonimos_avaliadores`` (``views/_helpers.py``): quem está fora da
    comissão não vê nomes, para não expor os avaliadores a coação. A numeração segue a ordem de
    ``vinculo_id``, então é estável entre carregamentos da página.
    """
    from rsc_tae.views._helpers import eh_membro_crsc_ativo

    pares = (
        AvaliacaoProcessoRSCTae.objects.filter(substituido=False, avaliador_vinculo__isnull=False)
        .values_list('avaliador_vinculo_id', 'avaliador_vinculo__pessoa__nome')
        .distinct()
    )
    ordenados = sorted(dict(pares).items())

    # AnonymousUser não tem get_vinculo. Testar o método, em vez de capturar Exception, mantém
    # visíveis os erros de verdade (banco fora do ar, por exemplo) em vez de virar "não é da CRSC".
    obter_vinculo = getattr(request.user, 'get_vinculo', None)
    vinculo_usuario = obter_vinculo() if obter_vinculo else None

    if eh_membro_crsc_ativo(vinculo_usuario):
        return {vinculo_id: nome or SEM_VALOR for vinculo_id, nome in ordenados}
    return {vinculo_id: f'Avaliador {posicao}' for posicao, (vinculo_id, _nome) in enumerate(ordenados, start=1)}


def carga_por_avaliador(rotulos: dict) -> list:
    """Uma linha por avaliador: pendentes, finalizadas, tempo médio de avaliação e taxa de aceite do sorteio.

    Percorre ``rotulos``, não o resultado da consulta: todo avaliador já sorteado aparece, mesmo
    zerado. Os três cards por avaliador usam a mesma lista, então as tabelas sempre batem entre si.
    """
    agregados = {
        linha['avaliador_vinculo_id']: linha
        for linha in AvaliacaoProcessoRSCTae.objects.filter(substituido=False)
        .values('avaliador_vinculo_id')
        .annotate(
            pendentes=Count('id', filter=Q(finalizada=False, processo__situacao=SituacaoProcesso.EM_ANALISE)),
            finalizadas=Count('id', filter=Q(finalizada=True)),
            tempo_medio=Avg(
                ExpressionWrapper(F('data_finalizacao') - F('data_notificacao_sorteio'), output_field=DurationField()),
                filter=Q(data_finalizacao__isnull=False, data_notificacao_sorteio__isnull=False),
            ),
            aceites=Count('id', filter=Q(resposta=AvaliacaoProcessoRSCTae.RESPOSTA_ACEITE)),
            sorteios=Count('id'),
        )
    }
    resultado = [
        {
            'avaliador': rotulo,
            'pendentes': agregados.get(vinculo_id, {}).get('pendentes', 0),
            'finalizadas': agregados.get(vinculo_id, {}).get('finalizadas', 0),
            'tempo_medio_dias': _duracao_em_dias(agregados.get(vinculo_id, {}).get('tempo_medio')),
            'taxa_aceite': _percentual(
                agregados.get(vinculo_id, {}).get('aceites', 0),
                agregados.get(vinculo_id, {}).get('sorteios', 0),
            ),
        }
        for vinculo_id, rotulo in rotulos.items()
    ]
    resultado.sort(key=lambda item: (item['pendentes'], item['finalizadas']), reverse=True)
    return resultado


def qualidade_por_avaliador(rotulos: dict) -> list:
    """Proporção de deferimento e média de itens validados por avaliador.

    Assim como ``carga_por_avaliador``, lista todos os avaliadores já sorteados — quem ainda não
    finalizou nenhuma avaliação aparece zerado, em vez de sumir da tabela.

    ``finalizadas`` conta toda avaliação concluída, igual ao card de carga. ``com_resultado`` conta
    só as que têm deferimento ou indeferimento gravado e é a base da taxa; quando os dois números
    diferem, existe avaliação finalizada sem resultado registrado — e isso precisa ficar visível.
    """
    agregados = {
        linha['avaliador_vinculo_id']: linha
        for linha in AvaliacaoProcessoRSCTae.objects.filter(substituido=False)
        .values('avaliador_vinculo_id')
        .annotate(
            finalizadas=Count('id', filter=Q(finalizada=True)),
            deferidas=Count('id', filter=Q(finalizada=True, resultado=SituacaoProcesso.DEFERIDO)),
            indeferidas=Count('id', filter=Q(finalizada=True, resultado=SituacaoProcesso.INDEFERIDO)),
            media_itens=Avg('itens_validados', filter=Q(finalizada=True)),
        )
    }
    resultado = []
    for vinculo_id, rotulo in rotulos.items():
        dados = agregados.get(vinculo_id, {})
        deferidas = dados.get('deferidas', 0)
        indeferidas = dados.get('indeferidas', 0)
        media_itens = dados.get('media_itens')
        com_resultado = deferidas + indeferidas
        resultado.append(
            {
                'avaliador': rotulo,
                'finalizadas': dados.get('finalizadas', 0),
                'com_resultado': com_resultado,
                'deferidas': deferidas,
                'indeferidas': indeferidas,
                'taxa_deferimento': _percentual(deferidas, com_resultado),
                'media_itens': round(media_itens, 1) if media_itens is not None else None,
            }
        )
    resultado.sort(key=lambda item: (item['finalizadas'], item['com_resultado']), reverse=True)
    return resultado


def processos_por_avaliador(rotulos: dict) -> list:
    """Todos os avaliadores já sorteados e os processos que estão em suas mãos agora.

    Cada avaliador aparece na lista mesmo sem processo em aberto, para que a comissão enxergue
    quem está sem carga. "Em suas mãos" significa avaliação não finalizada em processo que está
    em análise — a mesma definição usada em ``carga_por_avaliador``.
    """
    hoje = date.today()

    totais = {
        linha['avaliador_vinculo_id']: linha
        for linha in AvaliacaoProcessoRSCTae.objects.filter(substituido=False)
        .values('avaliador_vinculo_id')
        .annotate(
            recusados=Count('id', filter=Q(resposta=AvaliacaoProcessoRSCTae.RESPOSTA_RECUSA)),
            impedimentos=Count('id', filter=Q(resposta=AvaliacaoProcessoRSCTae.RESPOSTA_IMPEDIMENTO)),
        )
    }

    em_aberto = (
        AvaliacaoProcessoRSCTae.objects.filter(
            substituido=False,
            finalizada=False,
            processo__situacao=SituacaoProcesso.EM_ANALISE,
        )
        .values(
            'avaliador_vinculo_id',
            'processo_id',
            'processo__vinculo__pessoa__nome',
            'processo__nivel_requisitado__nome',
            'data_notificacao_sorteio',
            'data_limite_avaliacao',
            'data_cadastro',
        )
        .order_by('data_notificacao_sorteio', 'data_cadastro')
    )

    por_avaliador = {}
    for linha in em_aberto:
        por_avaliador.setdefault(linha['avaliador_vinculo_id'], []).append(_montar_processo_em_aberto(linha, hoje))

    resultado = []
    for vinculo_id, rotulo in rotulos.items():
        processos = por_avaliador.get(vinculo_id, [])
        dias = [processo['dias'] for processo in processos if processo['dias'] is not None]
        totais_avaliador = totais.get(vinculo_id, {})
        linha = {
            'avaliador': rotulo,
            'processos': processos,
            'em_avaliacao': len(processos),
            'dias_mais_antigo': max(dias) if dias else None,
            'recusados': totais_avaliador.get('recusados', 0),
            'impedimentos': totais_avaliador.get('impedimentos', 0),
        }
        linha['resumo'] = _resumo_avaliador(linha)
        resultado.append(linha)

    resultado.sort(key=lambda item: (item['em_avaliacao'], item['dias_mais_antigo'] or 0), reverse=True)
    # Identificador do accordion: posicional, para não expor o id do vínculo quando os nomes
    # estão anonimizados e para não quebrar em caso de avaliadores homônimos.
    for posicao, linha in enumerate(resultado, start=1):
        linha['slug'] = f'processos-avaliador-{posicao}'
    return resultado


def _resumo_avaliador(linha: dict) -> str:
    """Linha de apoio exibida na barra do accordion, ao lado do nome e do contador."""
    partes = []
    if linha['dias_mais_antigo'] is not None:
        partes.append(f'mais antigo: {linha["dias_mais_antigo"]} dia(s)')
    if linha['recusados']:
        partes.append(f'recusados: {linha["recusados"]}')
    if linha['impedimentos']:
        partes.append(f'impedimentos: {linha["impedimentos"]}')
    return ' · '.join(partes)


def _montar_processo_em_aberto(linha: dict, hoje: date) -> dict:
    """Normaliza uma avaliação em aberto: há quantos dias está com o avaliador e como está o prazo."""
    # Sorteios antigos podem não ter notificação registrada; nesse caso, a criação do registro é a
    # melhor aproximação de quando o processo passou às mãos do avaliador.
    inicio = linha['data_notificacao_sorteio'] or linha['data_cadastro']
    prazo = linha['data_limite_avaliacao']

    if prazo is None:
        situacao_prazo = 'sem-prazo'
    elif prazo < hoje:
        situacao_prazo = 'vencido'
    elif (prazo - hoje).days <= DIAS_ALERTA_SLA:
        situacao_prazo = 'vencendo'
    else:
        situacao_prazo = 'no-prazo'

    return {
        'processo_id': linha['processo_id'],
        'servidor': linha['processo__vinculo__pessoa__nome'] or SEM_VALOR,
        'nivel': linha['processo__nivel_requisitado__nome'] or SEM_VALOR,
        'dias': (hoje - inicio.date()).days if inicio else None,
        'prazo': prazo,
        'situacao_prazo': situacao_prazo,
    }


def gargalos_por_avaliador(rotulos: dict) -> list:
    """Avaliações em aberto com prazo vencido ou a vencer em até ``DIAS_ALERTA_SLA``, agrupadas por avaliador.

    Usa ``data_limite_avaliacao``, que é o prazo individual do avaliador — não o SLA do processo.
    Avaliações sem prazo registrado ficam de fora em vez de contar como zero.
    """
    hoje = date.today()
    limite_alerta = hoje + timedelta(days=DIAS_ALERTA_SLA)
    linhas = (
        AvaliacaoProcessoRSCTae.objects.filter(
            substituido=False,
            finalizada=False,
            processo__situacao=SituacaoProcesso.EM_ANALISE,
            data_limite_avaliacao__isnull=False,
            data_limite_avaliacao__lte=limite_alerta,
        )
        .values('avaliador_vinculo_id')
        .annotate(
            atrasadas=Count('id', filter=Q(data_limite_avaliacao__lt=hoje)),
            em_alerta=Count('id', filter=Q(data_limite_avaliacao__gte=hoje)),
            prazo_mais_antigo=Min('data_limite_avaliacao'),
        )
        .order_by('-atrasadas', 'prazo_mais_antigo')
    )
    return [
        {
            'avaliador': rotulos.get(linha['avaliador_vinculo_id'], SEM_VALOR),
            'atrasadas': linha['atrasadas'],
            'em_alerta': linha['em_alerta'],
            'prazo_mais_antigo': linha['prazo_mais_antigo'],
            'dias_atraso': max((hoje - linha['prazo_mais_antigo']).days, 0),
        }
        for linha in linhas
    ]


def montar_painel_avaliadores(request) -> dict:
    """Monta o conteúdo da aba "Avaliadores": KPIs do bloco, as quatro métricas e a série do gráfico de carga."""
    rotulos = rotulos_avaliadores(request)
    carga = carga_por_avaliador(rotulos)
    gargalos = gargalos_por_avaliador(rotulos)
    tempos = [linha['tempo_medio_dias'] for linha in carga if linha['tempo_medio_dias'] is not None]
    com_carga = [linha for linha in carga if linha['pendentes']]

    # Quem está sem processo em mãos vira uma linha só no rodapé do card, em vez de um accordion
    # vazio por avaliador.
    detalhe = processos_por_avaliador(rotulos)

    # Nenhuma tabela é cortada: a comissão precisa da lista completa de avaliadores. "Gargalos" é a
    # exceção natural — lá só entra quem tem prazo vencido ou vencendo, que é o propósito do card.
    return {
        'carga': carga,
        'qualidade': qualidade_por_avaliador(rotulos),
        'processos_por_avaliador': [linha for linha in detalhe if linha['em_avaliacao']],
        'avaliadores_sem_processo': [linha['avaliador'] for linha in detalhe if not linha['em_avaliacao']],
        'gargalos': gargalos,
        # KPIs da aba
        'total_avaliadores_com_carga': len(com_carga),
        'total_pendentes': sum(linha['pendentes'] for linha in carga),
        'total_atrasadas': sum(linha['atrasadas'] for linha in gargalos),
        'tempo_medio_geral': round(sum(tempos) / len(tempos), 1) if tempos else None,
        # Série do gráfico de carga (rótulos já anonimizados quando for o caso). Aqui os zerados
        # ficam de fora de propósito: barra de tamanho zero não comunica nada.
        'carga_labels': json.dumps([linha['avaliador'] for linha in com_carga]),
        'carga_totais': json.dumps([linha['pendentes'] for linha in com_carga]),
    }


def _duracao_em_dias(duracao) -> float | None:
    """Converte o ``timedelta`` médio devolvido pelo banco em dias com uma casa decimal.

    Só ``None`` (avaliador sem nenhuma avaliação datada) vira ``None``: duração zero é medição
    válida — avaliação concluída no mesmo dia do sorteio — e deve aparecer como 0,0.
    """
    if duracao is None:
        return None
    return round(duracao.total_seconds() / 86400, 1)


def _percentual(parte: int, total: int) -> int | None:
    """Percentual inteiro de ``parte`` sobre ``total``; None quando não há base de cálculo."""
    if not total:
        return None
    return round(parte / total * 100)
