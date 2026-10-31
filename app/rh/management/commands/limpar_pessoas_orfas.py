import os
from os.path import join

from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from djtools.utils import can_hard_delete, can_hard_delete_fast
from rh.models import PessoaFisica


class Command(BaseCommandPlus):
    help = 'Limpa todas as pessoas sem nenhum relacionamento'

    def handle(self, *args, **options):
        path = join(settings.BASE_DIR, 'deploy/static/')
        with open(join(path, 'orfaos.txt'), 'a+') as f_orfaos, open(join(path, 'relacionados.txt'), 'a+') as f_relacionados:
            f_relacionados.seek(0, os.SEEK_SET)
            relacionados = [x.strip() for x in f_relacionados]
            f_orfaos.seek(0, os.SEEK_SET)
            [x.strip() for x in f_orfaos]
            for pessoa in PessoaFisica.objects.filter(vinculo__user__isnull=True).order_by('id'):
                chave = str(pessoa.pk)
                if chave not in relacionados:
                    if can_hard_delete_fast(pessoa):
                        if hasattr(pessoa, 'user'):
                            if can_hard_delete(pessoa.user):
                                print(('apagando pessoa #', pessoa.pk))
                                f_orfaos.write(chave + '\n')
                                f_orfaos.flush()
                                pessoa.delete()
                        else:
                            print(('apagando pessoa #', pessoa.pk))
                            f_orfaos.write(chave + '\n')
                            f_orfaos.flush()
                            pessoa.delete()
                    else:
                        f_relacionados.write(chave + '\n')
                        f_relacionados.flush()
