"""
Comando para gerar bolsas na aplicação AE
"""

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import Avaliacao, Edital


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        :param args: lista de ids de editais
        :param options:
        :return:
        """
        print('NORMALIZANDO EDITAIS ...')
        editais_ids = (16, 17, 18, 20)
        editais = Edital.objects.filter(id__in=editais_ids)

        for edital in editais:
            print(f'Normalizando avaliações do edital {edital.titulo} ...')
            avaliacoes = Avaliacao.objects.filter(projeto__edital=edital)
            for avaliacao in avaliacoes:
                avaliacao.save()

        for edital in editais:
            print(f'Atualizano pontuação do currículo lattes do edital {edital.titulo} ...')
            for projeto in edital.projeto_set.all():
                projeto.atualizar_pontuacao_curriculo_lattes(maior_pontuacao_curriculo=0)

        for edital in editais:
            print(f'Normalizando projetos do edital {edital.titulo} ...')
            edital.normalizar_pontuacao_curriculo_lattes()
