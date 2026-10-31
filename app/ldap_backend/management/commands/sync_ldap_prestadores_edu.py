from django.apps import apps
from sentry_sdk import capture_exception

from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        Professor = apps.get_model('edu', 'Professor')
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhuma configuração LDAP ativa encontrada.')
        for professor in Professor.nao_servidores.all():
            try:
                conf.sync_user(professor.vinculo.user.username)
            except Exception as e:
                capture_exception(e)
