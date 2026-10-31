import os

from django.apps import apps
from django.conf import settings
from django.db import models

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Classe utilitária que varre as entidades que possuem atributos do tipo FileFields e verifica se os arquivos apontados
    existem em disco. Para mais detalhes execute 'python manage.py inspect --help'.

    Ex:
    python manage.py procurar_arquivos_ausentes
    python manage.py procurar_arquivos_ausentes --showall
    python manage.py procurar_arquivos_ausentes --modelname DocumentoControle
    python manage.py procurar_arquivos_ausentes --logdir /Users/misaelbarreto/
    python manage.py procurar_arquivos_ausentes --logdir /Users/misaelbarreto/ --logforentity
    python manage.py procurar_arquivos_ausentes --showall --logdir /Users/misaelbarreto/ --logforentity
    python manage.py procurar_arquivos_ausentes --modelname comum.models --showall --logdir /Users/misaelbarreto/ --logforentity
    """

    def __print_and_log(self, msg=''):
        print(msg)
        self.log.write(msg + '\n')

    def add_arguments(self, parser):
        parser.add_argument(
            '--showall',
            action='store_true',
            dest='showall',
            default=False,
            help='Mostrar todas as entidades varridas no procedimento. Obs: Por padrão só são exibidas as entidades que tem atributos do tipo FileField',
        )

        parser.add_argument(
            '--logforentity', action='store_true', dest='logforentity', default=False, help='Cria um arquivo de log separado para cada entidade'
        )

        parser.add_argument('--logdir', help='Diretório no qual deverá ser salvo o log')

        parser.add_argument('--modelname', help='Nome da entidade na qual se deseja realizar a busca')

    def handle(self, *args, **options):
        # Obtendo todos os parâmetros...
        show_all = options['showall']
        logforentity = options['logforentity']
        logdir = options['logdir'] or ''
        modelname = options['modelname']

        self.log = None
        for model in apps.get_models():
            if (not modelname) or (modelname in str(model)):
                fields = [f for f in model._meta.fields if isinstance(f, models.FileField)]

                if fields or modelname or show_all:
                    if logforentity:
                        self.log = open(os.path.join(logdir, f'{model.__module__}.{model.__name__}.log'), 'w')
                    elif not self.log:
                        self.log = open(os.path.join(logdir, 'procurar_arquivos_ausentes.log'), 'w')

                    self.__print_and_log()
                    self.__print_and_log('#' * len(str(model)))
                    self.__print_and_log(str(model))
                    self.__print_and_log('#' * len(str(model)))

                    for field in fields:
                        values_list = (
                            model.objects.exclude(**{field.attname: ''})
                            .exclude(**{field.attname: None})
                            .values_list('id', field.attname)
                            .order_by('id')
                        )

                        for pk, filename in values_list:
                            if callable(field.upload_to):
                                part1 = ''
                            else:
                                part1 = settings.MEDIA_ROOT
                            filename_path = os.path.join(part1, filename)
                            if not os.path.exists(filename_path):
                                self.__print_and_log(f'pk {pk};  field {field.attname};  field_value {filename_path}')

        self.log.close()
