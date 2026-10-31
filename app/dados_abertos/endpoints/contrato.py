import datetime

from django.db.models import Q, QuerySet
from django.http import HttpRequest
from ninja import Query, Router

from contratos.models import (
    Contrato,
)
from djtools.ninja.router import get

from ..schemas.contrato import (
    ContratoSchema,
)
from ..schemas.filters import (
    AnoFilter,
)

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/contratos/',
    response=list[ContratoSchema],
    auth=False,
    summary='Contratos',
    description='Retorna número do contrato, ano do contrato, campus, objeto, data de início, data de término, valor total, valor executado, cnpj da contratada e razão social da contratada',
)
def contrados(request: HttpRequest, filtros: AnoFilter = Query(...)) -> QuerySet[Contrato]:  # noqa: B008
    ano = filtros.ano
    data_inicio = datetime.date(ano, 1, 1)
    data_fim = datetime.date(ano, 12, 31)
    contratos = Contrato.objects.filter(Q(data_inicio__lte=data_fim), Q(data_fim__gte=data_inicio) | Q(data_fim=None))
    return contratos.select_related('vinculo_contratado__pessoa__pessoajuridica')
