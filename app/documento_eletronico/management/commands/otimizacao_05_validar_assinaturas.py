import os

from djtools.management.commands import BaseCommandPlus

from .validar_corrigir_assinaturas import Command as CommandValidarAssinaturas


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        command_validar_assinaturas = CommandValidarAssinaturas()
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        command_validar_assinaturas.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'
        options['executar_command'] = True
        options['corrigir_assinaturas_invalidas'] = False
        command_validar_assinaturas.handle(*args, **options)
