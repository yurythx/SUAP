"""
Comando para setar o atributo 'coordenador' do projeto
"""

from djtools.management.commands import BaseCommandPlus
from projetos.models import Participacao, Projeto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        contador = 0
        for participacao in Participacao.objects.all():
            if participacao.responsavel and participacao.vinculo_pessoa != participacao.projeto.vinculo_coordenador:
                contador += 1
                Projeto.objects.filter(id=participacao.projeto.id).update(
                    coordenador=participacao.pessoa, vinculo_coordenador=participacao.vinculo_pessoa
                )
        print(f'{contador} coordenadores definidos.')
