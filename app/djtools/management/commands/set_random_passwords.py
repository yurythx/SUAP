from django.contrib.auth.hashers import get_hasher, make_password

from comum.models import User
from djtools.management.commands import BaseCommandPlus
from djtools.utils import randomic


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        hasher = get_hasher()
        raw_password = randomic(10)
        password = make_password(raw_password, '', hasher)
        self.stdout.write(self.style.SQL_COLTYPE(f'{User.objects.update(password=password)} passwords changed to "{raw_password}"'))
        try:
            text_file = open('deploy/random_password.txt', 'w')
            text_file.write(str(raw_password))
            text_file.close()
        except Exception:
            self.stderr.write("Can't save the output on filesystem.")
