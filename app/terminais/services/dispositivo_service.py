from datetime import datetime

from terminais.models import Dispositivo, DispositivoStatus


class DispositivoService:
    @staticmethod
    def registrar_dispositivo(dispositivo_id, ip_maquina):
        dispositivo = Dispositivo.registrar(dispositivo_id=dispositivo_id, ip_maquina=ip_maquina)
        return dispositivo

    @staticmethod
    def atualizar_last_seen(dispositivo_id):
        dispositivo = Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()

        if dispositivo:
            dispositivo.last_seen = datetime.now()
            dispositivo.status = DispositivoStatus.ONLINE
            dispositivo.save()
            return True

        return False

    @staticmethod
    def atualizar_status(dispositivo_id, status):
        dispositivo = Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()

        if dispositivo:
            dispositivo.status = status
            dispositivo.save()
            return True

        return False

    @staticmethod
    def update_version(dispositivo_id, version):
        dispositivo = Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()

        if dispositivo:
            dispositivo.current_version = version
            dispositivo.save()
            return True

        return False

    @staticmethod
    def get_dispositivo(dispositivo_id):
        return Dispositivo.objects.filter(dispositivo_id=dispositivo_id).first()
