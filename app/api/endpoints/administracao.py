# ruff: noqa: B008
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404
from ninja import Query, Router
from oauth2_provider.decorators import protected_resource

from api.schemas.administracao import (
    AcessoSchema,
    MaoDeObraFiltersSchema,
    MaoDeObraSchema,
    ProcessoDetalheSchema,
    ProcessoFiltersSchema,
    ProcessoSchema,
)
from contratos.models import Contrato, MaoDeObra
from djtools.ninja.router import get
from portaria.models import Acesso
from protocolo.models import Processo

router = Router(tags=['Administração'])
router.api_url_prefix = 'administracao'


@get(
    router,
    'meus-processos-fisicos/',
    response=list[ProcessoSchema],
    summary='Obtem meus processos físicos',
    description='Obtém a lista de processos do Servidor logado.',
)
def obtem_meus_processos(request, filters: ProcessoFiltersSchema = Query(...)):
    """
    Obtém a lista de processos do Servidor logado.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a busca de processos.

    Returns:
        QuerySet: Lista de processos filtrados.
    """
    qs = Processo.objects.filter(interessado_documento=request.user.get_profile().cpf).order_by('-data_cadastro')
    qs = filters.filter(qs)
    return qs


@get(
    router,
    'meu-processo-fisico/{pk}/',
    response=ProcessoDetalheSchema,
    summary='Obtem processo físico pessoal específico detalhado',
    description='Obtém um processo físico específico do Servidor logado.',
)
@protected_resource(scopes=['dados_publicos'])
def obtem_processo(request, pk: int):
    """
    Obtém um processo específico do Servidor logado.

    Args:
        request: Objeto de requisição HTTP.
        pk: ID do processo.

    Returns:
        Processo: Objeto do processo detalhado.

    Raises:
        Http404: Se o processo não for encontrado.
    """
    return get_object_or_404(Processo, interessado_documento=request.user.get_profile().cpf, pk=pk)


@get(
    router,
    'validar-visitante-portaria/{chave_wifi}/',
    auth=False,
    response=AcessoSchema,
    summary='Exibe a validade de uma determinada chave wifi.',
    description='Exibe a validade de uma determinada chave wifi.',
    by_alias=True,
)
def validar_visitante(request, chave_wifi: str):
    """
    Exibe a validade de uma determinada chave wifi.

    Args:
        request: Objeto de requisição HTTP.
        chave_wifi (str): Chave wifi a ser validada.

    Returns:
        dict: Dicionário contendo a validade da chave wifi ou mensagem de erro.
    """
    obj = get_object_or_404(Acesso.objects.validos(), chave_wifi=chave_wifi)
    return 200, obj


@get(
    router,
    'terceirizados/',
    response=list[MaoDeObraSchema],
    summary='Obtem terceirizados ativos',
    description='Obtem os terceirizados ativos da instituição',
)
def terceirizados(request, filters: MaoDeObraFiltersSchema = Query(...)):
    """
    Obtém os terceirizados ativos da instituição.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a consulta de terceirizados.

    Returns:
        list: Lista de objetos de terceirizados.
    """
    qs = MaoDeObra.objects.filter(Exists(Contrato.objects.ativos().filter(pk=OuterRef('contrato_id'))))
    qs = qs.select_related(
        'contrato',
        'prestador_servico',
        'prestador_servico__pessoa_fisica',
        'prestador_servico__setor',
        'campus',
    ).prefetch_related(
        'prestador_servico__ocupacaoprestador_set__ocupacao',
    )
    qs = qs.order_by('prestador_servico__pessoa_fisica__nome', 'pk')
    qs = filters.filter(qs)
    return qs.distinct()
