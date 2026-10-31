from djtools.management.commands import BaseCommandPlus
from remanejamento.models import ServidorDataInicioExercicioRemocaoInterna


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        title = 'Remove instancias de ServidorDataInicioExercicioRemocaoInterna que a data de início seja igual a cadastrada no SUAP'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR) ').strip().upper()

        if executar_command == 'EXECUTAR':
            executar = True
        elif executar_command == 'SIMULAR':
            executar = False

        remover_ajustes_data_inicio_remocao_interna(executar=executar)
        print('FIM DO PROCESSAMENTO')


def remover_ajustes_data_inicio_remocao_interna(executar=False):
    ajustes_data_inicio_remocao_interna = ServidorDataInicioExercicioRemocaoInterna.objects.all().order_by('servidor__pessoa_fisica__nome')
    if ajustes_data_inicio_remocao_interna.exists():
        print(f'Existem {ajustes_data_inicio_remocao_interna.count()} ajustes de datas de ínício')
        for ajuste_data_inicio in ajustes_data_inicio_remocao_interna:
            servidor = ajuste_data_inicio.servidor
            if ajuste_data_inicio.data_inicio_exercicio == servidor.data_inicio_exercicio_no_cargo:
                print(
                    f'{servidor} - A data ajustada {ajuste_data_inicio.data_inicio_exercicio} é igual a data do cadastro no SUAP {servidor.data_inicio_exercicio_no_cargo}, será REMOVIDA a data ajustada.'
                )
                if executar:
                    ajuste_data_inicio.delete()
                    print(f'Ajuste de data do {servidor} removido.')
            elif ajuste_data_inicio.data_inicio_exercicio != servidor.data_inicio_exercicio_no_cargo:
                print(
                    f'{servidor} - A data ajustada {ajuste_data_inicio.data_inicio_exercicio} é diferente a data do cadastro no SUAP {servidor.data_inicio_exercicio_no_cargo}, será MANTIDA a data ajustada.'
                )

        if not executar:
            print('SIMULAÇÃO - Use a opção EXECUTAR para excluir')
