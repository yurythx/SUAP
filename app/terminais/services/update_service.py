from terminais.models import UpdateStatus
from terminais.services.deployment_service import DeploymentService


class UpdateService:
    @staticmethod
    def check_updates():
        deployments = DeploymentService.get_deployment_ativo()

        for deployment in deployments:
            release = deployment.release
            artefatos = release.artefatos.all()

            return {
                'update_available': True,
                'version': release.version,
                'artifacts': [
                    {
                        'component': a.componente,
                        'url': a.url,
                        'checksum': a.checksum,
                    }
                    for a in artefatos
                ],
            }

        return {'update_available': False}

    @staticmethod
    def check_update_dispositivo(dispositivo):
        deployments = DeploymentService.get_deployment_ativo()

        for deployment in deployments:
            if not DeploymentService.dispositivos_para_atualizar(dispositivo, deployment):
                continue

            release = deployment.release

            if dispositivo.current_version == release.version:
                continue

            artefatos = release.artefatos.all()

            return {
                'update_available': True,
                'version': release.version,
                'artifacts': [
                    {
                        'component': a.componente,
                        'url': a.url,
                        'checksum': a.checksum,
                    }
                    for a in artefatos
                ],
            }

        return {'update_available': False}

    @staticmethod
    def reportar_update(dispositivo, release, status):
        UpdateStatus.objects.update_or_create(
            device=dispositivo,
            release=release,
            defaults={
                'status': status,
            },
        )
