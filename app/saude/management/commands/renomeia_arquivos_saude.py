import os
import uuid

from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from saude.models import AnexoPsicologia


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for item in AnexoPsicologia.objects.all().order_by('id'):
            try:
                gera_string = str(uuid.uuid4())
                extensao = item.arquivo.url.split('.')
                if len(extensao) > 1:
                    extensao = extensao[len(extensao) - 1]
                    novo_nome = gera_string + '.' + extensao
                else:
                    novo_nome = gera_string

                caminho_relativo = 'upload/saude/psicologia/anexos/' + novo_nome
                caminho = settings.MEDIA_ROOT + '/' + caminho_relativo
                os.rename(item.arquivo.path, caminho)
                item.arquivo.name = caminho_relativo
                item.save()
            except Exception:
                pass
