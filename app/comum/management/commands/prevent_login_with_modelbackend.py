from comum.models import User
from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf


class Command(BaseCommandPlus):
    help = 'Impede que usuários autentiquem com django.contrib.auth.backends.ModelBackend, deixando a senha como um hash inatingível: "!".'

    def handle(self, *args, **options):
        conf = get_ldap_conf()
        if conf:
            User.objects.exclude(eh_estrangeiro=True).update(password='!', skip_history=True)
            self.stdout.write(self.style.SQL_COLTYPE(f'{User.objects.count()} password hashes changed to "!"'))
        else:
            self.stdout.write('Nenhuma configuração do LDAP ativa.')
