from ninja import Query, Router
from ninja.pagination import PageNumberPagination, paginate

from djtools.ninja.router import get
from pesquisa.models import EmpreendimentoIncubadora, Projeto, ProjetoCancelado

from ..schemas.filters import AnoFilter
from ..schemas.pesquisa import EmpresaIncubadaOut, ProjetoOut

router = Router(tags=['Dados Abertos'])


@paginate(PageNumberPagination)
@get(
    router,
    '/empresas_incubadas/',
    response=list[EmpresaIncubadaOut],
    auth=False,
    summary='Empresas incubadas',
    description='Retorna as informações sobre as empresas incubadas.',
)
def empresas_incubadas(request, filtros: AnoFilter = Query(...)):  # noqa: B008
    ano = filtros.ano
    return EmpreendimentoIncubadora.objects.filter(data_incubacao__year=ano)


@paginate(PageNumberPagination)
@get(
    router,
    '/projetos_desenvolvidos/',
    response=list[ProjetoOut],
    auth=False,
    summary='Projetos de pesquisa desenvolvidos',
    description='Retorna as informações sobre os projetos de pesquisa desenvolvidos.',
)
def projetos(request, filtros: AnoFilter = Query(...)):  # noqa: B008
    ano = filtros.ano
    projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    return Projeto.objects.filter(pre_aprovado=True, aprovado=True, inativado=False, inicio_execucao__year=ano).exclude(id__in=projetos_cancelados)
