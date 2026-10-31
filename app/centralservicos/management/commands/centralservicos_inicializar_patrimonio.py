import tqdm

from centralservicos.models import Chamado
from patrimonio.models import Inventario
from djtools.management.commands import BaseCommandPlus

"""
python manage.py centralservicos_inicializar_patrimonio
"""


class Command(BaseCommandPlus):
    """
    No contexto da Demanda 1641.
    """

    def handle(self, *args, **options):
        chamados_count = 0
        chamados_save = 0
        chamados_errors = []
        for chamado in tqdm.tqdm(Chamado.objects.filter(numero_patrimonio__isnull=False, patrimonio__isnull=True)):
            try:
                chamado_numero_patrimonio_as_int = int(chamado.numero_patrimonio)
            except Exception:
                chamado_numero_patrimonio_as_int = 0
            if chamado_numero_patrimonio_as_int:
                patrimonio = Inventario.objects.filter(numero=chamado_numero_patrimonio_as_int).first()
                if patrimonio:
                    if patrimonio.numero == chamado_numero_patrimonio_as_int:
                        chamado.patrimonio = patrimonio
                        chamado.save()
                        chamados_save += 1
                    else:
                        chamados_errors.append(
                            f'Chamado {chamado.id}: o número do patrimônio no inventário ({patrimonio.numero}) não coincide com o número de patrimônio do chamado {chamado.numero_patrimonio}.'
                        )
                else:
                    chamados_errors.append(f'Chamado {chamado.id}: patrimônio de número {chamado.numero_patrimonio} não encontrado no inventário.')
            else:
                chamados_errors.append(f'Chamado {chamado.id}: número de patrimônio inválido ({chamado.numero_patrimonio}).')
            chamados_count += 1
        self.stdout.write(f'Total de chamados processados: {chamados_count}')
        self.stdout.write(f'Total de chamados atualizados: {chamados_save} ({(chamados_save / chamados_count * 100) if chamados_count else 0:.2f}%)')
        self.stdout.write(f'Total de chamados com erros: {len(chamados_errors)}')
        for chamado_error in chamados_errors:
            self.stdout.write(f'{chamado_error}')
