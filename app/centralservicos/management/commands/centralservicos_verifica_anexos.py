import csv

from centralservicos.models import BaseConhecimentoAnexo, ChamadoAnexo
from djtools.management.commands import BaseCommandPlus

"""
python manage.py centralservicos_verifica_anexos
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        allowed_extensions = ['xlsx', 'xls', 'csv', 'docx', 'doc', 'pdf', 'jpg', 'jpeg', 'png', 'txt']

        with open('chamado.csv', 'w') as base_file:
            wr = csv.writer(base_file, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for obj in ChamadoAnexo.objects.all().order_by('chamado__servico__area'):
                extens = obj.anexo.name.split('.')[-1].lower()
                if extens not in allowed_extensions:
                    wr.writerow([f'{obj.chamado.servico.area};{obj.chamado.id};{obj.chamado.servico.nome};{obj.anexo.name}'])

        with open('base_conhecimento.csv', 'w') as base_file:
            wr = csv.writer(base_file, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for obj in BaseConhecimentoAnexo.objects.all().order_by('base_conhecimento__area'):
                extens = obj.anexo.name.split('.')[-1].lower()
                if extens not in allowed_extensions:
                    wr.writerow([f'{obj.base_conhecimento.area};{obj.base_conhecimento.id};{obj.base_conhecimento.titulo};{obj.anexo.name}'])
