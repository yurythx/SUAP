from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest
from ninja import Router

from api.schemas.demandas import (
    AgentContextSchema,
    AmbienteHomologacaoSchema,
    ByMrResponseSchema,
    ErrorSchema,
    MRStatusSchema,
    OpenMRResponseSchema,
    RevisaoEspecificacaoInputSchema,
    RevisaoEspecificacaoSchema,
    SpecDecisionInputSchema,
    SpecDecisionResponseSchema,
    SubdemandaSchema,
)
from comum.models import User
from demandas.models import AmbienteHomologacao, DecisaoEspecificacao, Demanda, DoD, Especificacao, RevisaoEspecificacao, Situacao
from djtools.ninja.router import get, post

router = Router(tags=['Demandas'])
router.api_url_prefix = 'demandas'

_NOT_FOUND = {
    'error': 'demanda_not_found',
    'hint': 'Verifique se o ID da demanda está correto',
    'context': {},
}
_PERMISSION_DENIED = {
    'error': 'permission_denied',
    'hint': 'O usuário autenticado não tem permissão para esta demanda',
    'context': {},
}


@get(
    router,
    '{id}/agent-context/',
    response={200: AgentContextSchema, 403: ErrorSchema, 404: ErrorSchema},
    summary='Contexto completo da demanda para o agente',
    description='Retorna especificação técnica, DoD, decisões arquiteturais, sub-demandas e informações de MR.',
)
def agent_context(request, id: int):
    try:
        demanda = Demanda.objects.prefetch_related(
            'dod_set',
            'dod_set__especificacao_set',
            'decisoes_especificacao',
            'decisoes_especificacao__autor',
            'subdemandas',
        ).get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    return 200, demanda


@get(
    router,
    '{id}/subdemandas/',
    # Só as filhas diretas: lista curta, devolvida inteira. Paginar embrulharia a tupla (status, corpo) como itens.
    ignore_paginate=True,
    response={200: list[SubdemandaSchema], 403: ErrorSchema, 404: ErrorSchema},
    summary='Sub-demandas diretas',
    description='Lista as sub-demandas diretas ordenadas por prioridade interna.',
)
def subdemandas(request, id: int):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    qs = demanda.get_subdemandas().annotate(
        _total_sub=Count('subdemandas'),
        _encerradas_sub=Count(
            'subdemandas',
            filter=Q(subdemandas__situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO]),
        ),
    )
    return 200, list(qs)


@get(
    router,
    '{id}/mr-status/',
    response={200: MRStatusSchema, 403: ErrorSchema, 404: ErrorSchema},
    summary='Status do MR vinculado à demanda',
    description='Retorna branch, id_merge_request e situação conforme registrado no banco.',
)
def mr_status(request, id: int):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    return 200, demanda


@post(
    router,
    '{id}/merge-request/',
    response={200: OpenMRResponseSchema, 201: OpenMRResponseSchema, 403: ErrorSchema, 404: ErrorSchema, 422: ErrorSchema},
    summary='Abre ou retorna MR vinculado à demanda',
    description='Idempotente: se o MR já existe, retorna o estado atual sem chamar o GitLab.',
)
def open_merge_request(request, id: int):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    if demanda.id_merge_request:
        demanda.already_exists = True
        return 200, demanda
    if not demanda.branch:
        return 422, {
            'error': 'branch_missing',
            'hint': 'Defina um branch para a demanda antes de abrir um MR',
            'context': {'demanda_id': id},
        }
    if not demanda.branch_existe():
        return 422, {
            'error': 'branch_not_found',
            'hint': f"O branch '{demanda.branch}' não foi encontrado no GitLab",
            'context': {'demanda_id': id, 'branch': demanda.branch},
        }
    demanda.criar_mergerequest_gitlab()
    demanda.refresh_from_db()
    if not demanda.id_merge_request:
        return 422, {
            'error': 'mr_creation_failed',
            'hint': 'Falha ao criar o MR. Verifique os logs do SUAP',
            'context': {'demanda_id': id},
        }
    demanda.already_exists = False
    return 201, demanda


@post(
    router,
    '{id}/spec-decisions/',
    response={201: SpecDecisionResponseSchema, 403: ErrorSchema, 404: ErrorSchema},
    summary='Registra decisão arquitetural na demanda',
    description='Append-only — nenhum registro existente é modificado.',
)
def create_spec_decision(request, id: int, payload: SpecDecisionInputSchema):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    decisao = DecisaoEspecificacao.objects.create(
        demanda=demanda,
        autor=request.user,
        decisao=payload.decisao,
        contexto=payload.contexto,
        origem=payload.origem,
    )
    return 201, decisao


def _erro(error: str, hint: str, **context) -> dict:
    return {'error': error, 'hint': hint, 'context': context}


def _checar_revisao(demanda: Demanda, user: User) -> tuple[int, dict] | None:
    """Mesmas condições da tela para revisar a consolidação (``tabs/dod.html`` + views de revisão).

    Permissão ``demandas.add_especificacao``, ser analista da demanda e a consolidação aceitar
    revisão: demanda em desenvolvimento ou homologação, sem validação já pedida aos demandantes.
    """
    if not (user.has_perm('demandas.add_especificacao') and demanda.eh_analista(user)):
        return 403, _erro('permission_denied', 'Só um analista da demanda com permissão de especificar pode propor revisões', demanda_id=demanda.pk)
    dod = demanda.get_dod()
    if dod is None:
        return 422, _erro('dod_not_found', 'A demanda ainda não tem consolidação', demanda_id=demanda.pk)
    if not dod.aceita_revisao:
        return 422, _erro(
            'revisao_nao_aceita',
            'A consolidação só aceita revisões com a demanda em desenvolvimento ou em homologação, '
            'antes de a validação das revisões ser solicitada aos demandantes',
            demanda_id=demanda.pk,
            situacao=demanda.situacao,
            validacao_revisao_solicitada=dod.validacao_revisao_solicitada,
        )
    return None


def _montar_revisao(dod: DoD, payload: RevisaoEspecificacaoInputSchema) -> RevisaoEspecificacao:
    """Monta a revisão como as views da tela: reaproveita a revisão pendente da especificação, se houver.

    Levanta ``Especificacao.DoesNotExist`` se a especificação não for desta consolidação e
    ``ValidationError`` se a proposta for inválida.
    """
    if payload.especificacao_id is None:
        if payload.remocao_solicitada:
            raise ValidationError('Informe a especificação cuja remoção é proposta.')
        if not (payload.nome and payload.nome.strip() and payload.atividades and payload.atividades.strip()):
            raise ValidationError('Uma especificação nova exige nome e atividades.')
        return RevisaoEspecificacao(dod=dod, nome=payload.nome, atividades=payload.atividades)

    especificacao = Especificacao.objects.get(pk=payload.especificacao_id, dod=dod)
    revisao = especificacao.revisaoespecificacao_set.first() or RevisaoEspecificacao(dod=dod, especificacao=especificacao)
    revisao.remocao_solicitada = payload.remocao_solicitada
    if payload.remocao_solicitada:
        # Igual a ``solicitar_remocao_especificacao``: a remoção não carrega conteúdo novo.
        revisao.nome, revisao.atividades = especificacao.nome, '-'
    else:
        revisao.nome = payload.nome if payload.nome is not None else especificacao.nome
        revisao.atividades = payload.atividades if payload.atividades is not None else especificacao.atividades
    return revisao


@post(
    router,
    '{id}/revisoes-especificacao/',
    response={200: RevisaoEspecificacaoSchema, 201: RevisaoEspecificacaoSchema, 403: ErrorSchema, 404: ErrorSchema, 422: ErrorSchema},
    summary='Propõe revisão de especificação da consolidação',
    description=(
        'Cria (201) ou atualiza (200) a RevisaoEspecificacao pendente — nunca altera a Especificacao aprovada: '
        'quem aplica é o demandante, ao validar. Com solicitar_validacao, envia as revisões pendentes para '
        'validação dos demandantes, como o botão "Solicitar validação das alterações".'
    ),
)
def propor_revisao_especificacao(request, id: int, payload: RevisaoEspecificacaoInputSchema):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if erro := _checar_revisao(demanda, request.user):
        return erro
    dod = demanda.get_dod()
    try:
        revisao = _montar_revisao(dod, payload)
        revisao.full_clean()
    except Especificacao.DoesNotExist:
        return 404, _erro(
            'especificacao_not_found',
            'A especificação não pertence à consolidação desta demanda',
            demanda_id=id,
            especificacao_id=payload.especificacao_id,
        )
    except ValidationError as e:
        return 422, _erro('revisao_invalida', ' '.join(e.messages), demanda_id=id)
    status = 200 if revisao.pk else 201
    with transaction.atomic():
        revisao.save()
        if payload.solicitar_validacao:
            dod.solicitar_aprovacao_modificacoes(request.user)
    return status, revisao


@get(
    router,
    '{id}/revisoes-especificacao/',
    ignore_paginate=True,
    response={200: list[RevisaoEspecificacaoSchema], 403: ErrorSchema, 404: ErrorSchema},
    summary='Revisões de especificação pendentes',
    description='Revisões propostas e ainda não aprovadas nem rejeitadas pelos demandantes.',
)
def revisoes_especificacao(request, id: int):
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    return 200, list(RevisaoEspecificacao.objects.filter(dod__demanda=demanda).select_related('dod', 'especificacao').order_by('id'))


@get(
    router,
    'by-mr/',
    response={200: ByMrResponseSchema, 403: ErrorSchema, 404: ErrorSchema},
    summary='Demanda vinculada a um MR',
    description='Retorna a demanda cujo id_merge_request corresponde ao mr_iid informado.',
)
def demanda_by_mr(request, mr_iid: int):
    try:
        demanda = Demanda.objects.get(id_merge_request=mr_iid)
    except Demanda.DoesNotExist:
        return 404, {
            'error': 'demanda_not_found',
            'hint': f'Nenhuma demanda vinculada ao MR !{mr_iid}',
            'context': {'mr_iid': mr_iid},
        }
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'mr_iid': mr_iid}}
    return 200, demanda


@get(
    router,
    '{id}/ambiente-homologacao/',
    response={200: AmbienteHomologacaoSchema, 403: ErrorSchema, 404: ErrorSchema},
    summary='Ambiente de homologação da demanda',
    description=(
        'Estado do ambiente da entrega atual da demanda: branch, banco, validade, pipeline e situação do job de deploy, '
        'consultada no GitLab na hora. Não devolve a senha do ambiente.'
    ),
)
def ambiente_homologacao(request: HttpRequest, id: int) -> tuple[int, AmbienteHomologacao | dict]:
    try:
        demanda = Demanda.objects.get(pk=id)
    except Demanda.DoesNotExist:
        return 404, {**_NOT_FOUND, 'context': {'demanda_id': id}}
    if not demanda.permite_visualizar(request.user):
        return 403, {**_PERMISSION_DENIED, 'context': {'demanda_id': id}}
    # O ambiente vive na entrega: o da entrega pendente ou, sem ela, o da mais recente que tenha um.
    ambiente = demanda.ambiente_homologacao_atual
    if ambiente is None:
        return 404, _erro('ambiente_not_found', 'A demanda não tem ambiente de homologação vinculado', demanda_id=id)
    ambiente.demanda_id = demanda.pk
    return 200, ambiente
