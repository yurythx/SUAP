from conectagov_pen.models import TramiteBarramento
from djtools.management.commands import BaseCommandPlus
from processo_eletronico.models import Tramite


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        title = 'Conectagov / barramento - Comando para corrigir ultimo tramite de processos com tramites externos recusados'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR) ').strip().upper()

        if executar_command == 'EXECUTAR':
            executar = True
        elif executar_command == 'SIMULAR':
            executar = False

        corrigir_ultimo_tramite_processo_com_tramites_externos_recusados(executar=executar)
        print('FIM DO PROCESSAMENTO')


def corrigir_ultimo_tramite_processo_com_tramites_externos_recusados(executar=False):
    # Tramites barramento com status pendente de recebimento e que nao possui processo gerado no suap
    tramites_externos_recusados = Tramite.objects.filter(
        tramite_barramento__status=TramiteBarramento.STATUS_RECUSADO, processo__ultimo_tramite__isnull=True
    )
    for tramite in tramites_externos_recusados:
        tramite.processo.ultimo_tramite = tramite
        if executar:
            tramite.processo.save()
            tramite.save()
            print(f'Executado com sucesso, ultimo tramite atualizado para processo {tramite.processo}')
        else:
            print(f'SIMULAÇÃO -  ultimo tramite atualizado para processo {tramite.processo}')
