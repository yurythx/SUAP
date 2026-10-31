from datetime import date, timedelta

from django.apps import apps

from djtools.management.commands import BaseCommandPlus

User = apps.get_model('comum', 'User')


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        # Sincroniza os usuários que não fizeram o login de ontem para hoje
        ontem = date.today() - timedelta(1)
        for user in User.objects.filter(last_login__lt=ontem):
            user.save()
