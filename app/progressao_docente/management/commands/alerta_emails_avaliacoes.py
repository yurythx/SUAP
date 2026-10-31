from djtools.management.commands import BaseCommandPlus
from progressao_docente.models import ProgressaoDocente


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Alertando responsáveis via e-mail ...')
        for progressao in ProgressaoDocente.objects.exclude(situacao=ProgressaoDocente.FINALIZADO):
            progressao.enviar_email_alerta()
        print('Alertas finalizados.')
