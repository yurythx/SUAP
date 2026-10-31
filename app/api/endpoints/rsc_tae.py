from django.db.models import Count, Q, QuerySet
from ninja import Router

from api.schemas.rsc_tae import MemorialAvaliadoSchema
from djtools.ninja.router import get
from rsc_tae.models import ProcessoRSCTae
from rsc_tae.views._helpers import montar_dados_memorial

router = Router(tags=['RSC-TAE'])
router.api_url_prefix = 'rsc_tae'


def _processos_avaliados_por_tres() -> QuerySet[ProcessoRSCTae]:
    """Processos com pelo menos três avaliadores com avaliação finalizada.

    Conta avaliadores distintos com avaliação finalizada (assinada), sem depender do
    flag ``substituido`` nem da situação do processo: ao atingir as três avaliações
    exigidas pelo regulamento, o memorial já fica disponível para o Portal.
    """
    return (
        ProcessoRSCTae.objects.annotate(
            n_avaliadores_finalizaram=Count(
                'avaliacoes_por_avaliador__avaliador_vinculo',
                filter=Q(avaliacoes_por_avaliador__finalizada=True),
                distinct=True,
            ),
        )
        .filter(n_avaliadores_finalizaram__gte=3)
        .select_related('vinculo__pessoa', 'vinculo__setor', 'nivel_requisitado', 'processo_anterior')
        .order_by('-data_finalizacao_avaliacao', '-id')
    )


@get(
    router,
    'memoriais-avaliados/',
    response=list[MemorialAvaliadoSchema],
    auth=False,
    summary='Memoriais descritivos avaliados pelos três avaliadores',
    description='Lista o memorial descritivo dos processos RSC-TAE cujos três avaliadores já finalizaram a avaliação.',
)
def memoriais_avaliados(request):
    """Retorna a listagem de memoriais descritivos elegíveis para o Portal."""
    return [montar_dados_memorial(processo) for processo in _processos_avaliados_por_tres()]
