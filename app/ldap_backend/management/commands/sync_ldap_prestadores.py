from django.apps import apps
from sentry_sdk import capture_exception

from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        PrestadorServico = apps.get_model('comum', 'PrestadorServico')
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhuma configuração LDAP ativa encontrada.')
        for p in PrestadorServico.objects.usuarios_externos_com_ocupacao():
            try:
                conf.sync_user(p)
            except Exception as e:
                capture_exception(e)
