from pathlib import Path

from django.conf import settings
from ninja_extra import NinjaExtraAPI
from ninja_jwt.controller import NinjaJWTDefaultController

from djtools.modulos_ocultos import area_api_oculta

api = NinjaExtraAPI(title='SUAP API', version='1.0.0', docs_url='docs/')

api.register_controllers(NinjaJWTDefaultController)

api.add_router('', 'djtools.ninja.router.deprecated_router')

BASE_DIR = Path(settings.BASE_DIR)

for area in [
    'rh',
    'ensino',
    'ti',
    'midia',
    'administracao',
    'pesquisa',
    'institucional',
    'eventos',
    'extensao',
    'terminais',
    'rsc_tae',
    'pnp',
    'pgd2',
]:
    if area_api_oculta(area):
        continue
    api_path = BASE_DIR / 'api' / 'endpoints' / f'{area}.py'
    if api_path.exists():
        endpoints = __import__(f'api.endpoints.{area}', fromlist=['api.endpoints'])
        router = getattr(endpoints, 'router', None)
        if router:
            api.add_router(router.api_url_prefix, router)
