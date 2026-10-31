import json
import os
from collections import OrderedDict
from pprint import pformat

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRel
from django.db.models import ManyToManyRel, ManyToOneRel, OneToOneRel

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument(
            '--details',
            action='store_true',
            dest='details',
            default=False,
            help='Exibe detalhes dos relacionamentos',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            dest='check',
            default=False,
            help='Compara com o arquivo module_dependencies.json',
        )
        parser.add_argument(
            '--save',
            action='store_true',
            dest='save',
            default=False,
            help='Salva as dependências no arquivo module_dependencies.json',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            dest='all',
            default=False,
            help='Altera o settings.INSTALLED_APPS para pegar todos os módulos do SUAP',
        )

    def generate_dependencies(self, options):
        dependencies = {}
        klasses = apps.get_models()
        for model in klasses:
            current_app = model._meta.app_label
            if current_app not in dependencies:
                if options['details']:
                    dependencies[current_app] = {}
                else:
                    dependencies[current_app] = []
            fields = model._meta.get_fields()
            for field in fields:
                if (
                    type(field) not in [ManyToOneRel, OneToOneRel, ManyToManyRel, GenericRel]
                    and getattr(field, 'related_model', None)
                    and current_app != field.related_model._meta.app_label
                ):
                    if options['details']:
                        dependencies[current_app][field.related_model._meta.app_label] = [model, field]
                    else:
                        if field.related_model._meta.app_label not in dependencies[current_app]:
                            dependencies[current_app].append(field.related_model._meta.app_label)
        if not options['check']:
            self.stdout.write(pformat(dependencies))
        return {key: dependencies[key] for key in sorted(dependencies.keys())}

    def handle(self, *args, **options):
        if options['all'] or options['save']:
            ALL_APPS = tuple(
                [
                    dir
                    for dir in os.listdir(settings.BASE_DIR)
                    if os.path.isdir(dir)
                    and '__init__.py' in os.listdir(os.path.join(settings.BASE_DIR, dir))
                    and dir
                    not in [
                        'tests',
                        'suap',
                        'djtools',
                    ]
                ]
            )
            apps.app_configs = OrderedDict()
            apps.apps_ready = apps.models_ready = apps.loading = apps.ready = False
            apps.clear_cache()
            apps.populate(settings.PRE_INSTALLED_APPS_SUAP + ALL_APPS + settings.POS_INSTALLED_APPS_SUAP)
        dependencies = self.generate_dependencies(options)
        filename = os.path.join(settings.BASE_DIR, 'module_dependencies.json')
        if options['save']:
            with open(filename, 'w') as f:
                json.dump(dependencies, f, indent=2)
        if options['check']:
            with open(filename) as f:
                MODULE_DEPENDENCIES = json.load(f)
            diff = dict_diff(MODULE_DEPENDENCIES, dependencies)
            if diff['added'] or diff['removed'] or diff.get('value_diffs'):
                self.stdout.write(pformat(dict_diff(MODULE_DEPENDENCIES, dependencies)))
                raise Exception('Dependências alteradas')


def dict_diff(dict_a, dict_b, show_value_diff=True):
    result = {}
    dict_a = dict_a or {}
    dict_b = dict_b or {}

    result['added'] = {k: dict_b[k] for k in set(dict_b) - set(dict_a)}
    result['removed'] = {k: dict_a[k] for k in set(dict_a) - set(dict_b)}
    if show_value_diff:
        common_keys = set(dict_a) & set(dict_b)
        value_diffs = {}
        for k in common_keys:
            a_val = dict_a[k]
            b_val = dict_b[k]
            if isinstance(a_val, list) and isinstance(b_val, list):
                if sorted(a_val) != sorted(b_val):
                    value_diffs[k] = (a_val, b_val)
            else:
                if a_val != b_val:
                    value_diffs[k] = (a_val, b_val)
        result['value_diffs'] = value_diffs
    return result
