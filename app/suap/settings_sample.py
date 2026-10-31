# ruff: noqa: F403, F405, F821
"""
Arquivo modelo do settings.py.
Aqui deve conter apenas o que há de diferente em relação ao settings_base.py,
como por exemplo senhas e outros dados sigilosos.
"""

import sys

from .settings_base import *

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

TEMPLATES[0]['OPTIONS']['debug'] = DEBUG
PIPELINE['PIPELINE_ENABLED'] = not DEBUG

if DEBUG:
    LOG_LEVEL = 'INFO'
    LOGGING['root']['level'] = LOG_LEVEL
    LOGGING['loggers']['django.db.backends'] = {'level': LOG_LEVEL, 'handlers': ['console'], 'propagate': False}
    INTERNAL_IPS = ['127.0.0.1']
    SILKY_PYTHON_PROFILER = True
    SILKY_PYTHON_PROFILER_BINARY = True
    MIDDLEWARE += (
        #    'debug_toolbar.middleware.DebugToolbarMiddleware',
        #     'silk.middleware.SilkyMiddleware',
    )
    POS_INSTALLED_APPS_SUAP += (
        #    'debug_toolbar',
        #    'silk',
    )
    if not EMAIL_HOST:
        EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'djtools.core.mail.backends.debug.EmailBackend')
        EMAIL_LOGGING = os.environ.get('EMAIL_LOGGING', 'file')
else:
    CSRF_FAILURE_VIEW = 'comum.views.csrf_failure'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME', 'suap_dev'),
        'USER': os.environ.get('DATABASE_USER', 'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
        'HOST': os.environ.get('DATABASE_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
        'DISABLE_SERVER_SIDE_CURSORS': os.environ.get('DISABLE_SERVER_SIDE_CURSORS', 'False') == 'True',
    },
}

PRE_INSTALLED_APPS_SUAP = (
    os.environ.get('PRE_INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('PRE_INSTALLED_APPS_SUAP', '').split(',')) or PRE_INSTALLED_APPS_SUAP
)

# Defina os módulos do suap nessa propriedade (exceto djtools)
INSTALLED_APPS_SUAP = os.environ.get('INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('INSTALLED_APPS_SUAP', '').split(',')) or INSTALLED_APPS_SUAP
# Descomente a linha a seguir para executar o SUAP apenas com as aplicações Comum e Rh
# INSTALLED_APPS_SUAP = ('comum', 'rh')

POS_INSTALLED_APPS_SUAP = (
    os.environ.get('POS_INSTALLED_APPS_SUAP', '') and tuple(os.environ.get('POS_INSTALLED_APPS_SUAP', '').split(',')) or POS_INSTALLED_APPS_SUAP
)

# REPRESENTACAO_CONCEITUAL = {'A':100, 'B':80, 'C':60, 'D':0}

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
        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
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
            'LOCATION': os.environ.get('REDIS_LOCATION', 'redis://127.0.0.1:6379/1'),
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient', 'PASSWORD': os.environ.get('REDIS_PASSWORD', '')},
        },
        'session': {
            'BACKEND': 'djtools.core.cache.CustomRedisCache',
            'LOCATION': os.environ.get('SESSION_LOCATION', 'redis://127.0.0.1:6379/2'),
            'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient', 'PASSWORD': os.environ.get('SESSION_PASSWORD', '')},
        },
    }

# ESSE TRECHO É PARA GARANTIR QUE TODOS OS MODULOS ESPECIFICADOS AQUI NO PRE_INSTALLED_APPS_SUAP OU INSTALLED_APPS_SUAP OU
#  POS_INSTALLED_APPS_SUAP ESTEJAM REPLICADOS EM INSTALLED_APPS
INSTALLED_APPS = PRE_INSTALLED_APPS_SUAP + INSTALLED_APPS_SUAP + POS_INSTALLED_APPS_SUAP

BEHAVE_CHROME_HEADLESS = os.environ.get('BEHAVE_CHROME_HEADLESS', 'True') != 'False'

BEHAVE_AUTO_DOC = os.environ.get('BEHAVE_AUTO_DOC', 'False') == 'True'
BEHAVE_AUTO_DOC_PATH = os.environ.get('BEHAVE_AUTO_DOC_PATH', os.path.join(BASE_DIR, 'deploy/media/documentacao'))
BEHAVE_AUTO_MOCK = os.environ.get('BEHAVE_AUTO_MOCK', 'False') == 'True'
BEHAVE_AUTO_MOCK_PATH = os.environ.get('BEHAVE_AUTO_MOCK_PATH', os.path.join(BASE_DIR, 'deploy/media/sql'))
BEHAVE_DEBUG_ON_ERROR = os.environ.get('BEHAVE_DEBUG_ON_ERROR', 'False') == 'True'

if USE_CELERY:
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/3')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/4')
    CELERY_ACCEPT_CONTENT = ['application/json']
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-task_serializer
    CELERY_TASK_SERIALIZER = 'json'
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#std:setting-result_serializer
    CELERY_RESULT_SERIALIZER = 'json'
    # http://docs.celeryproject.org/en/latest/userguide/configuration.html#beat-scheduler
    CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
    TASK_QUEUES_CELERY = {}
    tasks = os.environ.get('CELERY_TASK_QUEUES', '') and os.environ.get('CELERY_TASK_QUEUES', '').split(':') or ()
    for task in tasks:
        key, value = task.split(',')
        TASK_QUEUES_CELERY[key] = value

if 'api' not in INSTALLED_APPS:
    del (OAUTH2_PROVIDER_APPLICATION_MODEL, OAUTH2_PROVIDER)

if 'ldap_backend' not in INSTALLED_APPS:
    AUTHENTICATION_BACKENDS = os.environ.get('AUTHENTICATION_BACKENDS', 'django.contrib.auth.backends.ModelBackend').split(',')

TEST_DATABASE_NAME = os.environ.get('TEST_DATABASE_NAME', 'test_suap_dev')
DATABASES['default']['TEST'] = {
    'NAME': TEST_DATABASE_NAME,
    'CONN_MAX_AGE': None,
    'OPTIONS': {
        'connect_timeout': 10,
    },
    'MIGRATE': False,
}

# As configurações de testes devem vir no final do arquivo para sobrescrever todas as outras configurações
# ``'pytest' in sys.modules``: o ``.env`` (achado por ``load_dotenv`` inclusive em diretório pai) traz
# ``USE_CELERY=True`` e, sem worker, o decorator ``@task`` (djtools/assincrono) enfileira e a tarefa nunca
# roda. Checado no settings, e não no conftest, porque o pytest-django faz ``django.setup()`` antes dele e
# o decorator lê o valor no import.
if 'test_behave' in sys.argv or 'pytest' in sys.modules:
    DEBUG = False
    STORAGES['default']['BACKEND'] = 'djtools.storages.storage.FileSystemStoragePlus'
    CSRF_COOKIE_NAME = 'csrftoken'
    SESSION_COOKIE_NAME = 'sessionid'
    USE_REDIS = False
    USE_SENTRY = False
    USE_CELERY = False
    OAUTH2_PROVIDER_APPLICATION_MODEL = 'oauth2_provider.Application'
    OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = 'oauth2_provider.AccessToken'
    OAUTH2_PROVIDER_ID_TOKEN_MODEL = 'oauth2_provider.IDToken'
    OAUTH2_PROVIDER_GRANT_MODEL = 'oauth2_provider.Grant'
    OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = 'oauth2_provider.RefreshToken'
