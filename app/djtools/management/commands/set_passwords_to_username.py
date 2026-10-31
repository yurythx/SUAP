import tqdm

from comum.models import User
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = User.objects.all()
        contador = qs.count()
        for user in tqdm.tqdm(qs):
            user.set_password(user.username)
            user.save()
        print(self.style.SQL_COLTYPE(f'{contador} passwords changed to "username"'))
        self.stdout.write(f'Successfully {contador} passwords changed to username')
