from ninja import Router

from api.schemas.demandas import ErrorSchema, PipelineStatusSchema
from demandas.models import Entrega
from djtools.ninja.router import get

router = Router(tags=['Entregas'])
router.api_url_prefix = 'entregas'

_NOT_FOUND = {
    'error': 'entrega_not_found',
    'hint': 'Verifique se o ID da entrega está correto',
    'context': {},
}
_PERMISSION_DENIED = {
    'error': 'permission_denied',
    'hint': 'O usuário autenticado não tem permissão para esta demanda',
    'context': {},
}
_PIPELINE_NOT_LINKED = {
    'error': 'pipeline_not_linked',
    'hint': 'Esta entrega não tem pipeline associado',
    'context': {},
}


@get(
    router,
    '{id}/pipeline-status/',
    response={200: PipelineStatusSchema, 403: ErrorSchema, 404: ErrorSchema, 422: ErrorSchema},
    summary='Status do pipeline da entrega',
    description='Retorna pipeline_id e status da entrega conforme registrado no banco.',
)
def pipeline_status(request, id: int):
    try:
        entrega = Entrega.objects.select_related('demanda').get(pk=id)
    except Entrega.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'entrega_id': id}}
    if not entrega.demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'entrega_id': id}}
    if not entrega.pipeline_id:
        return 422, {**_PIPELINE_NOT_LINKED, 'context': {'entrega_id': id}}
    return 200, entrega
