import json

from django.apps import apps

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('modulos', nargs='*', type=str, help='Módulos')

    def get_or_create_from_dict(self, model_path, unique_fields, defaults):
        Model = apps.get_model(model_path)
        lookup = {field: defaults[field] for field in unique_fields}
        obj, created = Model.objects.get_or_create(defaults=defaults, **lookup)
        if self.verbosity > 0:
            if created:
                self.stdout.write(f'  Criado: {obj}')
            else:
                self.stdout.write(f'  Já existe: {obj}')
        return obj

    def handle(self, *args, **options):
        self.verbosity = options.get('verbosity', 1)
        with open('comum/fixtures/apis_externas.json') as f:
            apis_externas = f.read()
        apis = json.loads(apis_externas)

        for api in apis:
            if self.verbosity > 0:
                self.stdout.write(f'Carregando API Externa: {api["nome"]}')
            self.get_or_create_from_dict(
                'comum.ApiExterna',
                unique_fields=['nome'],
                defaults=api,
            )
