"""
Comando que deve ser executado após atualizar os fontes do SUAP.
"""

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus

Log = apps.get_model('comum', 'log')


def print_and_call_command(command, *args, **kwargs):
    kwargs.setdefault('interactive', False)
    print(
        termcolors.make_style(fg='cyan', opts=('bold',))(
            '>>> {} {}{}'.format(command, ' '.join(args), ' '.join([f'{k}={v}' for k, v in list(kwargs.items())]))
        )
    )
    call_command(command, *args, **kwargs)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        if hasattr(settings, 'USE_REDIS') and settings.USE_REDIS:
            print(termcolors.make_style(fg='cyan', opts=('bold',))('>>> Limpando sessões e cache.'))
            cache.clear()
