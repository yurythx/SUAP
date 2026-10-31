# ruff: noqa: F403, F405, F821
"""
settings.py de produção — Autarquia / deploy Docker.
Baseado em suap/settings_sample.py. DISABLE_EDU (env) esconde a parte
acadêmica sem tirá-la do INSTALLED_APPS. Ver djtools.modulos_ocultos.
"""

import os
import sys

from .settings_base import *

DEBUG = os.environ.get('DEBUG', 'False') == 'True'

TEMPLATES[0]['OPTIONS']['debug'] = DEBUG
PIPELINE['PIPELINE_ENABLED'] = not DEBUG

if DEBUG:
    LOG_LEVEL = 'INFO'
    LOGGING['root']['level'] = LOG_LEVEL
    LOGGING['loggers']['django.db.backends'] = {'level': LOG_LEVEL, 'handlers': ['console'], 'propagate': False}
    INTERNAL_IPS = ['127.0.0.1']
    if not EMAIL_HOST:
        EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'djtools.core.mail.backends.debug.EmailBackend')
        EMAIL_LOGGING = os.environ.get('EMAIL_LOGGING', 'file')
else:
    CSRF_FAILURE_VIEW = 'comum.views.csrf_failure'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME', 'suap'),
        'USER': os.environ.get('DATABASE_USER', 'suap'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
        'HOST': os.environ.get('DATABASE_HOST', 'db'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
        'DISABLE_SERVER_SIDE_CURSORS': os.environ.get('DISABLE_SERVER_SIDE_CURSORS', 'False') == 'True',
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
    },
}

PRE_INSTALLED_APPS_SUAP = (
    os.environ.get('PRE_INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('PRE_INSTALLED_APPS_SUAP', '').split(',')) or PRE_INSTALLED_APPS_SUAP
)

# Módulos SUAP: lista do settings_base, podendo ser sobrescrita por env.
INSTALLED_APPS_SUAP = (
    os.environ.get('INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('INSTALLED_APPS_SUAP', '').split(',')) or INSTALLED_APPS_SUAP
)

POS_INSTALLED_APPS_SUAP = (
    os.environ.get('POS_INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('POS_INSTALLED_APPS_SUAP', '').split(',')) or POS_INSTALLED_APPS_SUAP
)

INSTALLED_APPS = PRE_INSTALLED_APPS_SUAP + INSTALLED_APPS_SUAP + POS_INSTALLED_APPS_SUAP

if USE_SENTRY:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_URL,
        integrations=[DjangoIntegration(), RedisIntegration(), CeleryIntegration()],
        release=SUAP_VERSION,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILE_RATE,
        profile_lifecycle='trace',
        send_default_pii=True,
    )
    sentry_sdk.set_tag('suap.server.name', SERVER_ALIAS)

if USE_REDIS:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'session'
    CACHES = {
        'default': {
            'BACKEND': 'djtools.core.cache.CustomRedisCache',
            'LOCATION': os.environ.get('REDIS_LOCATION', 'redis://redis:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'PASSWORD': os.environ.get('REDIS_PASSWORD', ''),
            },
        },
        'session': {
            'BACKEND': 'djtools.core.cache.CustomRedisCache',
            'LOCATION': os.environ.get('SESSION_LOCATION', 'redis://redis:6379/2'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'PASSWORD': os.environ.get('REDIS_PASSWORD', ''),
            },
        },
    }

if USE_CELERY:
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/3')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/4')
    CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Overrides de teste (pytest / behave)
if 'test_behave' in sys.argv or 'pytest' in sys.modules:
    USE_CELERY = False
    DEBUG = False
    USE_REDIS = False
    USE_SENTRY = False
