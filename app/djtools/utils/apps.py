from django.conf import settings
from django.apps import apps
from typing import TypedDict


"""
Área SUAP <-- App SUAP <--- Tag de demandas (Módulo SUAP) <-- Área de atuação de demandas

Área SUAP:
* Classifica apps do SUAP via atributo 'area' configurado em apps.py
de cada app.

Tag de demandas (Módulo SUAP):
* Agrupa uma ou mais Apps SUAP via atributo 'apps_relacionadas'
no cadastro da Tag. Tag de demandas não se confunde com App SUAP e não
se confunde com Área SUAP.
* Classifica Áreas de atuação de demandas via atributo 'tags_relacionadas'
no cadastro da Área de atuação. Área de atuação de demandas não se confunde
com Área SUAP. As 'tags_relacionadas' são os módulos SUAP relacionados.
"""


class AreaSuap(TypedDict):
    area_id: str
    area: str
    icone: str


AREA_SUAP_ADMINISTRACAO = 'administracao'
AREA_SUAP_AUDITORIA = 'auditoria'
AREA_SUAP_ATIV_ESTUDANTIS = 'atividades-estudantis'
AREA_SUAP_COMUM = 'comum'
AREA_SUAP_COMUNICACAO = 'comunicacao'
AREA_SUAP_DESENVOLVIMENTO = 'desenvolvimento'
AREA_SUAP_PROCESSOS = 'processos'
AREA_SUAP_PROGRAMA_GESTAO = 'programa-de-gestao'
AREA_SUAP_ENSINO = 'ensino'
AREA_SUAP_EXTENSAO = 'extensao'
AREA_SUAP_RH = 'rh'
AREA_SUAP_PESQUISA = 'pesquisa'
AREA_SUAP_TI = 'ti'


AREAS_SUAP_CONF: list[AreaSuap] = [
    {'area_id': AREA_SUAP_ADMINISTRACAO, 'area': 'Administração', 'icone': 'tasks'},
    {'area_id': AREA_SUAP_AUDITORIA, 'area': 'Auditoria', 'icone': 'auditoria'},
    {'area_id': AREA_SUAP_ATIV_ESTUDANTIS, 'area': 'Atividades Estudantis', 'icone': 'graduation-cap'},
    {'area_id': AREA_SUAP_COMUM, 'area': 'Comum', 'icone': 'list'},
    {'area_id': AREA_SUAP_COMUNICACAO, 'area': 'Comunicação Social', 'icone': 'comment'},
    {'area_id': AREA_SUAP_DESENVOLVIMENTO, 'area': 'Desenvolvimento Institucional', 'icone': 'chart-bar'},
    {'area_id': AREA_SUAP_PROCESSOS, 'area': 'Documentos e Processos Eletrônicos', 'icone': 'file'},
    {'area_id': AREA_SUAP_PROGRAMA_GESTAO, 'area': 'Programa de Gestão', 'icone': 'programa-de-gestao'},
    {'area_id': AREA_SUAP_ENSINO, 'area': 'Ensino', 'icone': 'user-graduate'},
    {'area_id': AREA_SUAP_EXTENSAO, 'area': 'Extensão', 'icone': 'suitcase'},
    {'area_id': AREA_SUAP_RH, 'area': 'Gestão de Pessoas', 'icone': 'users'},
    {'area_id': AREA_SUAP_PESQUISA, 'area': 'Pesquisa e Inovação', 'icone': 'globe'},
    {'area_id': AREA_SUAP_TI, 'area': 'Tecnologia da Informação', 'icone': 'laptop'},
]


def get_areas_suap() -> dict[str, AreaSuap]:
    areas: dict[str, AreaSuap] = {}
    for app in get_apps_suap():
        area = getattr(app, 'area', 'Tecnologia da Informação')
        area_conf = [conf for conf in AREAS_SUAP_CONF if conf['area'] == area]
        if area_conf:
            area_id = area_conf[0]['area_id']
            icone = area_conf[0]['icone']
        else:
            area_id = area
            icone = 'border-none'
        if area_id not in areas:
            areas[area_id] = {
                'area_id': area_id,
                'area': area,
                'icone': icone,
            }
    return dict(sorted(areas.items(), key=lambda i: i[1]['area']))


def get_apps_suap(area: AreaSuap | None = None):
    modulos = []
    for app in apps.get_app_configs():
        if app.label in (*settings.INSTALLED_APPS_SUAP, 'djtools'):
            if not hasattr(app, 'icon'):
                app.icon = 'list'
            if (not area) or (getattr(app, 'area', 'Tecnologia da Informação') == area.get('area')):
                modulos.append(app)
    return sorted(modulos, key=lambda x: (x.verbose_name, getattr(x, 'area', '')))


def get_apps_suap_as_choices(area: AreaSuap | None = None) -> list[tuple[str, str]]:
    return [(app.label, f'{get_app_suap_display(app.label)}') for app in get_apps_suap(area)]


def get_app_suap_display(app_label):
    app_display = '?'
    app_area = '?'
    for app in get_apps_suap():
        if app.label == app_label:
            app_display = f'{app.verbose_name or "?"} ({app_label})'
            app_area = getattr(app, 'area', None) or 'Não definida'
    return f'{app_display} | Área: {app_area}'


def get_app_suap_verbose_name(app_label):
    for app in get_apps_suap():
        if app.label == app_label:
            return app.verbose_name or '?'
    return '?'
