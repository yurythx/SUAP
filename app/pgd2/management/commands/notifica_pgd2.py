from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.notificacoes import enviar_notificacoes_pgd

        enviar_notificacoes_pgd()
