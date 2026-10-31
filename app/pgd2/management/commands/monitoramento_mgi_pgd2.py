from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        from pgd2.monitoramento_mgi import MonitoramentoMGI

        monitoramento = MonitoramentoMGI(self_command=self)
        monitoramento.obter_dados()
