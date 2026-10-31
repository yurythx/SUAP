from ninja import Router

from djtools.ninja.router import get
from patrimonio.models import (
    Inventario,
)

from ..schemas.patrimonio import (
    InventarioSchema,
)

router = Router(tags=['Dados Abertos'])


@get(
    router,
    '/inventario/',
    response=list[InventarioSchema],
    auth=False,
    summary='Inventários',
    description='Retorna número, descricao, situação, estado de conservação, valor inicial, valor liquido contábil, campus dos itens do inventário',
)
def inventarios(
    request,
):
    return Inventario.objects.all()
