"""
Comando que deve ser executado antes de realizar o commit no repositório do SUAP.
"""

import os

from django.conf import settings
from django.core.management.commands.test import Command as TestCommand
from django.utils import termcolors

os.environ['USUARIOGRUPO_AS_ABSTRACT'] = '1'


class Command(TestCommand):
    help = 'Executa os testes do SUAP'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--nowarning', action='store_true', default=False, help='Desativa apenas os avisos na verificações de qualidade de código.'
        )
        parser.add_argument('--initialize-dev-db', action='store_true', default=False, help='Cria banco de dados de desenvolvimento (suap_dev)')

    def get_available_apps(self):
        return sorted(settings.INSTALLED_APPS_SUAP)

    def handle(self, *args, **options):
        apps = args or self.get_available_apps()

        self.stdout.write(termcolors.make_style(fg='green', opts=('bold',))('>>> test {} ...\n'.format(' '.join(apps))))

        # call_command('test',  *apps, **options)
        super().handle(*apps, **options)
