import time
from itertools import chain

import tqdm
from django.contrib.admin.utils import NestedObjects
from django.core import serializers

from comum.models import User
from djtools.management.commands import BaseCommandPlus


def flatten(elem):
    if isinstance(elem, list):
        return chain.from_iterable(list(map(flatten, elem)))
    return (elem,)


class Command(BaseCommandPlus):
    help = 'Limpa todas os usuários sem nenhum relacionamento'

    def dump(self, collector):
        lista = []

        self.stdout.write('Copiando usuarios')
        for instances in tqdm.tqdm(collector.data.values()):
            for instance in instances:
                if instance.__class__.__name__ not in ['Log', 'RegistroDiferenca'] and instance not in lista:
                    lista.append(instance)
        self.stdout.write('Copiando relacionamentos')
        for qs in tqdm.tqdm(collector.fast_deletes):
            for instance in qs:
                if instance.__class__.__name__ not in ['Log', 'RegistroDiferenca'] and instance not in lista:
                    lista.append(instance)
        return lista

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true', help='Executa a exclusão das pks?', default=False)
        parser.add_argument('--backup', action='store_true', help='Realizar backup?', default=False)

    def handle(self, *args, **options):
        delete = options.get('delete')
        backup = options.get('backup')
        tipos_ignorados = [
            'django.contrib.admin.models.LogEntry',
            'comum.models.User_user_permissions',
            'comum.models.User_groups',
            'comum.models.UsuarioGrupo',
            'edu.models.comunicador.Mensagem_destinatarios',
            'comum.models.IndexLayout',
            'comum.models.SessionInfo',
            'comum.models.Device',
            'social_django.models.UserSocialAuth',
            'comum.models.Preferencia',
        ]
        qs = User.objects.filter(
            vinculo__isnull=True, vinculo__pessoa__isnull=True, is_superuser=False, respondente__isnull=True, is_staff=False
        ).order_by('id')

        collector = NestedObjects('default')
        self.stdout.write('Iniciando coleta de usuários')
        start = time.perf_counter()
        collector.collect(qs)
        stop = time.perf_counter()
        self.stdout.write(f'Finalizando coleta de usuários: {stop - start}')

        if backup:
            self.stdout.write('Realizando backup')
            lista = self.dump(collector)
            f = open('backup.json', 'w')
            f.write(serializers.serialize('json', lista))
            f.close()

        self.stdout.write('Backup realizado')
        self.stdout.write('Verificando relacionamentos')

        pks = list(qs.values_list('pk', flat=True))

        for user in qs:
            for rel in collector.edges.get(user, []):
                klass = f'{rel.__module__}.{rel.__class__.__name__}'
                if str(klass) not in tipos_ignorados:
                    self.stdout.write(f'{klass} {user}')
                    pks.remove(user.pk)
                    break

        self.stdout.write(f'{len(pks)} usuários com os seguintes pks serão removidos:')
        self.stdout.write(f'{pks}')
        if delete:
            for user in tqdm.tqdm(User.objects.filter(pk__in=pks)):
                user.delete()
