import codecs
import json
from os import path
from xml.dom.minidom import parseString

from django.apps import apps
from django.conf import settings

from djtools.management.commands import BaseCommandPlus

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Criar JSON a partir dos arquivos Menu.xml'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument('--reset', action='store_true', help='Reseta menus JSON', default=False)

        parser.add_argument('--ignore', nargs='*', type=str, help='Ignora comando para determinado módulo')

    def handle(self, *args, **options):
        modulos = {value: value for i, value in enumerate(settings.INSTALLED_APPS_SUAP)}
        if options.get('ignore'):
            for modulo in options.get('ignore'):
                if modulo in modulos:
                    modulos.pop(modulo)
                else:
                    print(f'Módulo {modulo} não encontrado na aplicação')
        for app in list(modulos.values()):
            MENU_XML_CONTENTS = []
            filepath = path.join(settings.BASE_DIR, app, 'menu.xml')
            if path.isfile(filepath):
                file_ = open(filepath)
                MENU_XML_CONTENTS.append(file_.read())
                file_.close()
            json_data = []
            for menu_xml_content in MENU_XML_CONTENTS:
                doc = parseString(menu_xml_content)
                for item_tag in doc.getElementsByTagName('item'):
                    permissions = item_tag.getElementsByTagName('permission')
                    groups = item_tag.getElementsByTagName('group')
                    hierarchy = item_tag.getElementsByTagName('hierarchy')[0].firstChild.nodeValue
                    url = item_tag.getElementsByTagName('url')[0].firstChild.nodeValue
                    item = {'hierarchy': hierarchy, 'url': url}
                    if permissions:
                        list_permissions = []
                        for permission in permissions:
                            list_permissions.append(permission.firstChild.nodeValue)
                        item['permissions_required'] = list_permissions
                    if groups:
                        list_groups = []
                        for group in groups:
                            list_groups.append(group.firstChild.nodeValue)
                        item['groups_required'] = list_groups

                    json_data.append(item)

            filepath = path.join(settings.BASE_DIR, app, 'menu.json')
            if not path.isfile(filepath) or options.get('reset'):
                with codecs.open(filepath, 'w', encoding='utf-8') as outfile:
                    json.dump(json_data, outfile, sort_keys=True, indent=4, ensure_ascii=False)
