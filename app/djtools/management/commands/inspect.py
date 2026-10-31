from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    """
    Classe utilitária para fazer buscas no domínio das apps django com base em certas características. Para mais detalhes
    execute 'python manage.py inspect --help'.
    """

    def add_arguments(self, parser):
        # Outros exemplos de como passar argumentos
        # parser.add_argument('poll_id', nargs='+', type=int)
        #
        # # Named (optional) arguments
        # parser.add_argument('--delete',
        #     action='store_true',
        #     dest='delete',
        #     default=False,
        #     help=u'Delete poll instead of closing it')
        parser.add_argument(
            '--hasnot_attr_or_method',
            help='Nome do atributo esta ou método que NÃO deseja procurar dentro do modelo. Ex: python manage.py inspect --hasnot_attr_or_method SEARCH_FIELDS',
        )

        parser.add_argument(
            '--has_attr_or_method',
            help='Nome do atributo esta ou método que se deseja procurar dentro do modelo. Ex: python manage.py inspect --has_attr_or_method buscar',
        )

        parser.add_argument(
            '--has_django_field',
            help='Nome do atributo do model do django que se deseja procurar dentro do modelo. Ex: python manage.py inspect --has_django_field buscar',
        )

        parser.add_argument(
            '--has_django_field_type',
            help='Nome do tipo do atributo do model do django que se deseja procurar dentro do modelo. Ex: python manage.py inspect --has_django_field_type SearchField.',
        )

    def handle(self, *args, **options):
        i = 0
        for m in apps.get_models():
            if options['hasnot_attr_or_method']:
                if not hasattr(m, options['hasnot_attr_or_method']):
                    i += 1
                    print(f'{m.__module__}  -  {m.__name__}')

            if options['has_attr_or_method']:
                if hasattr(m, options['has_attr_or_method']):
                    i += 1
                    print(f'{m.__module__}  -  {m.__name__}')

            if options['has_django_field']:
                for f in m._meta.fields:
                    if f.name == options['has_django_field']:
                        i += 1
                        print(f'{m.__module__}  -  {m.__name__}')

            if options['has_django_field_type']:
                for f in m._meta.fields:
                    if f.__class__.__name__ == options['has_django_field_type']:
                        i += 1
                        print(f'{m.__module__}  -  {m.__name__}')

        print('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - -')
        if i > 0:
            print(f'Total de registros encontrados: {i}')
        else:
            print('Nenhum registro encontrado')
        print()
