"""
A classe `BaseCommandPlus` deve ser usada no lugar da
`django.core.management.base.BaseCommand` para que um email seja enviado em
caso de erro na execução do comando.

Nota: Foi feito o uso do handler `django.request` por se tratar de um handler
padrão e não ser necessário criar uma nova entrada em `settings.LOGGING.loggers`.
"""

import sys
from datetime import datetime
from logging import getLogger

from django.core.management.base import BaseCommand, OutputWrapper
from sentry_sdk import capture_exception

logger = getLogger(__name__)


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def format_time(dt):
    """
    Retira a parte não significativa de objetos datetime ou timedelta.
    formato padrão para datetime: 2014-05-13 16:03:26.087286
    formato padrão para timedelta: 0:01:22.473183
    """
    return str(dt).split('.')[0]


class OutputWrapperPlus(OutputWrapper):
    """
    Classe wrapper para stdout e stderr, que verifica verbosidade.
    """

    def __init__(self, out, ending='\n', verbosity=1):
        super().__init__(out, ending)
        self.verbosity = verbosity

    def write(self, msg, *args, **kwargs):
        if self.verbosity > 0:
            super().write(msg, *args, **kwargs)


class BaseCommandPlus(BaseCommand):
    stealth_options = ('interactive', 'raise_exception')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger

    def execute(self, *args, **options):
        x0 = datetime.now()
        command_name = self.__class__.__module__.split('.')[-1]
        verbosity = options.get('verbosity', 1)
        self.stdout = OutputWrapperPlus(options.get('stdout', sys.stdout), verbosity=verbosity)
        self.stderr = OutputWrapperPlus(options.get('stderr', sys.stderr), verbosity=verbosity)
        try:
            self.stdout.write(f'[{x0}] >>> Command {command_name} INICIANDO')
            super().execute(*args, **options)
        except Exception as e:
            capture_exception(e)
            self.stderr.write(f'[{datetime.now()}] >>> Command {command_name} FAILED')
            if options.get('raise_exception', True):
                raise e
        x1 = datetime.now()
        self.stdout.write(f'[{x1}] >>> Command {command_name} OK in {format_time(x1 - x0)}')
