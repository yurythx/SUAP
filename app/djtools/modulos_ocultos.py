"""Perfil administrativo: esconde ensino, pesquisa, extensão e vida estudantil.

Os apps continuam em INSTALLED_APPS. O SUAP oficial não sobe se eles saem da
lista (models de gestão e de pessoas importam o acadêmico). Com DISABLE_EDU o
menu, os quadros da página inicial, a API e o admin desses módulos somem, e a
URL direta responde 404.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings

# Ensino, pesquisa, extensão, vida estudantil e carreira docente.
# Fora desta lista de propósito: cursos (cursos e concursos de servidor),
# remanejamento (remoção interna) e gestao (indicadores institucionais).
APPS_ACADEMICOS = frozenset(
    {
        'acervo_academico',
        'ae',
        'auxilioemergencial',
        'avaliacao_cursos',
        'avaliacao_integrada',
        'cnpq',
        'cpa',
        'edu',
        'egressos',
        'encceja',
        'estagios',
        'etep',
        'labfisico',
        'labvirtual',
        'pafc',
        'pedagogia',
        'pesquisa',
        'pit_rit',
        'pit_rit_v2',
        'pit_rit_v3',
        'ppc',
        'processo_seletivo',
        'professor_sv',
        'professor_titular',
        'progressao_docente',
        'projetos',
        'projetos_ensino',
        'ps',
        'rsc',
        'saude',
        'sica',
    }
)
MENUS_ACADEMICOS = frozenset({'Ensino', 'Pesquisa', 'Extensão', 'Atividades Estudantis'})
AREAS_API_ACADEMICAS = frozenset({'ensino', 'pesquisa', 'extensao'})


def edu_desativado() -> bool:
    return getattr(settings, 'DISABLE_EDU', False) is True


def area_api_oculta(area: str) -> bool:
    return edu_desativado() and area in AREAS_API_ACADEMICAS


def app_oculto(app: str) -> bool:
    return edu_desativado() and app in APPS_ACADEMICOS


def funcao_oculta(func: Any) -> bool:
    return app_oculto(func.__module__.split('.')[0])


def app_do_caminho(path: str) -> str | None:
    partes = [parte for parte in path.split('/') if parte]
    if not partes:
        return None
    if partes[0] in ('json', 'chained_select') and len(partes) > 1:
        return partes[1]
    if partes[0] == 'admin' and len(partes) > 1:
        return partes[1]
    if partes[0] == 'api':
        return None
    return partes[0]


def _trecho_api_oculto(partes: list[str]) -> bool:
    return len(partes) > 1 and partes[1] in AREAS_API_ACADEMICAS


def _breadcrumb_oculto(partes: list[str]) -> bool:
    if len(partes) < 2 or partes[1] != 'breadcrumbs_reset':
        return False
    return any(parte in APPS_ACADEMICOS for parte in partes[2:])


def caminho_oculto(path: str) -> bool:
    if not edu_desativado():
        return False
    partes = [parte for parte in path.split('/') if parte]
    if not partes:
        return False
    if partes[0] == 'api':
        return _trecho_api_oculto(partes)
    if partes[0] == 'djtools':
        return _breadcrumb_oculto(partes)
    app = app_do_caminho(path)
    return bool(app) and app in APPS_ACADEMICOS


def item_menu_oculto(item: dict[str, Any]) -> bool:
    if not edu_desativado():
        return False
    raiz = (item.get('hierarchy') or '').split('::', 1)[0]
    if raiz in MENUS_ACADEMICOS:
        return True
    return caminho_oculto(item.get('url') or '')


def menu_visivel(itens: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    if not edu_desativado():
        return list(itens)
    return [item for item in itens if not item_menu_oculto(item)]


def ocultar_no_admin() -> None:
    """Tira os apps acadêmicos da página inicial do admin."""
    from django.contrib import admin

    if getattr(admin.site, '_suap_apps_ocultos', False):
        return
    original = admin.site.get_app_list

    def get_app_list(request: Any, app_label: str | None = None) -> list:
        app_list = original(request, app_label)
        if not edu_desativado():
            return app_list
        return [app for app in app_list if app.get('app_label') not in APPS_ACADEMICOS]

    admin.site.get_app_list = get_app_list
    admin.site._suap_apps_ocultos = True
