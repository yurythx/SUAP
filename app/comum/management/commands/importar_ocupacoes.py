import csv

from comum.models import Ocupacao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        with open('comum/fixtures/cbo2002.csv', encoding='windows-1252') as csvfile:
            objs = csv.reader(csvfile, delimiter=';')
            for row in objs:
                ocupacao = Ocupacao.objects.filter(codigo=row[0]).first()
                if ocupacao:
                    self.stdout.write(f'Ocupação "{row[0]}" atualizou descrição de "{ocupacao.descricao}" para "{row[1]}"')
                    ocupacao.descricao = row[1]
                    ocupacao.save()
                else:
                    ocupacao, created = Ocupacao.objects.get_or_create(codigo=row[0], descricao=row[1])
                    if created:
                        self.stdout.write(f'Ocupação "{ocupacao}" criada.')
                    else:
                        self.stdout.write(f'Ocupação "{ocupacao}" já existe.')
