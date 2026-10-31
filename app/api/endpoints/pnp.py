from ninja import Router

from api.schemas.pnp import ServidorNaoDocenteSchema
from djtools.ninja.auth import TrustedAppAuth
from djtools.ninja.router import get
from rh.models import Servidor

router = Router(tags=['PNP'])
router.api_url_prefix = 'pnp'


@get(
    router,
    'servidores-nao-docentes/',
    response=list[ServidorNaoDocenteSchema],
    auth=TrustedAppAuth(),
    summary='Servidores não docentes',
    description='Lista os servidores não docentes do sistema.',
)
def servidores_nao_docentes(request):
    """Retorna os servidores não docentes do sistema."""
    # exclude em vez de filter(eh_docente=False): o campo é anulável e quem está com ele
    # nulo (nem docente nem técnico-administrativo) também não é docente
    return Servidor.objects.exclude(eh_docente=True).select_related('pessoa_fisica', 'situacao', 'setor__uo__estruturapnp').order_by('id')
