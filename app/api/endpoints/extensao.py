from django.db.models import Exists, OuterRef
from ninja import Router

from api.schemas.extensao import ProjetoSchema
from djtools.ninja.router import get
from projetos.models import Projeto, ProjetoCancelado, RegistroConclusaoProjeto

router = Router(tags=['Extensão'])
router.api_url_prefix = 'extensao'


@get(
    router,
    '/projetos/',
    response=list[ProjetoSchema],
    summary='Obtém projetos',
    description='Obtém todos os projetos em execucao e concluidos',
)
def projetos(request):
    """
    Obtém todos os projetos em execução e concluídos.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de dicionários contendo informações dos projetos.
    """

    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos = (
        Projeto.objects.filter(
            pre_aprovado=True,
            aprovado=True,
            inativado=False,
        )
        .exclude(id__in=projetos_cancelados)
        .select_related(
            'uo',
            'vinculo_coordenador__pessoa',
            'vinculo_coordenador__user',
        )
        .annotate(
            is_concluido=Exists(
                RegistroConclusaoProjeto.objects.filter(
                    projeto=OuterRef('pk'),
                    dt_avaliacao__isnull=False,
                )
            )
        )
        .order_by('-is_concluido', '-id')
    )
    return projetos
