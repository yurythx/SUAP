import json
from functools import reduce
from operator import or_
from urllib.parse import parse_qs

from django.conf import settings
from django.db import models
from ninja import Router
from sentry_sdk import capture_exception

from api.endpoints.demandas import router as demandas_router
from api.endpoints.entregas import router as entregas_router
from api.schemas.ti import (
    AtualizacaoSchema,
    AutocompleteSchema,
    DisponibilidadeServicoSchema,
    RespostaSchema,
    ServicoSchema,
    SolicitacaoSchema,
    serialize_list,
)
from catalogo_provedor_servico.models import Solicitacao
from catalogo_provedor_servico.providers.base import Resposta
from catalogo_provedor_servico.providers.factory import get_service_provider_factory
from catalogo_provedor_servico.utils import obter_choices_por_funcao
from demandas.models import Atualizacao
from djtools.ninja.auth import TrustedAppAuth
from djtools.ninja.router import get, post
from djtools.utils import mask_cpf

router = Router(tags=['Tecnologia da Informação'])
router.api_url_prefix = 'ti'

# Demandas e entregas fazem parte do domínio de TI; seus routers são montados
# como sub-routers de `ti` (não como áreas próprias em suap/api.py), expondo-os
# em /api/ti/demandas/... e /api/ti/entregas/...
router.add_router(demandas_router.api_url_prefix, demandas_router)
router.add_router(entregas_router.api_url_prefix, entregas_router)

BALCAO_DIGITAL_RESPONSE_CODES = frozenset({200, 201, 400, 403, 404})


@get(
    router,
    'balcao-digital/{int:id_servico_portal_govbr}/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Lista um serviço ativo especifico do catalogo digital',
    description='Lista os serviços ativos do catalogo digital',
)
def servicos_ativos(request, id_servico_portal_govbr: int | None):
    """
    Obtém os serviços ativos com base no ID do portal de serviço fornecido.

    Args:
        request: O objeto de requisição HTTP.
        id_servico_portal_govbr (Optional[int]): O ID do portal de serviço do GovBR.

    Returns:
        tuple: Uma tupla contendo o código de status HTTP e a resposta JSON.
            - Se serviços ativos forem encontrados, retorna (200, resposta JSON com a lista de serviços ativos).
            - Se nenhum serviço ativo for encontrado, retorna (200, resposta JSON com uma mensagem indicando nenhum serviço ativo).
            - Se ocorrer uma exceção, retorna (404, resposta JSON com uma mensagem de erro).

    Raises:
        Exception: Se um erro ocorrer e a configuração DEBUG estiver ativada, a exceção é lançada.
    """
    try:
        servicos_ativos = get_service_provider_factory().get_servicos_ativos(id_servico_portal_govbr=id_servico_portal_govbr)
        if not servicos_ativos:
            return 200, Resposta(mensagem='Nenhum serviço ativo.').json()
        resposta = Resposta(resposta=serialize_list(servicos_ativos, ServicoSchema))
        return 200, resposta.json()
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(mensagem='Erro ao listar os serviços ativos.', exception=e)
        return 404, resposta.json()


@get(
    router,
    'balcao-digital/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Lista todos os serviços ativos do catalogo digital',
    description='Lista todos os serviços ativos do catalogo digital',
)
def todos_servicos_ativos(request):
    """
    Recupera todos os serviços ativos sem nenhuma filtragem.

    Esta função serve como um encapsulador para servicos_ativos(), passando None como parâmetro de filtro
    para retornar todos os serviços ativos no sistema.

    Args:
        request: O objeto de requisição HTTP contendo as informações da requisição.

    Returns:
        HttpResponse: A resposta contendo os dados de todos os serviços ativos.
    """
    return servicos_ativos(request, None)


@get(
    router,
    'balcao-digital/cpf/{cpf}/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Lista os serviços disponíveis para um determinado usuário',
    description='Lista os serviços disponíveis para um determinado usuário',
)
def servicos_disponiveis(request, cpf: str):
    """
    Retorna os serviços disponíveis para um determinado CPF.
    Args:
        request: Objeto de requisição HTTP
        cpf (str): CPF do usuário no formato XXX.XXX.XXX-XX ou sem formatação
    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta
                Em caso de sucesso:
                    - lista de serviços disponíveis ou mensagem indicando que não há serviços
                Em caso de erro:
                    - mensagem de erro
    Raises:
        Exception: Em ambiente de desenvolvimento (DEBUG=True), propaga exceções encontradas
    Notes:
        - O CPF é automaticamente formatado usando a função mask_cpf
        - Em produção, exceções são capturadas e reportadas via sentry
    """
    try:
        cpf = mask_cpf(cpf)
        servicos = get_service_provider_factory().get_servicos_disponiveis(cpf)
        if not servicos:
            return 200, Resposta(mensagem='Nenhum serviço disponível.').json()

        resposta = Resposta(resposta=serialize_list(servicos, ServicoSchema))
        return 200, resposta.json()
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(mensagem='Erro ao listar os serviços disponíveis.', exception=e)
        return 404, resposta.json()


@get(
    router,
    'balcao-digital/cpf/{cpf}/avaliacao_disponibilidade/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Lista os serviços disponíveis para um determinado usuário',
    description='Lista os serviços disponíveis para um determinado usuário',
)
def servicos_avaliacao_disponibilidade(request, cpf: str):
    """
    Obtém as avaliações de disponibilidade de serviços para um determinado CPF.
    Esta função consulta e retorna as avaliações de disponibilidade de serviços associadas
    a um CPF específico. Caso nenhuma avaliação seja encontrada, retorna uma mensagem indicando
    a ausência de avaliações.
    Args:
        request: Objeto de requisição HTTP
        cpf (str): Número do CPF do usuário a ser consultado
    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta
                - Em caso de sucesso: lista de avaliações de disponibilidade
                - Em caso de erro: mensagem de erro
    Raises:
        Exception: Captura e trata qualquer exceção que ocorra durante o processamento,
                  retornando uma mensagem de erro apropriada
    """
    try:
        cpf = mask_cpf(cpf)
        avaliacoes_disponibilidade_servicos = get_service_provider_factory().get_avaliacoes_disponibilidade_servicos(cpf)
        if not avaliacoes_disponibilidade_servicos:
            return 200, Resposta(mensagem='Nenhuma avaliação de disponibilidade de serviço encontra-se disponível.').json()

        resposta = Resposta(resposta=serialize_list(avaliacoes_disponibilidade_servicos, DisponibilidadeServicoSchema))
        return 200, resposta.json()
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(
            mensagem=f'Erro ao realizar a avaliação de disponibilidade dos serviços para o cpf {cpf}.', exception=e
        )
        return 404, resposta.json()


@post(
    router,
    'balcao-digital/autocompletar/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: AutocompleteSchema},
    auth=TrustedAppAuth(),
    summary='Retorna uma lista de objetos para a busca do autocompletar do balcao digital',
    description='Retorna uma lista de objetos para a busca do autocompletar do balcao digital',
)
def servicos_autocompletar(request):
    """
    Função que retorna resultados para um campo de autocompletar.
    Esta função processa requisições para autocompletar campos baseados em choices_resource_id,
    aplicando filtros e paginação nos resultados.
    Args:
        request: Objeto HttpRequest contendo os dados da requisição.
                Espera receber um corpo com:
                - choices_resource_id (str): Identificador do recurso de choices
                - filters (dict, opcional): Filtros a serem aplicados na consulta
                - term (str, opcional): Termo de busca para filtrar resultados
                - page (int, opcional): Número da página de resultados (padrão: 1)
    Returns:
        tuple: Uma tupla contendo:
            - int: Código HTTP de status (200 para sucesso, 404 para erro)
            - dict/json: Para sucesso, retorna um dicionário com:
                - results: Lista de dicionários com 'id' e 'text' dos resultados
                - pagination: Dicionário com informação se há mais páginas
              Para erro, retorna um JSON com mensagem de erro
    Raises:
        Exception: Captura e trata exceções gerais, retornando mensagem apropriada
    """
    try:
        if request.headers.get('Content-Type') == 'application/json':
            data = json.loads(request.body.decode())
        else:
            raw_data = parse_qs(request.body.decode())
            data = {}
            for key, value in raw_data.items():
                if len(value) == 1:
                    data[key] = value[0]
                else:
                    data[key] = value

        choices_resource_id = data.get('choices_resource_id')
        if choices_resource_id:
            filters = data.get('filters')
            qs = obter_choices_por_funcao(choices_resource_id, filters)
            if not qs:
                resposta = Resposta.create_from_exception(
                    mensagem='Erro ao obter resultados do autocompletar.', exception=Exception('choices_resource_id inválido')
                )
                return 404, resposta.json()
            search_fields = qs.model.SEARCH_FIELDS
            results = []
            page = int(data.get('page', 1))
            term = data.get('term')
            if term:
                words = term.split()
                for word in words:
                    or_queries = [models.Q(**{f'{field_name}__icontains': word}) for field_name in search_fields]
                    qs = qs.filter(reduce(or_, or_queries))

            for obj in qs[20 * page - 20 : 20 * page]:
                results.append({'id': obj.pk, 'text': str(obj)})

            results = {'results': results, 'pagination': {'more': (page * 20) < qs.count()}}
            return 200, results
        else:
            resposta = Resposta.create_from_exception(
                mensagem='Erro ao obter resultados do autocompletar.', exception=Exception('choices_resource_id vazio')
            )
            return 404, resposta.json()
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(mensagem='Erro ao obter resultados do autocompletar.', exception=e)
        return 404, resposta.json()


def receber_solicitacao(request, id_servico_portal_govbr: int, cpf: str):
    """
    Recebe uma solicitação de serviço para um determinado CPF e ID de serviço.

    Args:
        request: Objeto de requisição HTTP
        id_servico_portal_govbr (int): ID do serviço no portal GovBR
        cpf (str): CPF do usuário no formato XXX.XXX.XXX-XX ou sem formatação

    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta

    Raises:
        Exception: Em ambiente de desenvolvimento (DEBUG=True), propaga exceções encontradas
    """
    try:
        cpf = mask_cpf(cpf)
        if request.headers.get('Content-Type') == 'application/json':
            data = json.loads(request.body.decode())
        else:
            raw_data = parse_qs(request.body.decode())
            data = {}
            for key, value in raw_data.items():
                if len(value) == 1:
                    data[key] = value[0]
                else:
                    data[key] = value
        request.data = data
        service_provider = get_service_provider_factory().get_service_provider(id_servico_portal_govbr=id_servico_portal_govbr)
        if not service_provider or not service_provider.get_avaliacao_disponibilidade(cpf=cpf).is_ok:
            resposta = Resposta(mensagem=f'Serviço indisponível para o cpf {cpf}.')
            return 200, resposta.json()

        return service_provider.receber_solicitacao(request=request, cpf=cpf)
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(mensagem='Erro ao receber solicitação.', exception=e)
        return 404, resposta.json()


@post(
    router,
    'balcao-digital/{int:id_servico_portal_govbr}/cpf/{str:cpf}/receber_solicitacao/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Recebe a solicitação de um determinado usuário',
    description='Recebe a solicitação de um determinado usuário',
)
def receber_solicitacao_post(request, id_servico_portal_govbr: int, cpf: str):
    """
    Recebe uma solicitação de serviço via método POST para um determinado CPF e ID de serviço.

    Args:
        request: Objeto de requisição HTTP
        id_servico_portal_govbr (int): ID do serviço no portal GovBR
        cpf (str): CPF do usuário no formato XXX.XXX.XXX-XX ou sem formatação

    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta

    Raises:
        Exception: Em ambiente de desenvolvimento (DEBUG=True), propaga exceções encontradas
    """
    request.method = 'POST'
    return receber_solicitacao(request=request, id_servico_portal_govbr=id_servico_portal_govbr, cpf=cpf)


@get(
    router,
    'balcao-digital/{int:id_servico_portal_govbr}/cpf/{str:cpf}/receber_solicitacao/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Recebe a solicitação de um determinado usuário',
    description='Recebe a solicitação de um determinado usuário',
)
def receber_solicitacao_get(request, id_servico_portal_govbr: int, cpf: str):
    """
    Recebe uma solicitação de serviço via método GET para um determinado CPF e ID de serviço.

    Args:
        request: Objeto de requisição HTTP
        id_servico_portal_govbr (int): ID do serviço no portal GovBR
        cpf (str): CPF do usuário no formato XXX.XXX.XXX-XX ou sem formatação

    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta

    Raises:
        Exception: Em ambiente de desenvolvimento (DEBUG=True), propaga exceções encontradas
    """
    request.method = 'GET'
    return receber_solicitacao(request=request, id_servico_portal_govbr=id_servico_portal_govbr, cpf=cpf)


@get(
    router,
    'balcao-digital/cpf/{str:cpf}/acompanhamentos/',
    response={BALCAO_DIGITAL_RESPONSE_CODES: RespostaSchema},
    auth=TrustedAppAuth(),
    summary='Lista os acompanhamentos de um determinado CPF',
    description='Lista os acompanhamentos de um determinado CPF',
)
def acompanhamentos_por_cidadao(request, cpf: str):
    """
    Lista os acompanhamentos de um determinado CPF.

    Args:
        request: Objeto de requisição HTTP
        cpf (str): CPF do usuário no formato XXX.XXX.XXX-XX ou sem formatação

    Returns:
        tuple: Uma tupla contendo:
            - int: Código de status HTTP (200 para sucesso, 404 para erro)
            - str: JSON contendo a resposta

    Raises:
        Exception: Em ambiente de desenvolvimento (DEBUG=True), propaga exceções encontradas
    """
    try:
        cpf = mask_cpf(cpf)
        solicitacoes = Solicitacao.objects.filter(cpf=cpf)
        if not solicitacoes:
            return 200, Resposta(mensagem='Nenhuma solicitação encontrada.').json()

        dados = serialize_list(solicitacoes, SolicitacaoSchema)
        resposta = Resposta(resposta=dados)
        return 200, resposta.json()
    except ConnectionError as e:
        resposta = Resposta.create_from_exception(mensagem='Erro ao listar os acompanhamentos.', exception=e)
        return 404, resposta.json()
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)
        resposta = Resposta.create_from_exception(mensagem='Erro ao listar os acompanhamentos.', exception=e)
        return 404, resposta.json()


@get(
    router,
    'atualizacoes-suap/',
    auth=False,
    response=list[AtualizacaoSchema],
    summary='Obtém as atualizações do SUAP',
    description='Obtém todas as atualizações do SUAP',
)
def atualizacoes(request):
    """
    Obtém todas as atualizações do SUAP.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        QuerySet: Lista de atualizações ordenadas por ID.
    """
    return Atualizacao.objects.order_by('-id').select_related('demanda').prefetch_related('grupos', 'tags', 'demanda__dod_set')
