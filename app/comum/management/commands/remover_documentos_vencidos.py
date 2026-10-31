import datetime

from django.core.files.storage import default_storage

from comum.models import RegistroEmissaoDocumento
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = RegistroEmissaoDocumento.objects.filter(data_validade__lt=datetime.datetime.today()).exclude(documento='')
        for registro in qs:
            if default_storage.exists(registro.documento.name):
                default_storage.delete(registro.documento.name)
                print(f'Arquivo {registro.documento.name} apagado')
            else:
                print(f'Arquivo {registro.documento.name} inexistente')
        qs.update(documento='')
