import os

from django.conf import settings
from django.db import transaction

from arquivo.models import Processo, TipoArquivo
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        arquivo = os.path.join(settings.BASE_DIR, 'arquivo/static/arquivo/tipo_arquivo.txt')
        with open(arquivo) as txt_file:
            for linha in txt_file:
                tipo_str, _, proc_str = linha.partition('&&')
                tipo_str = tipo_str.strip()
                proc_str = proc_str.strip()
                if not (tipo_str and proc_str):
                    continue

                if ':' in proc_str:
                    superior_desc, _, processo_desc = proc_str.partition(':')
                    processo_superior, _ = Processo.objects.get_or_create(descricao=superior_desc.strip())
                    processo, _ = Processo.objects.get_or_create(descricao=processo_desc.strip())
                    if processo.superior_id != processo_superior.pk:
                        processo.superior = processo_superior
                        processo.save()
                else:
                    processo, _ = Processo.objects.get_or_create(descricao=proc_str)

                tipo_arquivo, _ = TipoArquivo.objects.get_or_create(descricao=tipo_str)
                processo.tipos_arquivos.add(tipo_arquivo)
