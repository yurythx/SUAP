from django.contrib.auth.hashers import get_hasher, make_password

from comum.models import User
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('raw_password', type=str)
        parser.add_argument('usernames', type=str, nargs='?', default=None)

    def handle(self, *args, **options):
        hasher = get_hasher()
        raw_password = options['raw_password']
        password = make_password(raw_password, '', hasher)
        usernames = options['usernames']
        users = User.objects.all()
        if usernames:
            users = users.filter(username__in=usernames.split(','))
        result = self.style.SQL_COLTYPE(f'{users.update(password=password)} passwords changed to "{raw_password}"')
        self.stdout.write(f'{result}\n')
        try:
            text_file = open('deploy/random_password.txt', 'w')
            text_file.write(str(raw_password))
            text_file.close()
        except Exception:
            self.stdout.write("Can't save the output on filesystem.\n")
