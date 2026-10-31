import sys
from collections import OrderedDict

from django.core import serializers
from django.db import connection
from django.db.transaction import atomic

from djtools.management.commands import BaseCommandPlus


def update_sequence_value(model):
    last_value = model.objects.exists() and model.objects.values_list('pk', flat=True).order_by('-id')[0] or 0
    cursor = connection.cursor()
    cursor.execute(f'select last_value from {model._meta.db_table}_id_seq')
    value = cursor.fetchone()[0]
    if value <= last_value:
        cursor.execute(f'ALTER SEQUENCE {model._meta.db_table}_id_seq RESTART WITH {last_value + 1}')
        print(f'Updating sequence for {model.__name__} to {last_value + 1}')


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('models', nargs='*', type=str)
        parser.add_argument('--add', action='store_true', dest='add', default=())

    @atomic
    def handle(self, models, **options):
        data = OrderedDict()
        lista = []
        for arg in models:
            data[arg] = []
        s = sys.stdin.read()
        for obj in serializers.deserialize('json', s):
            if models:
                if obj.object.__class__.__name__ in data:
                    data[obj.object.__class__.__name__].append(obj.object)
                    if obj.object.__class__ not in lista:
                        lista.append(obj.object.__class__)
            else:
                if obj.object.__class__.__name__ not in data:
                    data[obj.object.__class__.__name__] = []
                data[obj.object.__class__.__name__].append(obj.object)
                if obj.object.__class__ not in lista:
                    lista.append(obj.object.__class__)

        for key in data:
            print((key, len(data[key])))
            for obj in data[key]:
                try:
                    obj.save()
                except Exception:
                    obj.save_base(raw=True, using=None, force_insert=False, force_update=False)

        if options.pop('add', False):
            for model in lista:
                update_sequence_value(model)
