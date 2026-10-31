from datetime import datetime


from djtools.management.commands import BaseCommandPlus
from ldap_backend.models import LdapConf


class Command(BaseCommandPlus):
    # Esse comando vai fazer uma consulta no LDAP de todos os usuários que tenham o attributo accountExpires diferente de None
    # e que estejam com o atributo accountExpires menor que a data atual.
    # Esses usuários serão considerados expirados e serão atualizados no banco de dados.
    help = 'Sincroniza usuários expirados do LDAP'

    def handle(self, *args, **options):
        conf = LdapConf.get_active()
        now = datetime.now()
        # Converter data atual para FileTime (AD): número de 100-nanosegundos desde 1601-01-01
        filetime_now = int((now - datetime(1601, 1, 1)).total_seconds() * 10**7)
        ldap_users = conf.search_users_by_account_expires(min_expires=0, max_expires=filetime_now)

        expired_users = []
        expired_users_errors = []
        for user in ldap_users:
            username_field = user.get(conf.filterstr_prefix.replace('=', ''), [b''])[0]
            try:
                conf.sync_user(username_field.decode())
                expired_users.append(username_field.decode())
            except Exception:
                self.stdout.write(f'Erro ao sincronizar usuário {username_field.decode()}. Verifique o log para mais detalhes.')
                expired_users_errors.append(username_field.decode())
                continue

        self.stdout.write(f'{len(expired_users)} usuários expirados no LDAP.')
        self.stdout.write(f'{len(expired_users_errors)} usuários expirados com erro de sincronização.')
