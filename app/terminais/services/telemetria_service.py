from terminais.models import Deployment, Dispositivo


class TelemetriaService:
    @staticmethod
    def registrar_heartbeat(dispositivo_id, versao, ip, uptime):
        dispositivo = Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()

        if not dispositivo:
            raise ValueError(f'Dispositivo com ID {dispositivo_id} não encontrado.')

        return dispositivo.registrar_heartbeat(versao=versao, ip=ip, uptime=uptime)

    @staticmethod
    def registrar_report_update(report_update):
        deploy_id = report_update['deploy_id']
        dispositivo_id = report_update['device_id']

        deployment = Deployment.objects.filter(id=deploy_id).first()

        if not deployment:
            raise ValueError(f'Deploy com ID {deploy_id} não encontrado.')

        dispositivo = Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()

        if not dispositivo:
            raise ValueError(f'Dispositivo com ID {dispositivo_id} não encontrado.')

        return deployment.registrar_report_update(
            dispositivo=dispositivo,
            version=report_update['version'],
            status=report_update['status'],
        )
