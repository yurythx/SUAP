from ninja import Query, Router
from ninja.pagination import PageNumberPagination, paginate

from cnpq.models import ProducaoBibliografica
from djtools.ninja.router import get

from ..schemas.cnpq import ProducaoBibiograficaOut
from ..schemas.filters import AnoFilter

router = Router(tags=['Dados Abertos'])


@paginate(PageNumberPagination)
@get(
    router,
    '/producao_academica/',
    response=list[ProducaoBibiograficaOut],
    auth=False,
    summary='Produção acadêmica',
    description=(
        'Retorna as informações sobre as produções acadêmicas de servidores. '
        'Os campos lattes_servidor_ifrn e orcid_servidor_ifrn identificam o servidor do IFRN de cujo currículo Lattes '
        'a produção foi extraída; o campo autor reproduz o primeiro autor declarado na produção, que pode ser outra pessoa.'
    ),
)
def producao_academica(request, filtros: AnoFilter = Query(...)):  # noqa: B008
    ano = filtros.ano
    return ProducaoBibliografica.objects.filter(ano=ano).select_related('curriculo__vinculo__pessoa__pessoafisica')
