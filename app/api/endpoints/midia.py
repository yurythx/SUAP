import datetime

from django.db.models import Prefetch
from ninja import Router

from api.schemas.midia import BannerSchema, EventoSchema
from djtools.ninja.router import get
from eventos.models import AtividadeEvento, Banner, Evento, Modalidade

router = Router(tags=['Comunicação Social'])
router.api_url_prefix = 'midia'


@get(
    router,
    'banners/',
    response=list[BannerSchema],
    summary='Obtém a lista de banners ativos',
    description='Obtém a lista de banners ativos.',
)
def banners_ativos(request):
    """
    Obtém a lista de banners ativos.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        QuerySet: Lista de banners ativos.
    """
    hoje = datetime.datetime.now()
    return Banner.objects.filter(data_inicio__lte=hoje, data_termino__gte=hoje)


@get(
    router,
    'eventos/ativos-deferidos/',
    response=list[EventoSchema],
    summary='Obtém eventos',
    description='Obtém todos os eventos ativos e deferidos.',
)
def eventos(request):
    """
    Obtém todos os eventos ativos e deferidos.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de dicionários contendo informações dos eventos ativos e deferidos.
    """
    return (
        Evento.objects.filter(deferido=True, ativo=True)
        .select_related('campus', 'classificacao')
        .prefetch_related(
            Prefetch('atividadeevento_set', queryset=AtividadeEvento.objects.select_related('tipo')),
            Prefetch('modalidade_set', queryset=Modalidade.objects.select_related('tipo')),
            'tipos_participante',
            'tipos_participante__tipo_participacao',
            'fluxos_submissao',
        )
        .order_by('-id')
    )
