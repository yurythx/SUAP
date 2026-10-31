import datetime

from djtools.management.commands import BaseCommandPlus
from djtools.models import Task


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        tasks_antigas = Task.objects.filter(start__lt=datetime.datetime.now() - datetime.timedelta(days=1))
        sem_usuarios = tasks_antigas.filter(user__isnull=True)
        self.stdout.write(f'>>> Limpando {sem_usuarios.count()} tarefas sem usuários.', style_func=self.style.SUCCESS)
        self.stdout.flush()
        sem_usuarios.delete()
        nao_finalizadas = tasks_antigas.filter(end__isnull=True)
        self.stdout.write(f'>>> Finalizando {nao_finalizadas.count()} tarefas antigas.', style_func=self.style.SUCCESS)
        self.stdout.flush()
        nao_finalizadas.update(
            end=datetime.datetime.today(), error='Tempo de execução superior a 1 dia.', message='Tempo de execução superior a 1 dia.'
        )
