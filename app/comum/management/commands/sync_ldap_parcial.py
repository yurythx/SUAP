from django.core.management import call_command

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        call_command('sync_ldap_alunos', alterado_em='2', interactive=False, raise_exception=False)
        call_command('sync_ldap_servidores', alterado_em='2', interactive=False, raise_exception=False)
