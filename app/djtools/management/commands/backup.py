# ruff: noqa: T100
import pdb

from django.apps import apps
from django.core import serializers
from django.db.models.deletion import Collector

from djtools.management.commands import BaseCommandPlus


def dump(qs):
    lista = []
    c = []
    collector = Collector('default')
    collector.collect(qs)
    for instances in collector.data.values():
        for instance in instances:
            if instance.__class__.__name__ not in ['Log', 'RegistroDiferenca'] and instance not in lista:
                lista.append(instance)
                if instance.__class__.__name__ not in c:
                    c.append(instance.__class__.__name__)
    for qs in collector.fast_deletes:
        for instance in qs:
            if instance.__class__.__name__ not in ['Log', 'RegistroDiferenca'] and instance not in lista:
                lista.append(instance)
                if instance.__class__.__name__ not in c:
                    c.append(instance.__class__.__name__)
    return c, lista


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        # Positional argument
        parser.add_argument('--obj', type=str, help='Object query in the format: <app>.</model>.<id>. Ex: edu.pais.245')

    def handle(self, *args, **options):
        obj = options['obj']
        queryset = None

        if obj:
            app, model, pk = obj.split('.')
            queryset = apps.get_model(app, model).objects.filter(pk=pk)
        else:
            msg = '\nPor favor, instancie o queryset que você deseja salvar e em seguida digite a tecla "c".\nÉ necessário importar os modelos necessários.\n\tEx: from edu.models import Aluno\n\tqueryset = Aluno.objects.filter(ano_letivo__ano=2015)\n\n'
            self.stdout.write(msg)
            pdb.set_trace()
        c, lista = dump(queryset)
        msg = '\nUm arquivo "backup.json" foi salvo no diretório corrente contendo {} objetos. Para restaurá-los, digite o seguinte comando:\n\n\tpython manage.py restore {} < backup.json\n\nÉ necessário ordenar as classes corretamente de acordo com as dependências entre elas.\n\n'.format(
            len(lista), ' '.join(c)
        )
        self.stdout.write(msg)
        f = open('backup.json', 'w')
        f.write(serializers.serialize('json', lista))
        f.close()
