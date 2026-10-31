from djtools.management.commands import BaseCommandPlus
from progressao_docente.models import DocenteAProgredir, ProgressaoDocente


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('-s', '--save', action='store_true', help='Salvar processo.')
        parser.add_argument('-a', '--alert', action='store_true', help='Alertar responsáveis pelos novos processos.')

    def handle(self, *args, **options):
        self.stdout.write('Calculando docentes a progredir ...')
        # alert = options.get("alert")
        removidos = DocenteAProgredir.remover_pendentes_fora_do_quadro()
        self.stdout.write(f'Linhas removidas de docentes fora do quadro: {removidos}')
        ProgressaoDocente.calcular_docentes_a_progredir()
        # if alert:
        #     ProcessoProgressao.alertar_responsaveis_processos()
        self.stdout.write('--------')
        self.stdout.write('Relação de docentes a progredir atualizada.')
