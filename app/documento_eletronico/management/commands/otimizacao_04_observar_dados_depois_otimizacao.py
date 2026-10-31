import os

from djtools.management.commands import BaseCommandPlus

from .otimizacao_01_observar_dados_antes_otimizacao import Command as Command01


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        command = Command01()
        command.estagio_consulta = 'DEPOIS'
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        command.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

        command.handle(*args, **options)
