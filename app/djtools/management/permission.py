# O processo de permissões:
# O script deve ter opções para:
#    - Resetar todas as permissões (padrão)
#    - Somente garantir as permissões dos grupos
#    - Poder escolher a aplicação a resetar/atualizar permissões
#    - Validar se o grupo já foi definido
#    - Validar duplicidade de permissão em um mesmo grupo
#    - Colocar uma opção force para efetuar as operações indepente das Warnings

from os.path import isfile

import yaml
from django.conf import settings
from django.contrib.auth.models import Group

from comum.models import GerenciamentoGrupo


def obter_texto(node_list):
    rc = ''
    for node in node_list:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc


def obter_por_nome_tag(node_list, tagName):
    for node in node_list:
        if node.nodeType == node.ELEMENT_NODE and node.tagName == tagName:
            return node
    return None


class App:
    def __init__(self, nome=None):
        self.nome = nome
        self.grupos = {}


class Grupo:
    def __init__(self, nome=None, app=None):
        self.nome = nome
        self.app = app
        self.permissoes = []
        self.app_manager = None
        self.can_manager = True
        self.description = ''

    def set_notmanageable(self):
        self.can_manager = False

    def set_manager(self, app):
        self.app_manager = app

    def set_description(self, description):
        self.description = description


class Permissao:
    def __init__(self, model_app, model_name, permission_name):
        self.nome = f'{model_app}.{model_name}.{permission_name}'


class GroupPermission:
    def __init__(self):
        self.apps = {}
        self.nomes_grupo = {}

    def obter_grupos(self):
        retorno = []
        for app in list(self.apps.values()):
            retorno.extend(list(app.grupos.values()))
        return retorno

    def app_registry(self, model_app_name):
        if model_app_name in self.apps:
            app = self.apps[model_app_name]
        else:
            app = App(model_app_name)
            self.apps[model_app_name] = app
        return app

    def group_registry(self, group_name, model_app_name, app):
        if group_name in app.grupos:
            grupo = app.grupos[group_name]
        else:
            # se não, crie e já adicione
            grupo = Grupo(group_name, model_app_name)
            app.grupos[group_name] = grupo
            self.nomes_grupo[group_name] = grupo
        return grupo

    def processar_yaml(self, nome_arquivo_permissao, current_app):
        with open(rf'{nome_arquivo_permissao}') as arquivo:
            dados = yaml.safe_load(arquivo)
        permissoes = []
        # Start process permission file
        for group_name, group_detail in dados.items():
            can_manager = group_detail.pop('can_manager', True)
            description = group_detail.pop('description', '')
            app_manager = group_detail.pop('app_manager', current_app)
            if bool(group_detail):
                for model_app_name, models in group_detail.items():
                    # se já estiver adicionado recupere
                    app = self.app_registry(model_app_name)
                    grupo = self.group_registry(group_name, model_app_name, app)

                    # se já estiver adicionado recupere
                    if (app_manager == model_app_name == current_app) and not can_manager:
                        grupo.set_notmanageable()
                    if app_manager:
                        grupo.set_manager(app_manager)
                    if description:
                        grupo.set_description(description)

                    # Process permissions
                    for model_name, permissions in models.items():
                        for permission_name in permissions:
                            permissao = Permissao(model_app_name, model_name, permission_name)
                            grupo.permissoes.append(permissao)
                            permissoes.append(permissao.nome)
            else:
                app = self.app_registry(current_app)
                grupo = self.group_registry(group_name, current_app, app)

        return permissoes

    def obter_dicionario(self):
        retorno = {}
        for grupo in self.obter_grupos():
            nome_grupo = grupo.nome
            retorno[nome_grupo] = []
            if grupo.description:
                retorno[f'{nome_grupo}_description'] = grupo.description
            for permissao in grupo.permissoes:
                retorno[nome_grupo].append(permissao.nome)

        return retorno

    def processar(self, nome_arquivo_permissao, current_app):
        from xml.dom import minidom

        from djtools.utils import to_ascii

        dom = minidom.parse(nome_arquivo_permissao).documentElement
        permissoes = []
        # Start process permission file
        for group in dom.getElementsByTagName('group'):
            group_names = obter_texto(group.getElementsByTagName('name')[0].childNodes).split(';')
            not_manageable_tag = bool(group.getElementsByTagName('notmanageable'))
            description = obter_texto(group.getElementsByTagName('description')[0].childNodes) if group.getElementsByTagName('description') else ''
            # Se tiver a tag app do grupo
            group_app_tag = obter_por_nome_tag(group.childNodes, 'app')
            if group_app_tag:
                group_names_app = (obter_texto(obter_por_nome_tag(group.childNodes, 'app').childNodes) or current_app).split(';')

                # se não tiver a mesma quantidade
                if len(group_names) != len(group_names_app):
                    raise Exception(
                        f'In {current_app}/permission.xml group name {group_names} or apps {group_names_app} has no app correctly defined'
                    )

            for index, group_name in enumerate(group_names):
                group_name = group_name.strip()

                # Caso não tenha definito a app, a app defaul será a do permissions.xml
                group_app = current_app
                if group_app_tag:
                    group_app = group_names_app[index].strip()

                if group_name in self.nomes_grupo and self.nomes_grupo[group_name].app != group_app:
                    raise Exception(
                        f'In {current_app}/permission.xml group name {group_names} has been defined in module {self.nomes_grupo[group_name].app}'
                    )

                # se já estiver adicionado recupere
                if group_app in self.apps:
                    app = self.apps[group_app]
                else:
                    # se não, crie e já adicione
                    app = App(group_app)
                    self.apps[group_app] = app

                # se já estiver adicionado recupere
                if group_name in app.grupos:
                    grupo = app.grupos[group_name]
                else:
                    # se não, crie e já adicione
                    grupo = Grupo(group_name, group_app)
                    app.grupos[group_name] = grupo
                    self.nomes_grupo[group_name] = grupo

                if (not group_app_tag or (group_app_tag and group_app_tag == current_app)) and not_manageable_tag:
                    grupo.set_notmanageable()

                if description:
                    grupo.set_description(description)

                tags_models = group.getElementsByTagName('models')
                tags_model = group.getElementsByTagName('model')

                if tags_models.length > 1:
                    raise Exception(to_ascii(f'Nao deve haver mais de uma tag models em uma tag group => {nome_arquivo_permissao}[{group_name}]'))
                elif tags_models.length == 1:
                    if tags_model.length == 0:
                        raise Exception(to_ascii(f'Deve haver ao menos de uma tag model em uma tag models => {nome_arquivo_permissao}[{group_name}]'))
                elif tags_models.length == 0:
                    if tags_model.length != 0:
                        raise Exception(to_ascii(f'A tag model deve estar em uma tag models => {nome_arquivo_permissao}[{group_name}]'))

                # Process permissions
                for model in tags_model:
                    model_app = obter_texto(model.getElementsByTagName('app')[0].childNodes)
                    model_name = obter_texto(model.getElementsByTagName('name')[0].childNodes)
                    for permission in model.getElementsByTagName('permission'):
                        permission_name = obter_texto(permission.childNodes)
                        permissao = Permissao(model_app, model_name, permission_name)
                        grupo.permissoes.append(permissao)
                        permissoes.append(permissao.nome)
        return permissoes

    def obter_dicionario_yaml(self, app_name=None):
        retorno = {}
        for grupo in self.obter_grupos():
            nome_grupo = grupo.nome
            retorno[nome_grupo] = {}
            if grupo.description:
                retorno[f'{nome_grupo}']['description'] = grupo.description
            if not grupo.can_manager:
                retorno[f'{nome_grupo}']['can_manager'] = False

            if grupo.app != app_name:
                retorno[f'{nome_grupo}']['app_manager'] = grupo.app

            for permissao in grupo.permissoes:
                app, model, permission_name = permissao.nome.split('.')
                if not retorno[nome_grupo].get(app):
                    retorno[nome_grupo][app] = {}
                if not retorno[nome_grupo][app].get(model):
                    retorno[nome_grupo][app][model] = []
                retorno[nome_grupo][app][model].append(permission_name)
        return retorno

    def obter_dicionario_permissoes_descricoes(self):
        permissoes = {}
        descricoes = {}
        managers = {}
        for app in list(self.apps.values()):
            for grupo in list(app.grupos.values()):
                nome_grupo = grupo.nome
                if not permissoes.get(nome_grupo):
                    permissoes[nome_grupo] = []
                if not descricoes.get(nome_grupo):
                    descricoes[nome_grupo] = {}
                if not managers.get(nome_grupo):
                    managers[nome_grupo] = {}
                descricoes[nome_grupo][app.nome] = grupo.description if hasattr(grupo, 'description') else ''
                managers[nome_grupo] = grupo.app_manager if hasattr(grupo, 'app_manager') else app.nome
                for permissao in grupo.permissoes:
                    permissoes[nome_grupo].append(permissao.nome)

        return permissoes, descricoes, managers

    @classmethod
    def obter_grupos_por_app_yaml(cls, app):
        groups = set()
        permission_file_name = f'{app}/permissions.yaml'
        if settings.LPS and isfile(f'{app}/lps/{settings.LPS}/permissions.yaml'):
            permission_file_name = f'{app}/lps/{settings.LPS}/permissions.yaml'

        if isfile(permission_file_name):
            with open(rf'{permission_file_name}') as arquivo:
                dados = yaml.safe_load(arquivo)

            for group_name, group_detail in dados.items():
                app_manager = group_detail.get('app_manager')
                if not app_manager or app_manager == app:
                    groups.add(group_name)

            grupo_gerenciador = Group.objects.filter(name=GerenciamentoGrupo.NOME_GRUPO_GERENCIADOR_FORMAT.format(app))
            if grupo_gerenciador.exists():
                groups.add(grupo_gerenciador[0].name.strip())
            grupo_configuracador = Group.objects.filter(name=GerenciamentoGrupo.NOME_GRUPO_CONFIGURADOR_FORMAT.format(app)).first()
            if grupo_configuracador:
                groups.add(grupo_configuracador.name.strip())

        return groups
