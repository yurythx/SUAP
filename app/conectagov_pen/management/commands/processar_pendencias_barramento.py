from django.core.mail import mail_admins
from requests.exceptions import RequestException

from conectagov_pen.processa_pendencias import processar_pendencias
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        try:
            processar_pendencias()
        except ConnectionError, RequestException:
            mensagem = 'O servidor do conectagov encontra-se inacessível e não foi possível processar as pendências do barramento.'
            self.stdout.write(f'ATENÇÃO: {mensagem}')
            mail_admins('[SUAP] Barramento', mensagem)
