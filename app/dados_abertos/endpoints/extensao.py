from ninja import Query, Router
from ninja.pagination import PageNumberPagination, paginate

from djtools.ninja.router import get
from projetos.models import Projeto, ProjetoCancelado

from ..schemas.extensao import ProjetoOut
from ..schemas.filters import AnoFilter

router = Router(tags=['Dados Abertos'])


@paginate(PageNumberPagination)
@get(
    router,
    '/projetos_desenvolvidos/',
    response=list[ProjetoOut],
    auth=False,
    summary='Projetos de extensão desenvolvidos',
    description='Retorna as informações sobre os projetos de extensão desenvolvidos.',
)
def projetos(request, filtros: AnoFilter = Query(...)):  # noqa: B008
    ano = filtros.ano
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    return Projeto.objects.filter(pre_aprovado=True, aprovado=True, inativado=False, inicio_execucao__year=ano).exclude(id__in=projetos_cancelados)
