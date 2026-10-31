"""Aba "Comissão" do dashboard RSC-TAE: volume de deliberação por membro, agrupado por categoria.

Reproduz a estrutura do relatório "Trabalho da CRSC" (``rsc_tae/docs/relatorio-comissao.png``):
um card por categoria, cada um listando MEMBRO e TOTAL em ordem decrescente, com o total da
categoria no rodapé.

Os cards são **dinâmicos**: toda categoria cadastrada vira um card, na ordem definida no cadastro.
Hoje são CONSUP, DIGPE e CIS-PCCTAE, mas nada aqui depende desses nomes. Membros sem categoria
ganham um card próprio, exibido por último e apenas quando existem — o campo nasce vazio, então
no primeiro acesso todos caem nele.

Ao contrário do painel de avaliadores, aqui **não há anonimização**: o número mede volume de
trabalho, não desempenho individual, e o dashboard já é restrito a RH sistêmico e membros da CRSC.
"""

from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import Count

from rh.models import Servidor
from rsc_tae.models import (
    CategoriaMembroComissaoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    MembroComissaoRSCTae,
    VotoDeliberacaoFinalRSCTae,
)

SEM_CATEGORIA = 'Sem categoria'


def _membros_ativos() -> list[MembroComissaoRSCTae]:
    """Membros ativos da comissão ativa, com o nome já resolvido.

    Sem ``select_related('categoria')`` de propósito: o agrupamento usa ``categoria_id``, que já
    vem na própria linha, e o título do card sai da consulta de categorias. O JOIN não pagaria nada.

    O ``relacionamento`` do vínculo é ``GenericForeignKey`` e o ``__str__`` do ``Servidor`` lê
    ``pessoa_fisica``: sem o ``GenericPrefetch`` seriam duas consultas por membro.
    """
    return list(
        MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True)
        .select_related('vinculo__pessoa')
        .prefetch_related(GenericPrefetch('vinculo__relacionamento', [Servidor.objects.select_related('pessoa_fisica')]))
        .order_by('vinculo__pessoa__nome')
    )


def _totais_por_vinculo(vinculo_ids: list[int]) -> dict[int, int]:
    """``{vinculo_id: total de deliberações}`` — votos de item + votos finais.

    Duas consultas agregadas, uma por modelo de voto; nada por linha.

    O total é o histórico **completo** do vínculo, e não o recorte da vigência da comissão atual:
    a mesma pessoa costuma ser recadastrada a cada nova comissão, e o indicador mede o trabalho
    dela, não o do mandato. Decisão consciente — se um dia o recorte por mandato for necessário,
    o caminho é filtrar ``data_deliberacao`` pela vigência da comissão.

    Voto de desempate fica **fora**: é prerrogativa do presidente e inflaria o número dele por
    causa do cargo, não do trabalho. Contar só voto normal mantém os membros comparáveis.
    """
    totais = dict.fromkeys(vinculo_ids, 0)

    for modelo in (DeliberacaoItemCRSCRSCTae, VotoDeliberacaoFinalRSCTae):
        agregado = (
            modelo.objects.filter(deliberado_por_vinculo_id__in=vinculo_ids, desempate=False)
            .values('deliberado_por_vinculo_id')
            .annotate(total=Count('id'))
        )
        for linha in agregado:
            totais[linha['deliberado_por_vinculo_id']] += linha['total']

    return totais


def _montar_card(titulo: str, membros: list[MembroComissaoRSCTae], totais: dict[int, int]) -> dict:
    """Um card: linhas em ordem decrescente de total e a soma da categoria no rodapé."""
    linhas = [
        {
            # Texto, e não o objeto: a ordenação abaixo desempata por ele, e objeto não é ordenável.
            'membro': str(membro.vinculo.relacionamento or membro.vinculo),
            'total': totais.get(membro.vinculo_id, 0),
        }
        for membro in membros
    ]
    linhas.sort(key=lambda linha: (-linha['total'], linha['membro']))
    return {
        'titulo': titulo,
        'linhas': linhas,
        'total': sum(linha['total'] for linha in linhas),
        'total_membros': len(linhas),
    }


def cards_por_categoria() -> list[dict]:
    """Um card por categoria cadastrada, mais o de "Sem categoria" quando houver membros nele.

    Percorre as categorias, e não os membros: categoria recém-cadastrada aparece de imediato, com
    o card vazio, sinalizando que ninguém foi associado a ela ainda.
    """
    membros = _membros_ativos()
    totais = _totais_por_vinculo([membro.vinculo_id for membro in membros])

    por_categoria: dict[int | None, list[MembroComissaoRSCTae]] = {}
    for membro in membros:
        por_categoria.setdefault(membro.categoria_id, []).append(membro)

    cards = [_montar_card(categoria.nome, por_categoria.get(categoria.pk, []), totais) for categoria in CategoriaMembroComissaoRSCTae.objects.all()]

    # Sempre por último, e só quando existe: um card vazio de "Sem categoria" não informaria nada.
    sem_categoria = por_categoria.get(None, [])
    if sem_categoria:
        cards.append(_montar_card(SEM_CATEGORIA, sem_categoria, totais))
    return cards


def montar_painel_comissao() -> dict:
    """Conteúdo da aba "Comissão".

    Não recebe ``request``, ao contrário de ``montar_painel_avaliadores``: lá o usuário decide a
    anonimização, aqui os nomes são sempre visíveis e nada depende de quem está olhando.
    """
    cards = cards_por_categoria()
    tem_sem_categoria = any(card['titulo'] == SEM_CATEGORIA for card in cards)
    return {
        'cards': cards,
        'total_geral': sum(card['total'] for card in cards),
        'total_membros': sum(card['total_membros'] for card in cards),
        # Só as categorias do cadastro: contar o card "Sem categoria" faria o KPI dizer 4 com três
        # categorias cadastradas, contradizendo o próprio rótulo.
        'total_categorias': len(cards) - (1 if tem_sem_categoria else 0),
        'tem_sem_categoria': tem_sem_categoria,
    }
