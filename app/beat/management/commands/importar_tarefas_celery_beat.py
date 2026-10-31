import importlib
import logging
import os

from django.conf import settings

from djtools.management.commands import BaseCommandPlus

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def load_tasks(self):
        for module in settings.INSTALLED_APPS:
            if not module.startswith('django.'):
                if os.path.exists(os.path.join(settings.BASE_DIR, f'{module}/beat.py')):
                    try:
                        beat = importlib.import_module(f'{module}.beat')
                        beat.load_tasks_schedule()
                        if self.verbosity > 0:
                            self.stdout.write(f'Tarefas do módulo {module}.beat carregadas com sucesso.\n')
                    except ImportError as e:
                        self.stderr.write(f'Erro ao carregar tarefas do módulo {module}.beat: {e}\n')

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        self.load_tasks()
