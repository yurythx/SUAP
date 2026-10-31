"""Endpoints ninja para o lançamento de execuções (RIT) do PGD via GitLab."""

from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router

from api.schemas.pgd2 import EntregasDisponiveisOutput, HorasPitOutput, LancarRitInput, RitDoMrOutput, RitLancadoOutput
from djtools.ninja.auth import TrustedAppAuth
from djtools.ninja.router import get, post
from pgd2 import services
from pgd2.models import PlanoIndividualTrabalhoEntregas, RelatorioIndividualTrabalho

router = Router(tags=['PGD2'])
router.api_url_prefix = 'pgd2'


@get(
    router,
    'execucao-gitlab/entregas-disponiveis/',
    auth=TrustedAppAuth(),
    response=EntregasDisponiveisOutput,
    summary='Lista entregas do PIT em que o servidor pode lançar RIT',
)
def entregas_disponiveis(request: HttpRequest, gitlab_username: str) -> dict[str, Any] | tuple[int, dict[str, Any]]:
    """Lista as entregas do PIT em que o servidor (resolvido pelo username GitLab) pode lançar RIT.

    Args:
        request: requisição HTTP.
        gitlab_username: username do autor no GitLab.

    Returns:
        Dicionário com a chave ``entregas`` (lista de entregas disponíveis), ou ``(404, ...)``
        quando o username não está vinculado a nenhum servidor.
    """
    from pgd2.models import PeriodoPitRit

    try:
        servidor = services.resolver_servidor_por_gitlab_username(gitlab_username)
    except ValueError as erro:
        return 404, {'message': str(erro)}

    periodo_corrente = PeriodoPitRit.get_periodo_pit_atual()
    entregas = services.get_entregas_disponiveis_para_servidor(servidor)
    resultado = []
    for e in entregas:
        pes = e.entrega_pes  # pode ser None
        resultado.append(
            {
                'id': e.id,
                'titulo': e.titulo,
                'descricao': e.descricao or '',
                'pit_id': e.pit_id,
                'pes_titulo': pes.titulo if pes else None,
                'pes_descricao': pes.descricao if pes else None,
                'pes_criterios_avaliacao': pes.criterios_avaliacao if pes else None,
                'metrica': pes.metrica if pes else None,
                'meta': pes.meta if pes else None,
                'periodo_titulo': e.pit.periodo_pit_rit.titulo,
                'pit_data_inicio': e.pit.data_inicio,
                'pit_data_fim': e.pit.data_fim,
                'eh_periodo_corrente': bool(periodo_corrente and e.pit.periodo_pit_rit_id == periodo_corrente.id),
            }
        )
    return {'entregas': resultado}


@post(
    router,
    'execucao-gitlab/lancar-rit/',
    auth=TrustedAppAuth(),
    response=RitLancadoOutput,
    summary='Cria/atualiza o RIT (em EM_CADASTRO_RIT) a partir de um MR, ou cria um RIT sem MR',
)
def lancar_rit(request: HttpRequest, payload: LancarRitInput) -> dict[str, Any] | tuple[int, dict[str, Any]]:
    """Cria/atualiza o RIT a partir de um MR do GitLab, de forma idempotente por ``(projeto, MR)``.

    Sem ``gitlab_mr_iid`` (deploy, investigação sem MR), cada chamada cria um RIT novo.

    Args:
        request: requisição HTTP.
        payload: dados do RIT e da proveniência GitLab.

    Returns:
        Dicionário com ``rit_id``, ``entrega_pit_id``, ``gitlab_mr_iid`` e ``criado``; ou
        ``(404, ...)`` se o username não resolve em servidor, ou ``(403, ...)`` se a entrega
        não pertence ao servidor ou o PGD nega o cadastro do RIT.
    """
    entrega_pit = get_object_or_404(PlanoIndividualTrabalhoEntregas, pk=payload.entrega_pit_id)
    try:
        servidor = services.resolver_servidor_por_gitlab_username(payload.gitlab_username)
    except ValueError as erro:
        return 404, {'message': str(erro)}

    if entrega_pit.pit.adesao.servidor_id != servidor.id:
        return 403, {'message': 'A entrega não pertence ao servidor informado.'}

    # sem MR o service sempre cria; filtrar por None casaria com os RITs lançados à mão
    ja_existia = (
        payload.gitlab_mr_iid is not None
        and RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=payload.gitlab_project_id, gitlab_mr_iid=payload.gitlab_mr_iid).exists()
    )

    dados = dict(  # noqa: C408
        titulo=payload.titulo,
        descricao=payload.descricao,
        tempo_executado=payload.tempo_executado,
        perc_executada_em_teletrabalho=payload.perc_executada_em_teletrabalho,
        data_inicio=payload.data_inicio,
        data_fim=payload.data_fim,
        quantidade_progresso=payload.quantidade_progresso,
    )
    try:
        rit = services.lancar_rit_via_gitlab(
            entrega_pit,
            dados,
            gitlab_project_id=payload.gitlab_project_id,
            gitlab_mr_iid=payload.gitlab_mr_iid,
            request=request,
        )
    except PermissionDenied as erro:
        return 403, {'message': str(erro)}

    return {'rit_id': rit.id, 'entrega_pit_id': rit.entrega_pit_id, 'gitlab_mr_iid': rit.gitlab_mr_iid, 'criado': not ja_existia}


@get(
    router,
    'execucao-gitlab/rit-do-mr/',
    auth=TrustedAppAuth(),
    response=RitDoMrOutput,
    summary='Informa o RIT lançado para um MR (status da execução)',
)
def rit_do_mr(request: HttpRequest, gitlab_project_id: int, gitlab_mr_iid: int) -> dict[str, Any] | tuple[int, dict[str, Any]]:
    """Retorna o RIT lançado para o MR ``(gitlab_project_id, gitlab_mr_iid)``.

    Usado pelo comentário de confirmação no merge para informar a execução registrada.

    Args:
        request: requisição HTTP.
        gitlab_project_id: ID do projeto no GitLab.
        gitlab_mr_iid: IID do merge request no GitLab.

    Returns:
        Dicionário com ``rit_id``, ``situacao_rit`` (situação do RIT do PIT), ``entrega_titulo``
        e ``tempo_executado``; ou ``(404, ...)`` quando não há RIT para o MR.
    """
    rit = RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=gitlab_project_id, gitlab_mr_iid=gitlab_mr_iid).first()
    if rit is None:
        return 404, {'message': 'Nenhum RIT para este MR.'}
    return {
        'rit_id': rit.id,
        'situacao_rit': rit.entrega_pit.pit.situacao_rit,
        'entrega_titulo': rit.entrega_pit.titulo,
        'tempo_executado': rit.tempo_executado,
    }


@get(
    router,
    'execucao-gitlab/horas-pit/',
    auth=TrustedAppAuth(),
    response=HorasPitOutput,
    summary='Informa, por PIT aberto a RIT, a CH prevista, as horas já lançadas, o que falta e o % de teletrabalho',
)
def horas_pit(request: HttpRequest, gitlab_username: str) -> dict[str, Any] | tuple[int, dict[str, Any]]:
    """Informa as horas dos PITs do servidor que ainda aceitam RIT.

    Os valores são os mesmos da tela do PIT (``tempo_previsto`` e ``tempo_executado_total``),
    que o PGD recalcula a cada RIT lançado.

    Args:
        request: requisição HTTP.
        gitlab_username: username do servidor no GitLab.

    Returns:
        Dicionário com a chave ``pits``, ou ``(404, ...)`` quando o username não está
        vinculado a nenhum servidor.
    """
    from pgd2.models import PeriodoPitRit

    try:
        servidor = services.resolver_servidor_por_gitlab_username(gitlab_username)
    except ValueError as erro:
        return 404, {'message': str(erro)}

    periodo_corrente = PeriodoPitRit.get_periodo_pit_atual()
    pits = []
    for pit in services.get_pits_abertos_para_rit(servidor):
        previsto = pit.tempo_previsto or Decimal(0)
        executado = pit.tempo_executado_total or Decimal(0)
        pits.append(
            {
                'pit_id': pit.id,
                'periodo_titulo': pit.periodo_pit_rit.titulo,
                'pit_data_inicio': pit.data_inicio,
                'pit_data_fim': pit.data_fim,
                'eh_periodo_corrente': bool(periodo_corrente and pit.periodo_pit_rit_id == periodo_corrente.id),
                'tempo_previsto': previsto,
                'tempo_executado_total': executado,
                'tempo_restante': max(previsto - executado, Decimal(0)),
                'percentual_teletrabalho': pit.percentual_teletrabalho or Decimal(0),
            }
        )
    return {'pits': pits}
