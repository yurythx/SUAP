from django.contrib.auth.models import Group

from comum.models import User
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        group = Group.objects.get(name='Atendente da Central de Serviços')
        users = User.objects.filter(groups__name='Atendente da Central de Serviços', atendentes_set__isnull=True)
        for user in users:
            user.groups.remove(group)
