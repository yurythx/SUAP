from djtools.management.commands import BaseCommandPlus
from ponto.models import RecessoOpcaoEscolhida

"""
    Compensações em Acompanhamento / Recessos Escolhidos
    Remover Recessos Escolhidos Específicos
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        ids_a_excluir = [3842]  # chamado #82954 - Recesso Escolhido por Geraldo Lucas Bezerra Rocha (2424497), que foi desligado.
        RecessoOpcaoEscolhida.objects.filter(id__in=ids_a_excluir).delete()
