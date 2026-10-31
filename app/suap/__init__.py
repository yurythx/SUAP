from .celery_app import app as celery_app

__all__ = ('celery_app',)

import sys

from django.conf import settings

for command in ('makemigrations', 'migrate', 'sync'):
    if command in sys.argv:
        settings.INSTALLED_APPS = settings.PRE_INSTALLED_APPS_SUAP + settings.APPS_SUAP + settings.POS_INSTALLED_APPS_SUAP
