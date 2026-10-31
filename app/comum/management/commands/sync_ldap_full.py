from django.core.management import call_command

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        commands = []
        commands.append('sync_ldap_ous')
        commands.append('sync_ldap_alunos')
        commands.append('sync_ldap_servidores')
        commands.append('sync_ldap_prestadores')
        commands.append('prevent_login_with_modelbackend')

        for command in commands:
            call_command(command, interactive=False, raise_exception=False)
