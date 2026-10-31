"""
Comando para normalizar pontuações do curriculo lattes e dos grupos de pesquisa
"""

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import Edital, Projeto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        editais = Edital.objects.em_selecao() | Edital.objects.em_pre_avaliacao()

        for edital in editais:
            if (
                edital.peso_avaliacao_lattes_coordenador
                and Projeto.objects.filter(edital=edital, pre_aprovado=True, pontuacao_curriculo_normalizado=None).exists()
            ):
                edital.normalizar_pontuacao_curriculo_lattes()
            if (
                edital.peso_avaliacao_grupo_pesquisa
                and Projeto.objects.filter(edital=edital, pre_aprovado=True, pontuacao_grupo_pesquisa_normalizado=None).exists()
            ):
                edital.normalizar_pontuacao_grupo_pesquisa()
