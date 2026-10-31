import datetime

from djtools.management.commands import BaseCommandPlus
from djtools.models import EmailEnviadoLog


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        mes_passado = datetime.datetime.now() - datetime.timedelta(days=30)
        emails = EmailEnviadoLog.objects.filter(data__lte=mes_passado)
        contador = emails.count()
        emails.delete()
        print(f'{contador} logs de email excluídos')
