from django.db.models import QuerySet
from django.http import HttpRequest
from ninja import Router

from contratos.models import (
    Contrato,
)
from djtools.ninja.router import get

from ..schemas.engenharia import (
    ObraSchema,
)

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/engenharia/',
    response=list[ObraSchema],
    auth=False,
    summary='Engenharia',
    description='Retorna numero contrato, cnpj empresa, razão social empresa, descrição da obra, data de início, data de término e valor da obra.',
)
def contrados(request: HttpRequest) -> QuerySet[Contrato]:
    return Contrato.objects.filter(tipo=5).select_related('vinculo_contratado__pessoa__pessoajuridica')
