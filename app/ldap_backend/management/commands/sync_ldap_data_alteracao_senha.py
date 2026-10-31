import tqdm

from comum.models import User
from djtools.management.commands import BaseCommandPlus
from ldap_backend.models import LdapConf
from ldap_backend.utils import ad_to_datetime


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)

    def handle(self, *args, **options):
        conf = LdapConf.get_active()
        for user in tqdm.tqdm(User.objects.all()):
            dn = conf.get_user(user.username, attrs=['pwdLastSet'])
            if dn:
                pwd_last_set = dn['pwdLastSet'][0].decode()
                pwd_date = ad_to_datetime(pwd_last_set)
                user.data_ultima_alteracao_senha = pwd_date
                user.save()
