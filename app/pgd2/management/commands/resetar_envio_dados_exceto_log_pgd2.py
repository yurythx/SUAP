from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.api_pgd2 import resetar_envio_dados_exceto_log

        resetar_envio_dados_exceto_log()
