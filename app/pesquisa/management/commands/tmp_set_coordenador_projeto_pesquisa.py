"""
Comando para atualizar a coluna coordenador do modelo Projeto
"""

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import Participacao, Projeto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        contador = 0
        for projeto in Projeto.objects.all():
            if Participacao.objects.filter(projeto=projeto, responsavel=True).exists() and (
                Participacao.objects.filter(projeto=projeto, responsavel=True)[0].vinculo_pessoa != projeto.vinculo_coordenador
            ):
                coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True)[0]
                projeto.coordenador = coordenador.pessoa
                projeto.vinculo_coordenador = coordenador.vinculo_pessoa
                projeto.save()
                contador += 1
