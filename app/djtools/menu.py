import logging
import re
from functools import cmp_to_key
from os import path

import yaml
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.template.defaultfilters import slugify

from djtools.modulos_ocultos import menu_visivel
from djtools.utils import running_tests, to_ascii
from suap import nomenclatura

logger = logging.getLogger(__name__)

MENU_APP_ORDER = ['documento_eletronico', 'processo_eletronico', 'pgd', 'pgd2', 'edu', 'pesquisa', 'projetos', 'rh']
cache.delete('menus')
ORDER_DEFAULT = 99
MENU_ITEMS_ORDER = {}


def get_menu_from_file(app):
    filepath = path.join(settings.BASE_DIR, app, 'menu.yaml')
    retorno = []
    if settings.LPS:
        filepath_lps = path.join(settings.BASE_DIR, app, 'lps', settings.LPS, 'menu.yaml')
        if path.isfile(filepath_lps):
            filepath = filepath_lps

    if path.isfile(filepath):
        with open(filepath, encoding='utf-8') as data_file:
            try:
                dic = yaml.safe_load(data_file)
                lista = []
                for key, value in dic.items():
                    obj = {}
                    obj['hierarchy'] = key
                    obj.update(value)
                    lista.append(obj)
                retorno += lista
            except Exception as e:
                logger.warning(f'Erro ao processar arquivo {filepath}: {e}')
    return retorno


def colocar_menu_na_cache():
    if not cache.get('menus'):
        menu_json = []
        for app in MENU_APP_ORDER:
            if app in settings.INSTALLED_APPS_SUAP:
                menu_json += get_menu_from_file(app)
        for app in (*settings.INSTALLED_APPS_SUAP, 'djtools'):
            if app not in MENU_APP_ORDER:
                menu_json += get_menu_from_file(app)

        cache.set('menus', menu_json, 60)
    return cache.get('menus') or []


def compare_order_nodes(a, b):
    order_a = MENU_ITEMS_ORDER.get(f'{a["hierarchy"]}::{a["label"]}') or ORDER_DEFAULT
    order_b = MENU_ITEMS_ORDER.get(f'{b["hierarchy"]}::{b["label"]}') or ORDER_DEFAULT
    if order_a > order_b:
        return 1
    elif order_a == order_b:
        return 0
    else:
        return -1


def get_menu_json_as_html(user):
    menu_items = []  # Lista dos itens de menu; cada item é o raiz com seus filhos
    menu_items_index = {}  # Controle dos raízes

    def add_item(path, url):
        for idx, i in enumerate(path):
            path_idx = '::'.join(path[: idx + 1])
            eh_folha = idx == len(path) - 1
            # Primeiro Elemento Raiz
            if idx == 0 and path_idx not in menu_items_index:
                item = {'hierarchy': None, 'label': i, 'children': [], 'css_class': to_ascii(slugify(i.lower()))}
                menu_items.append(item)
                menu_items_index[path_idx] = item
            # Nao eh primeiro nem ultimo
            elif not eh_folha:
                if path_idx not in menu_items_index:
                    i = i.format(nomenclatura=nomenclatura)
                    item = {'hierarchy': '::'.join(path_idx.split('::')[0:-1]), 'label': i, 'children': []}
                    menu_items_index[path_idx] = item
                    menu_items_index['::'.join(path[:idx])]['children'].append(item)
            else:  # Folha
                i = i.format(nomenclatura=nomenclatura)
                id_ = '_'.join([re.sub(r'\W', '', i.lower()) for i in path])
                item = {'hierarchy': '::'.join(path_idx.split('::')[0:-1]), 'label': i, 'url': url, 'id_': id_}
                menu_items_index['::'.join(path[:idx])]['children'].append(item)

    def get_items_as_li(node):
        nodes = []
        __get_descendents_helper(node, nodes)
        return ''.join(nodes)

    def __get_descendents_helper(node, nodes):
        node_children = node.get('children', [])
        node_children = sorted(node_children, key=cmp_to_key(compare_order_nodes))
        css = node.get('css_class', b'')
        css_class = []
        if node_children:
            css_class.append('has-child')
        if node.get('css_class'):
            css_class.append('menu-' + css)
        css_class = ' '.join(css_class)

        url = '#'
        icon = ''
        if css:
            icon = f'<span class="icone fas fa-{css}" aria-hidden="true"></span>'
        id_ = ''
        if node.get('url'):
            url = '/djtools/breadcrumbs_reset/'
            icon = ''
            if node.get('id_'):
                id_ = 'id="menu-item-{}"'.format(node.get('id_'))
                url += str(node.get('id_'))
            if node.get('url'):
                url += node.get('url')
            if running_tests():
                url = node.get('url')
            if not url.endswith('/') and '?' not in url:
                url += '/'

        nodes.append(
            '<li class="{}" {}><a href="{}" title="{}">{} <span>{}</span></a>'.format(css_class, id_, url, node['label'], icon, node['label'])
        )

        if node_children:
            nodes.append('<ul>')
        for c in node_children:
            __get_descendents_helper(c, nodes)
        if node_children:
            nodes.append('</ul>')
        nodes.append('</li>')
        return nodes

    if user.is_superuser:
        user_groups = Group.objects.all().values_list('name', flat=True)
    else:
        user_groups = user.groups.values_list('name', flat=True)
    user_permissions = user.get_all_permissions()
    # Guardar conteúdos dos menu.xml em memória
    menu = menu_visivel(colocar_menu_na_cache())
    for item_menu in menu:
        # Verificando se o usuário tem direito ao item
        show_item = False
        from comum.models import Configuracao

        has_required_config = False
        if (
            item_menu.get('config_required')
            and any(bool(Configuracao.get_valor_por_chave(*each.split('.'))) for each in item_menu['config_required'])
            or not item_menu.get('config_required')
        ):
            has_required_config = True
        if has_required_config:
            if (
                not item_menu.get('permissions_required')
                and not item_menu.get('groups_required')
                or item_menu.get('permissions_required')
                and any(each in item_menu['permissions_required'] for each in user_permissions)
                or item_menu.get('groups_required')
                and any(each in item_menu['groups_required'] for each in user_groups)
            ):
                show_item = True
        if not show_item:
            continue
        hierarchy = item_menu.get('hierarchy')
        if item_menu.get('order'):
            MENU_ITEMS_ORDER['::'.join(hierarchy.split('::'))] = item_menu.get('order')
        if item_menu.get('url'):
            add_item(hierarchy.split('::'), url=item_menu.get('url'))

    menu_html = []
    for i in menu_items:
        menu_html.append(get_items_as_li(i))
    return ''.join(menu_html)
