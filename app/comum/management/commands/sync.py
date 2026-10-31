"""
Comando que deve ser executado após atualizar os fontes do SUAP.
"""

import os
import sys

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus

Log = apps.get_model('comum', 'log')


def print_and_call_command(command, *args, **kwargs):
    arguments = args and ' '.join(args) + ' ' or ''
    parameters = arguments + ' '.join([f'{k}={v}' for k, v in list(kwargs.items())])
    sys.stdout.write(termcolors.make_style(fg='cyan', opts=('bold',))(f'>>> {command} {parameters}\n'))
    call_command(command, *args, **kwargs)


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        os.system('./bin/clean_pyc.sh')
        print_and_call_command('migrate', interactive=False)
        print_and_call_command('gerar_metadados')
        print_and_call_command('loaddata', 'initial_data', skip_checks=True, ignore=True)
        print_and_call_command('sync_permissions')
        print_and_call_command('collectstatic', verbosity=0, interactive=False)
        print_and_call_command('carregar_apis', verbosity=0)
        Log.objects.create(titulo='Atualização do Sistema', texto='Atualização do SUAP', app='suap')
        cache.delete('data_ultima_atualizacao_suap')
        if 'erros' in settings.INSTALLED_APPS and not settings.DEBUG:
            from comum.utils import ferramentas_configuradas

            if ferramentas_configuradas():
                print_and_call_command('sincronizar_erros')
        if 'demandas' in settings.INSTALLED_APPS and not settings.DEBUG:
            print_and_call_command('sincronizar_demandas')
            print_and_call_command('gitlab_atualiza_mrs')
        if 'beat' in settings.INSTALLED_APPS:
            print_and_call_command('importar_tarefas_celery_beat', verbosity=0)
