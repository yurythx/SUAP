from djtools.management.commands import BaseCommandPlus
from ponto.models import RecessoOpcaoEscolhida

"""
    Compensações em Acompanhamento / Recessos Escolhidos
    Revalidar Recessos Escolhidos Específicos (cancelar validação atual)
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        ids_a_revalidar = [8360]  # chamado #86232 - Recesso Escolhido por Julianna Azevedo.
        for recesso in RecessoOpcaoEscolhida.objects.filter(id__in=ids_a_revalidar):
            recesso.validacao = RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO
            recesso.motivo_nao_autorizacao = ''
            recesso.save()
