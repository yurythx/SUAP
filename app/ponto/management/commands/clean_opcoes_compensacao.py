from djtools.management.commands import BaseCommandPlus
from ponto.models import RecessoOpcao

""" Remove opções de compensações específicas fechadas, impositivas e
    "sem filhos", ou seja, sem que nenhum servidor tenha
    escolhido a opção ou a ele tenha sido atribuída.

    Provavelmente são registros que estão no "limbo" e sem utilidade.
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for opcao in RecessoOpcao.objects.filter(situacao=RecessoOpcao.SITUACAO_FECHADO).exclude(tipo=RecessoOpcao.TIPO_PERMITE_ESCOLHA_LIVRE):
            confirma_eh_fechada = opcao.situacao == RecessoOpcao.SITUACAO_FECHADO
            confirma_eh_impositiva = not opcao.is_permite_escolha_pelos_servidores
            ha_escolhas = opcao.get_dias_escolhidos().exists() or opcao.get_periodos_escolhidos().exists()
            if confirma_eh_fechada and confirma_eh_impositiva and not ha_escolhas:
                print(f'Excluindo ... {opcao}')
                opcao.delete()
