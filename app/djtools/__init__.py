import os
from os import path
from xml.dom import minidom

from django.conf import settings
from django.utils.safestring import mark_safe

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suap.settings')


def get_item(_item):
    if _item.getElementsByTagName('view'):
        view = _item.getElementsByTagName('view')[0].firstChild.nodeValue.strip()
    else:
        view = None
    if _item.getElementsByTagName('tip'):
        tip = _item.getElementsByTagName('tip')[0].firstChild.nodeValue.strip()
    else:
        tip = None
    if _item.getElementsByTagName('name'):
        name = _item.getElementsByTagName('name')[0].firstChild.nodeValue.strip()
    else:
        name = None
    if _item.getElementsByTagName('description'):
        description = _item.getElementsByTagName('description')[0].toxml()[13:-14].strip()
    else:
        description = None
    groups = []
    for _groups in _item.getElementsByTagName('groups'):
        if _groups.parentNode == _item:
            for _group in _groups.getElementsByTagName('group'):
                group = _group.firstChild.nodeValue.strip()
                groups.append(group)

    required_models = []
    for _required_models in _item.getElementsByTagName('required-models'):
        if _required_models.parentNode == _item:
            for _required_model in _required_models.getElementsByTagName('required-model'):
                required_model = _required_model.firstChild.nodeValue.strip()
                required_models.append(required_model)

    actions = []
    for _actions in _item.getElementsByTagName('actions'):
        if _actions.parentNode == _item:
            for _action in _actions.getElementsByTagName('action'):
                if _action.getElementsByTagName('view') and not _action.getElementsByTagName('name'):
                    action_view = _action.getElementsByTagName('view')[0].firstChild.nodeValue.strip()
                    tip_view = ''
                    if _action.getElementsByTagName('tip'):
                        tip_view = _action.getElementsByTagName('tip')[0].firstChild.nodeValue.strip()
                    actions.append({'view': action_view, 'tip': tip_view})
                else:
                    action_item = get_item(_action)
                    actions.append(action_item)
                    HELP_XML_CONTENTS[action_item['view']] = action_item
    required_to = []
    for _required_to in _item.getElementsByTagName('required-to'):
        if _required_to.parentNode == _item:
            for _required_to_item in _required_to.getElementsByTagName('ref'):
                required_to_item = _required_to_item.firstChild.nodeValue.strip()
                required_to.append(required_to_item)
    conditions = []
    for _conditions in _item.getElementsByTagName('conditions'):
        if _conditions.parentNode == _item:
            for _condition in _conditions.getElementsByTagName('condition'):
                condition = _condition.toxml()[11:-12].strip()
                conditions.append(mark_safe(condition))

    detail = ''
    for _details in _item.getElementsByTagName('detail'):
        if _details.parentNode == _item:
            if _details:
                detail = _details.toxml()[8:-9].strip()

    if view:
        app_name, view_name = view.split('.')
        url = f'/djtools/help_view/{app_name}/{view_name}/'
    else:
        url = None

    return {
        'view': view,
        'name': name,
        'groups': groups,
        'actions': actions,
        'required_models': required_models,
        'required_to': required_to,
        'conditions': conditions,
        'description': mark_safe(description),
        'detail': mark_safe(detail),
        'url': url,
        'tip': tip,
    }


HELP_XML_CONTENTS = {}
if not HELP_XML_CONTENTS:
    for app in settings.INSTALLED_APPS:
        filepath = path.join(settings.BASE_DIR, app, 'help.xml')
        if path.isfile(filepath):
            dom = minidom.parse(filepath).documentElement
            for _item in dom.getElementsByTagName('item'):
                item = get_item(_item)
                view = item['view']
                HELP_XML_CONTENTS[view] = item
