from datetime import datetime

from terminais.models import Deployment, DeploymentStatus


class DeploymentService:
    @staticmethod
    def check_deploy():
        deployment = Deployment.objects.filter(
            started_at__lte=datetime.now(),
            status__in=[
                DeploymentStatus.PENDING,
                DeploymentStatus.IN_PROGRESS,
            ],
        )

        return deployment.first()

    @staticmethod
    def criar_deployment(release, dispositivo):
        deployment = release.deployments.create(status=DeploymentStatus.IN_PROGRESS)
        return deployment

    @staticmethod
    def dispositivos_para_atualizar(deployment):
        dispositivos = deployment.dispositivo_set.filter(
            maquina__ativo=True,
        )

        total = dispositivos.count()

        allowed = int(total * deployment.rollout_percentage / 100)
        eligible_devices = list(dispositivos.order_by('id')[:allowed])

        return eligible_devices

    @staticmethod
    def get_deployment_ativo():
        return Deployment.objects.filter(status=DeploymentStatus.IN_PROGRESS).order_by('-started_at').first()

    @staticmethod
    def get_deployment(id):
        return Deployment.objects.get(id=id)
