from ninja import Router

from api.schemas.terminais import (
    CheckResponseSchema,
    DeployDispositivosResponseSchema,
    DispositivoRegistroSchema,
    HeartbeatSchema,
    RegistrarResponseSchema,
    StatusResponseSchema,
    UpdateReportSchema,
)
from djtools.ninja.auth import TrustedAppAuth
from djtools.ninja.router import get, post
from terminais.services import DeploymentService, DispositivoService, TelemetriaService, UpdateService
from terminais.services.release_service import ReleaseService

router = Router(tags=['Terminais'])
router.api_url_prefix = 'terminais'


type BatchHeartbeatResponse = dict[int, bool]
type BatchUpdateReportResponse = dict[int, bool]


@post(
    router,
    'registrar/',
    auth=TrustedAppAuth(),
    response=RegistrarResponseSchema,
    summary='Registra um dispositivo',
    description='Realiza o registro de um novo dispositivo.',
)
def registrar_dispositivo(request, payload: DispositivoRegistroSchema):
    """
    Registra um dispositivo.

    Args:
        request: Objeto de requisição HTTP.
        payload: Dados para registrar o dispositivo.

    Returns:
        Dispositivo: Objeto do dispositivo registrado.
    """
    dispositivo = DispositivoService.registrar_dispositivo(
        dispositivo_id=payload.dispositivo_id,
        ip_maquina=payload.ip_maquina,
    )

    return {
        'dispositivo_id': dispositivo.dispositivo_id,
        'registered': True,
    }


@post(
    router,
    'heartbeat/',
    auth=TrustedAppAuth(),
    response=StatusResponseSchema,
    summary='Registrar heartbeat de um dispositivo',
    description='Registra o heartbeat de um dispositivo.',
)
def heartbeat(request, payload: HeartbeatSchema):
    """
    Registra o heartbeat de um dispositivo.

    Args:
        request: Objeto de requisição HTTP.
        payload: Dados de heartbeat do dispositivo.

    Returns:
        StatusResponseSchema: Objeto com status 'ok'.
    """
    TelemetriaService.registrar_heartbeat(
        dispositivo_id=payload.device_id,
        versao=payload.version,
        ip=payload.ip,
        uptime=payload.uptime,
    )

    return {
        'status': 'ok',
    }


@post(
    router,
    'batch-heartbeat/',
    auth=TrustedAppAuth(),
    response=BatchHeartbeatResponse,
    summary='Registrar heartbeat em lote de dispositivos',
    description='Registra heartbeat em lote de dispositivos.',
)
def batch_heartbeat(request, payload: list[HeartbeatSchema]):
    """
    Registra heartbeat em lote de dispositivos.

    Args:
        request: Objeto de requisição HTTP.
        payload: Lista de dados de heartbeat dos dispositivos.

    Returns:
        StatusResponseSchema: Objeto com status 'ok'.
    """
    result = dict()  # noqa: C408

    for heartbeat in payload:
        try:
            TelemetriaService.registrar_heartbeat(
                dispositivo_id=heartbeat.device_id,
                versao=heartbeat.version,
                ip=heartbeat.ip,
                uptime=heartbeat.uptime,
            )
            result[heartbeat.id] = True
        except ValueError:
            result[heartbeat.id] = False

    return result


@get(
    router,
    'deploy/check/',
    response=CheckResponseSchema,
    # auth=TrustedAppAuth(),
    summary='Verifica a existência de deploys ativos',
    description='Verifica se há deploys disponíveis.',
)
def deploy_check(request) -> CheckResponseSchema:
    """
    Verifica se há deploys disponíveis para um dispositivo.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        CheckResponseSchema: Objeto com status 'ok'.
    """
    deploy = DeploymentService.check_deploy()

    if deploy is None:
        return {
            'update_available': False,
        }

    return {
        'update_available': True,
        'deploy_id': deploy.id,
        'version': deploy.release.versao,
        'artifacts': [
            {
                'component': artefato.componente,
                'url': artefato.url,
                'checksum': artefato.checksum,
            }
            for artefato in deploy.release.artefatos.all()
        ],
    }


@get(
    router,
    'deploy/dispositivos/{deployment_id}',
    response=DeployDispositivosResponseSchema,
    # auth=TrustedAppAuth(),
    summary='Obtém a lista de dispositivos elegíveis',
    description='Com base em um deployment, obtém a lista de dispositivos elegíveis para atualização.',
)
def deploy_dispositivos_get(request, deployment_id: str) -> DeployDispositivosResponseSchema:
    """
    Obtém a lista de dispositivos elegíveis para atualização.

    Args:
        request: Objeto de requisição HTTP.
        deployment_id: ID do deployment.

    Returns:
        DeployDispositivosResponseSchema: Objeto com a lista de dispositivos elegíveis.
    """
    deployment = DeploymentService.get_deployment(deployment_id)

    return {'dispositivos': [dispositivo.dispositivo_id for dispositivo in deployment.dispositivos]}


@post(
    router,
    'report/',
    auth=TrustedAppAuth(),
    response=StatusResponseSchema,
    summary='Registrar relatório de um dispositivo',
    description='Registra o relatório de um dispositivo.',
)
def report_update(request, payload: UpdateReportSchema):
    """
    Registra o relatório de um dispositivo.

    Args:
        request: Objeto de requisição HTTP.
        payload: Dados do relatório de atualização do dispositivo.

    Returns:
        StatusResponseSchema: Objeto com status 'received'.
    """
    dispositivo = DispositivoService.get_dispositivo(payload.device_id)
    release = ReleaseService.get_release(payload.version)

    UpdateService.registrar_relatorio(dispositivo, release, payload.status)

    return {'status': 'received'}


@post(
    router,
    'batch-report/',
    auth=TrustedAppAuth(),
    response=BatchUpdateReportResponse,
    summary='Registrar atualizações em lote de dispositivos',
    description='Registra atualizações em lote de dispositivos.',
)
def batch_report(request, payload: list[UpdateReportSchema]):
    """
    Registra atualizações em lote de dispositivos.

    Args:
        request: Objeto de requisição HTTP.
        payload: Lista de dados de update reports dos dispositivos.

    Returns:
        StatusResponseSchema: Objeto com status 'ok'.
    """
    result = dict()  # noqa: C408

    for update_report in payload:
        try:
            TelemetriaService.registrar_report_update(
                report_update={
                    'deploy_id': update_report.deploy_id,
                    'device_id': update_report.device_id,
                    'version': update_report.version,
                    'status': update_report.status,
                }
            )
            result[update_report.fleet_id] = True
        except ValueError:
            result[update_report.fleet_id] = False

    return result
