# ruff: noqa: B008

import datetime
from collections.abc import Iterable

from django.db.models import Count, F
from django.http import HttpRequest
from ninja import Query, Router

from api.schemas.institucional import DocumentoTextoFiltersSchema, DocumentoTextoSchema, SuapEmNumerosSchema
from djtools.ninja.router import get
from documento_eletronico.models import DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from edu.models import Aluno
from pesquisa.models import Projeto as ProjPesquisa
from pesquisa.models import ProjetoCancelado as ProjPesqCancelado
from projetos.models import Edital as EditalExt
from projetos.models import Projeto as ProjExt
from projetos.models import ProjetoCancelado as ProjExtCancelado
from rh.models import Servidor

router = Router(tags=['Gestão Institucional'])
router.api_url_prefix = 'institucional'

type EstatisticaCampus = dict[str, int | str]


def _get_alunos_ativos_por_campus() -> Iterable[EstatisticaCampus]:
    return (
        Aluno.ativos.filter(curso_campus__diretoria__setor__uo__isnull=False)
        .values(
            campus_id=F('curso_campus__diretoria__setor__uo_id'),
            campus_sigla=F('curso_campus__diretoria__setor__uo__sigla'),
            campus_nome=F('curso_campus__diretoria__setor__uo__nome'),
        )
        .annotate(alunos_ativos=Count('id'))
    )


def _get_servidores_ativos_por_campus() -> Iterable[EstatisticaCampus]:
    return (
        Servidor.objects.ativos()
        .filter(setor__uo__isnull=False)
        .values(
            campus_id=F('setor__uo_id'),
            campus_sigla=F('setor__uo__sigla'),
            campus_nome=F('setor__uo__nome'),
        )
        .annotate(servidores_ativos=Count('id'))
    )


def _get_estatisticas_por_campus() -> list[EstatisticaCampus]:
    estatisticas = {}
    for dados_alunos in _get_alunos_ativos_por_campus():
        estatisticas[dados_alunos['campus_id']] = {
            'campus_id': dados_alunos['campus_id'],
            'campus_sigla': dados_alunos['campus_sigla'],
            'campus_nome': dados_alunos['campus_nome'],
            'alunos_ativos': dados_alunos['alunos_ativos'],
            'servidores_ativos': 0,
        }

    for dados_servidores in _get_servidores_ativos_por_campus():
        campus_id = dados_servidores['campus_id']
        estatisticas.setdefault(
            campus_id,
            {
                'campus_id': campus_id,
                'campus_sigla': dados_servidores['campus_sigla'],
                'campus_nome': dados_servidores['campus_nome'],
                'alunos_ativos': 0,
                'servidores_ativos': 0,
            },
        )
        estatisticas[campus_id]['servidores_ativos'] = dados_servidores['servidores_ativos']

    return sorted(estatisticas.values(), key=lambda estatistica: estatistica['campus_sigla'])


@get(
    router,
    'estatisticas/',
    auth=False,
    response=SuapEmNumerosSchema,
    summary='Obtém estatisticas do SUAP',
    description='Obtém dados estatísticos do SUAP',
)
def suap_em_numeros(request: HttpRequest) -> dict[str, object]:
    """
    Obtém dados estatísticos do SUAP.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        dict: Dicionário contendo as estatísticas do SUAP.
    """
    hoje = datetime.datetime.now()
    alunos_ativos = Aluno.ativos.count()
    servidores_ativos = Servidor.objects.ativos().count()

    projetos_pesquisa_cancelados = ProjPesqCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos_pesquisa_em_execucao = (
        ProjPesquisa.objects.filter(pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False)
        .exclude(id__in=projetos_pesquisa_cancelados)
        .count()
    )

    projetos_extensao_cancelados = ProjExtCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
    projetos_extensao_nao_concluidos = ProjExt.objects.filter(
        pre_aprovado=True, aprovado=True, registroconclusaoprojeto__dt_avaliacao__isnull=True, inativado=False
    ).exclude(id__in=projetos_extensao_cancelados)
    projetos_extensao_em_execucao = (
        projetos_extensao_nao_concluidos.filter(edital__divulgacao_selecao__lt=hoje)
        | projetos_extensao_nao_concluidos.filter(edital__tipo_fomento=EditalExt.FOMENTO_EXTERNO)
    ).count()

    resultado = {}
    resultado['next'] = None
    resultado['previous'] = None
    resultado['results'] = {
        'alunos_ativos': alunos_ativos,
        'servidores_ativos': servidores_ativos,
        'projetos_extensao_em_execucao': projetos_extensao_em_execucao,
        'projetos_pesquisa_em_execucao': projetos_pesquisa_em_execucao,
        'estatisticas_por_campus': _get_estatisticas_por_campus(),
    }

    return resultado


@get(
    router,
    'consulta_publica/documentos/',
    response=list[DocumentoTextoSchema],
    summary='Obtem documentos eletrônicos públicos',
    description='Obtém a lista de documentos eletrônicos públicos.',
)
def documentos_publicos(request, filters: DocumentoTextoFiltersSchema = Query(...)):
    """
    Obtém a lista de documentos eletrônicos públicos

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a busca de documentos: identificador.

    Returns:
        QuerySet: Lista de documentos filtrados com identificador e url_publica.
    """
    qs = DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO, modelo__tipo_documento_texto__consulta_publica=True)
    qs = filters.filter(qs)
    return qs
