from djtools.management.commands import BaseCommandPlus
from progressoes.models import ProcessoProgressao


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('-s', '--save', action='store_true', help='Salvar processo.')
        parser.add_argument('-a', '--alert', action='store_true', help='Alertar responsáveis pelos novos processos.')

    def handle(self, *args, **options):
        print('Calculando servidores a progredir ...')
        save = options.get('save')
        alert = options.get('alert')
        novos_processos = ProcessoProgressao.calcular_servidores_a_progredir(salvar_processos=save)
        if alert:
            ProcessoProgressao.alertar_responsaveis_processos()
        print('--------')
        print(f'{len(novos_processos)} novo(s) processo(s) identificado(s).')
