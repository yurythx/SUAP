"""
Converter:
``APP/permissions.xml`` template:

<groups>
    <group>
        <name>suap_operador</name>
        <models>
            <model>
                <app>comum</app>
                <name>sala</name>
                <permissions>
                    <permission>can_add_sala</permission>
                    <permission>can_change_sala</permission>
                    <permission>can_delete_sala</permission>
                </permissions>
            </model>
        </models>
    </group>
</groups>

PARA:
``APP/permissions.yaml`` template:

suap_operador
    comum:
        sala: add, change, delete
"""

import os
from os.path import isfile

import yaml
from django.conf import settings
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus
from djtools.management.permission import GroupPermission


class Command(BaseCommandPlus):
    grupos_no_permisions_xml = []

    def handle(self, *args, **options):
        for app in os.listdir(settings.BASE_DIR):
            self.processar_group_permission(app, options)

    def processar_group_permission(self, app, options):
        permissionFileName = f'{app}/permissions.xml'
        if settings.LPS:
            permissionFileName_lps = f'{app}/lps/{settings.LPS}/permissions.xml'
            if isfile(permissionFileName_lps):
                if options['verbosity'] in ('2', '3'):
                    self.stdout.write(termcolors.make_style(fg='yellow')(f'Processing {permissionFileName_lps}'))
                groupPermission = GroupPermission()
                groupPermission.processar(permissionFileName_lps, app)
                with open(rf'{app}/lps/{settings.LPS}/permissions.yaml', 'w') as file:
                    yaml.safe_dump(groupPermission.obter_dicionario_yaml(app), file, encoding='utf-8', allow_unicode=True, default_flow_style=False)
        if isfile(permissionFileName):
            if options['verbosity'] in ('2', '3'):
                self.stdout.write(termcolors.make_style(fg='yellow')(f'Processing {permissionFileName}'))
            groupPermission = GroupPermission()
            groupPermission.processar(permissionFileName, app)
            with open(rf'{app}/permissions.yaml', 'w') as file:
                yaml.safe_dump(groupPermission.obter_dicionario_yaml(app), file, encoding='utf-8', allow_unicode=True, default_flow_style=False)
