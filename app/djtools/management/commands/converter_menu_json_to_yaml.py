import json
import os

import yaml
from django.conf import settings
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    help = 'Criar YAML a partir dos arquivos menu.json'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument('--reset', action='store_true', help='Reseta menus YAML', default=False)

    def generate_yaml(self, old_json_file, new_yaml_file):
        if os.path.isfile(old_json_file):
            self.stdout.write(termcolors.make_style(fg='yellow')(f'Processing {old_json_file}'))
            with open(new_yaml_file, 'w') as file:
                with open(old_json_file) as f:
                    dic = json.loads(f.read())
                    new_dic = {}
                    for obj in dic:
                        key = obj.pop('hierarchy')
                        new_dic[key] = obj
                yaml.safe_dump(new_dic, file, encoding='utf-8', allow_unicode=True, default_flow_style=False)

    def handle(self, *args, **options):
        modulos = {value: value for i, value in enumerate(settings.INSTALLED_APPS_SUAP)}
        modulos['djtools'] = 'djtools'
        for app in list(modulos.values()):
            filepath_new = os.path.join(settings.BASE_DIR, f'{app}/menu.yaml')
            if options.get('reset'):
                if os.path.exists(filepath_new):
                    self.stdout.write(termcolors.make_style(fg='yellow')(f'Apagando {filepath_new}'))
                    os.remove(filepath_new)
            else:
                filepath = f'{app}/menu.json'
                filepath_lps = f'{app}/lps/{settings.LPS}/menu.json'
                filepath_lps_new = f'{app}/lps/{settings.LPS}/menu.yaml'
                if settings.LPS:
                    self.generate_yaml(filepath_lps, filepath_lps_new)
                self.generate_yaml(filepath, filepath_new)
