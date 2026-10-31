from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhuma configuração LDAP ativa encontrada.')
        conf.sync_all_ous(test_mode=False)
