import datetime
import json
import logging
import os
import tempfile
from os import makedirs
from os.path import abspath, dirname, exists, join

from dotenv import load_dotenv

load_dotenv()


PUBLIC_INDEX_URL = os.environ.get('PUBLIC_INDEX_URL', '/')

TIPO_ARVORE_SETORES = os.environ.get('TIPO_ARVORE_SETORES', 'SUAP')  # 'SUAP|SIAPE'

USE_REDIS = os.environ.get('USE_REDIS', 'False') == 'True'
USE_SENTRY = os.environ.get('USE_SENTRY', 'False') == 'True'
USE_CELERY = os.environ.get('USE_CELERY', 'False') == 'True'
USE_ELASTICSEARCH = os.environ.get('USE_ELASTICSEARCH', 'False') == 'True'
USE_HISTORY = os.environ.get('USE_HISTORY', 'False') == 'True'
USE_EDU_LOG = os.environ.get('USE_EDU_LOG', 'True') == 'True'
USE_PWA = os.environ.get('USE_PWA', 'False') == 'True'

BASE_DIR = dirname(dirname(abspath(__file__)))

try:
    with open(join(BASE_DIR, 'VERSION')) as f:
        SUAP_VERSION = f.read().strip()
except FileNotFoundError, OSError:
    SUAP_VERSION = '0.0.1'


SUAP_ENVIRONMENT = os.environ.get('SUAP_ENVIRONMENT', default='production')  # dev|production|homolog|test
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000')
SERVER_ALIAS = os.environ.get('SERVER_ALIAS', 'suap')
PROJECT_NAME = BASE_DIR.split('/')[-1]

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

SSL_HEADER = os.environ.get('SECURE_PROXY_SSL_HEADER', 'HTTP_X_FORWARDED_PROTO,https')
SECURE_PROXY_SSL_HEADER = SSL_HEADER and SSL_HEADER.split(',') or None

EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = os.environ.get('EMAIL_PORT', '')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_SUBJECT_PREFIX = '[suap-erros] '
EMAIL_LOGGING = os.environ.get('EMAIL_LOGGING', 'db').split(',')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'suap@naoresponder.ifrn.edu.br')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'djtools.core.mail.backends.smtp.EmailBackend')
DEBUG_SMTP_CONNECTION = os.environ.get('DEBUG_SMTP_CONNECTION', 'False') == 'True'

CLIENT_IP_HEADERS = os.environ.get('CLIENT_IP_HEADERS', 'HTTP_X_REAL_IP,HTTP_X_FORWARDED_FOR,REMOTE_ADDR').split(',')

admins = os.environ.get('ADMINS', 'Admin,admin@suap.net').split(':')
ADMINS = []
for admin in admins:
    ADMINS.append(admin.split(','))

MONTH_DAY_FORMAT = r'd \d\e F'
YEAR_MONTH_FORMAT = r'F \d\e Y'

DATABASES = {
    'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'suap', 'USER': 'postgres', 'PASSWORD': '', 'HOST': '127.0.0.1', 'PORT': '5432'}
}
DISABLE_SERVER_SIDE_CURSORS = os.environ.get('DISABLE_SERVER_SIDE_CURSORS', 'False') == 'True'

SUAP_TESTS = {}
SUAP_TESTS['SALVAR_CENARIO'] = False
SUAP_TESTS['MANTER_JSON'] = False

TIME_ZONE = os.environ.get('TIME_ZONE', 'America/Recife')
LANGUAGE_CODE = 'pt-br'
DATE_FORMAT = 'd/m/Y'
DATE_INPUT_FORMATS = ('%Y-%m-%d', '%d/%m/%Y')
DATETIME_FORMAT = 'd/m/Y H:i'
DATETIME_INPUT_FORMATS = ('%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M')

FORMS_URLFIELD_ASSUME_HTTPS = True

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.PipelineFinder',
)

CACHES = {
    'default': {
        'BACKEND': 'djtools.core.cache.CustomLocMemCache',
    }
}

STORAGES = {
    'default': {
        'BACKEND': os.environ.get('DEFAULT_FILE_STORAGE', 'djtools.storages.storage.FileSystemStoragePlus'),
    },
    'staticfiles': {'BACKEND': os.environ.get('STATICFILES_STORAGE', 'djtools.storages.pipeline.CacheControlPipelineStorage')},
}

AWS_S3_SIGNATURE_VERSION = os.environ.get('AWS_S3_SIGNATURE_VERSION', 's3v4')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-2')
AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN', None)
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', 'http://localhost:9000')  # 'http://minio.suap.instituicao.edu.br:9000'

AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', 'admin')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', 'miniopassword')

AWS_MEDIA_BUCKET_NAME = os.environ.get('AWS_MEDIA_BUCKET_NAME', 'media')
AWS_PRIVATE_MEDIA_BUCKET_NAME = os.environ.get('AWS_PRIVATE_MEDIA_BUCKET_NAME', 'media')
AWS_STATIC_BUCKET_NAME = os.environ.get('AWS_STATIC_BUCKET_NAME', 'static')
AWS_TEMP_BUCKET_NAME = os.environ.get('AWS_TEMP_BUCKET_NAME', 'temp')
AWS_QUERYSTRING_EXPIRE = int(os.environ.get('AWS_QUERYSTRING_EXPIRE', '86400'))  # padrao 24h

SENTRY_URL = os.environ.get('SENTRY_URL', 'http://token@sentry.ifrn.local/3')
SENTRY_ENVIRONMENT = os.environ.get('SENTRY_ENVIRONMENT', 'production')
SENTRY_SAMPLE_RATE = float(os.environ.get('SENTRY_SAMPLE_RATE', '0.0'))
SENTRY_PROFILE_RATE = float(os.environ.get('SENTRY_PROFILE_RATE', '0.0'))
SENTRY_JS = os.environ.get('SENTRY_JS', 'https://sentry.ifrn.local/js-sdk-loader/token.min.js')

STATIC_ROOT = join(BASE_DIR, 'static')
STATIC_URL = '/static/'
ADMIN_MEDIA_PREFIX = '/static/admin/'

MEDIA_ROOT = join(BASE_DIR, 'deploy/media')
TEMP_DIR = join(MEDIA_ROOT, 'tmp')
tempfile.tempdir = TEMP_DIR
FILE_UPLOAD_TEMP_DIR = TEMP_DIR

if not exists(TEMP_DIR):
    makedirs(TEMP_DIR)
MEDIA_URL = '/media/'
TEMP_URL = '/media/tmp/'
NOCAPTCHA = True

# Arquivos de midia (futuramente as midias serão movidas para uma particao específica)
MEDIA_PUBLIC = join(BASE_DIR, 'deploy/media/public-media')
MEDIA_PRIVATE = join(BASE_DIR, 'deploy/media/private-media')

SECRET_KEY = os.environ.get('SECRET_KEY', 'xru6&52s_b&vv5%!f@hyd)m&059z^x54q(s-=2-x9b1up(xiwn')

MIDDLEWARE = (
    # Middlewares do django
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # 'djtools.middleware.session_middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.admindocs.middleware.XViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    # Middlewares do suap
    'djtools.middleware.session_lock.SessionLock',
    'djtools.middleware.userinfo.UserInfoMiddleware',
    'djtools.middleware.threadlocals.ThreadLocals',
    'djtools.middleware.govbr.Middleware',
    'djtools.middleware.usuario_sem_setor.UsuarioSemSetorMiddleware',
    'djtools.middleware.change_process_name.ChangeProcessNameMiddleware',
    'reversion.middleware.RevisionMiddleware',
    # 'djtools.middleware.previnir_multiplos_logins.UserRestrict',
    'djtools.middleware.minify_html.MinifyHTMLMiddleware',
    # deve ser removido assim que o problema no pacote django-pipeline for resolvido
    # 'edu.middleware.titulacao.InformarTitulacaoMiddleware',
    'djtools.middleware.http_exception.HttpResponseConflictMiddleware',
    'djtools.middleware.locale.LocaleMiddlewarePlus',
    # Perfil prefeitura: 404 nas URLs acadêmicas quando DISABLE_EDU=True.
    'djtools.middleware.modulos_ocultos.ModulosOcultosMiddleware',
)

# Apps acadêmicos permanecem instalados. A flag só esconde menu, quadros, API e URLs.
DISABLE_EDU = os.environ.get('DISABLE_EDU', 'False') == 'True'

X_FRAME_OPTIONS = 'SAMEORIGIN'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

ROOT_URLCONF = 'suap.urls'

LOGIN_URL = '/accounts/login/'
LOGOUT_URL = '/comum/logout/'
LOGIN_REDIRECT_URL = '/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [f'{BASE_DIR}/templates', f'{BASE_DIR}/comum/templates', f'{BASE_DIR}/djtools/templates/adminutils', BASE_DIR],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': [
                'djtools.templatetags.filters.utils',
                'djtools.templatetags.filters.ajax',
                'djtools.templatetags.filters.sanitize',
                'djtools.templatetags.tags.pagination',
                'djtools.templatetags.tags.renders',
                'djtools.templatetags.tags.utils',
            ],
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'djtools.context_processor.suap_context_processor',
            ],
            'debug': True,
        },
    }
]

LANGUAGES = []
langs = os.environ.get('LANGUAGES', 'pt-br:Português,en:English,es:Español').split(',')
for lang in langs:
    LANGUAGES.append(lang.split(':'))

LOCALE_PATHS = [
    join(BASE_DIR, 'locale'),
]

PRE_INSTALLED_APPS_SUAP = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'djtools',  # O djtools deve vir antes de django.contrib.admin
    'django.contrib.admin',
    'django_recaptcha',
    'django.contrib.postgres',
)

# Todas as apps inclusas na lista abaixo serão testadas ao executar o comando test_suap
APPS_SUAP = (
    'comum',
    'rh',
    'almoxarifado',
    'edu',
    'catalogo_provedor_servico',
    'gestao',
    'patrimonio',
    'ponto',
    'centralservicos',
    'contracheques',
    'protocolo',
    'frota',
    'financeiro',
    'ldap_backend',
    'chaves',
    'estacionamento',
    'cursos',
    'remanejamento',
    'contratos',
    'planejamento',
    'convenios',
    'orcamento',
    'materiais',
    'projetos',
    'compras',
    'pedagogia',
    'ae',
    'cnpq',
    'pdi',
    'cpa',
    'processo_seletivo',
    'saude',
    'arquivo',
    'microsoft',
    'acervo_academico',
    'ferias',
    'eleicao',
    'enquete',
    'rsc',
    'progressoes',
    'estagios',
    'portaria',
    'pesquisa',
    'avaliacao_integrada',
    'clipping',
    'temp_rh2',
    'acumulocargo',
    'plan_v2',
    'demandas',
    'api',
    'professor_titular',
    'ps',
    'etep',
    'documento_eletronico',
    'processo_eletronico',
    'avaliacao_cursos',
    'eventos',
    'encceja',
    'egressos',
    'gerenciador_projetos',
    'pit_rit',
    'pit_rit_v2',
    'pit_rit_v3',
    'plan_estrategico',
    'integracao_wifi',
    'acompanhamentofuncional',
    'conectagov_pen',
    'sica',
    'demandas_externas',
    'tesouro_gerencial',
    'boletim_servico',
    'auxilioemergencial',
    'licenca_capacitacao',
    'erros',
    'pdp_ifrn',
    'processmining',
    'siads',
    'labfisico',
    'labvirtual',
    'projetos_ensino',
    'pgd',
    'ppc',
    'pafc',
    'calculos_pagamentos',
    'progressao_docente',
    'terminais',
    'solenidades',
    'pgd2',
    'auditoria',
    'beat',
    'professor_sv',
    'sigepe_ocorrencias',
    'dados_abertos',
    'rsc_tae',
    'pnp',
)

INSTALLED_APPS_SUAP = tuple(APPS_SUAP)

POS_INSTALLED_APPS_SUAP = (
    'django_extensions',
    'django_tables2',
    'tinymce',
    'reversion',  # https://github.com/etianen/django-reversion
    'reversion_compare',  # https://github.com/jedie/django-reversion-compare
    'corsheaders',
    'sass_processor',
    'pipeline',
    # Documento e Processo Eletrônico
    'django_fsm',
    'crispy_forms',
    'mptt',
    'formtools',
    'oauth2_provider',
    'django_celery_beat',
    'ninja_extra',  # ninja api
)

INSTALLED_APPS = PRE_INSTALLED_APPS_SUAP + INSTALLED_APPS_SUAP + POS_INSTALLED_APPS_SUAP

# CSRF
TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', None)
CSRF_TRUSTED_ORIGINS = TRUSTED_ORIGINS and TRUSTED_ORIGINS.split(',') or ['https://*.br', 'http://*.br']
CSRF_COOKIE_HTTPONLY = os.environ.get('CSRF_COOKIE_HTTPONLY', 'True') == 'True'
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False') == 'True'
CSRF_COOKIE_NAME = os.environ.get('CSRF_COOKIE_NAME', 'csrftoken')
CSRF_COOKIE_AGE = (30 * 24 * 60 * 60) - (3 * 60 * 60)  # 1 mês de acordo com a demanda #1133 -3 horas do horário de verão


# TINYMCE_DEFAULT_CONFIG = {
#     'height': 600,
#     'width': '100%',
#     'menubar': True,
#     'plugins': """
#         advlist autolink lists link image charmap print preview anchor
#         searchreplace visualblocks code fullscreen insertdatetime media
#         table paste code help wordcount
#     """,
#     'toolbar': """
#     """,
#     'fontsize_formats': '8pt 10pt 12pt 14pt 18pt 24pt 36pt',
#     'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
#     'style_formats': [
#         {'title': 'Line height 1', 'block': 'p', 'styles': {'line-height': '1'}},
#         {'title': 'Line height 1.5', 'block': 'p', 'styles': {'line-height': '1.5'}},
#         {'title': 'Line height 2', 'block': 'p', 'styles': {'line-height': '2'}},
#         {'title': 'Text indent', 'block': 'p', 'styles': {'text-indent': '2em'}},
#     ],
#     'image_title': True,
#     'automatic_uploads': True,
#     'file_picker_types': 'image',
#     "language": "pt_BR",
# }

# settings.py

TINYMCE_DEFAULT_CONFIG = {
    # NÃO definir 'selector': o django-tinymce usa o `target` do textarea de cada
    # campo. Um selector fixo (ex.: o de demonstração 'textarea#open-source-plugins')
    # faz o init_tinymce.js mirar um elemento inexistente e o editor não renderiza.
    # TinyMCE >= 6.8 exige license_key; 'gpl' silencia o aviso da versão self-hosted.
    'license_key': 'gpl',
    'promotion': False,  # remove o botão "Upgrade" / promoção do Tiny Cloud
    'height': 600,
    'width': '100%',
    'toolbar_sticky': True,  # fixa a barra no topo ao rolar
    'toolbar_mode': 'sliding',
    'menubar': False,
    'autosave_interval': '30s',
    # Booleano de verdade: a string 'true' chega ao JS como "true" e o TinyMCE a rejeita
    # ("The value must be a boolean"), avisando no console — o que derruba os testes do behave.
    'autosave_ask_before_unload': True,
    # Plugins necessários pros botões abaixo (apenas plugins válidos no TinyMCE 6;
    # `paste` foi incorporado ao core e não existe mais como plugin).
    'plugins': (
        'advlist autolink lists link image charmap preview anchor '
        'searchreplace visualblocks code fullscreen media '
        'table help wordcount pagebreak quickbars importcss emoticons'
    ),
    # Formato persistido único para todos os editores. Cada contexto paginado
    # define como a classe page-break deve ser renderizada.
    'pagebreak_separator': '<div class="page-break"></div>',
    'external_plugins': {
        'case': '/static/tinymce/plugins/case/plugin.min.js',
        # Format Painter próprio: o plugin oficial é premium e não carrega no GPL.
        'formatpainter': '/static/tinymce/plugins/formatpainter/plugin.min.js',
    },
    'toolbar': (
        'undo redo | document_styles | blocks fontfamily fontsize case | '
        'bold italic underline strikethrough | '
        'align numlist bullist | subscript superscript | '
        'link image tabelasuap | lineheight outdent indent | '
        'forecolor backcolor removeformat formatpainter | '
        'link unlink anchor | media | '
        'charmap emoticons | pagebreak | '
        'searchreplace | preview | fullscreen | code'
    ),
    'formats': {
        'simples': {'block': 'p', 'styles': {'text-indent': '0'}},
        'paragrafo': {'block': 'p', 'styles': {'text-indent': '3em'}},
    },
    # Estilos e fontes
    # As regras de tabela aqui devem espelhar as de documento_eletronico/templates/
    # conteudo_documento.html (CSS de impressão), para o editor renderizar a tabela
    # igual ao documento final. Sem elas, o padding default da célula + a margem dos
    # <p> dentro da célula deixavam as linhas da tabela bem mais altas que o texto.
    'content_style': (
        'body { font-family: Calibri, Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; }'
        'table { border-collapse: collapse; }'
        # Sem border-style: solid, qualquer largura definida pelo editor vira 0.
        # Restringe a largura zero a border ausente, vazio ou zero. Valores positivos
        # usam o presentational hint do navegador; estilos inline em px prevalecem.
        'table, table td, table th { border-style: solid; border-color: #000; }'
        'table:not([border]), table:not([border]) td, table:not([border]) th, '
        'table[border=""], table[border=""] td, table[border=""] th, '
        'table[border="0"], table[border="0"] td, table[border="0"] th { border-width: 0; }'
        # overflow-wrap/word-wrap: quebra o texto dentro da célula quando não cabe,
        # evitando que ele estoure/sobreponha (word-wrap é o alias que o WebKit antigo
        # do wkhtmltopdf entende; overflow-wrap é o nome padrão pros navegadores).
        'table td, table th { padding: 1px 6px; vertical-align: top; overflow-wrap: break-word; word-wrap: break-word; }'
        'table td > p, table th > p { margin: 0; }'
    ),
    # Reabilita os campos de espaçamento/preenchimento/borda no diálogo de tabela
    # (no TinyMCE 6 vêm desligados por padrão), restaurando o ajuste fino que o
    # editor anterior (CKEditor) permitia via "Propriedades da tabela".
    'table_appearance_options': True,
    'table_advtab': True,
    'table_cell_advtab': True,
    'table_default_styles': {'border-collapse': 'collapse', 'width': '100%'},
    # Restaura um dropdown de estilos prontos (perdido na migração do CKEditor),
    # mantendo também os formatos padrão do TinyMCE (style_formats_merge).
    'style_formats_merge': True,
    'style_formats': [
        {'title': 'Simples', 'format': 'simples'},
        {'title': 'Parágrafo', 'format': 'paragrafo'},
        {'title': 'Título 1', 'block': 'h1'},
        {'title': 'Título 2', 'block': 'h2'},
        {'title': 'Título 3', 'block': 'h3'},
        {'title': 'Tabela compacta', 'selector': 'table', 'styles': {'border-collapse': 'collapse', 'width': '100%'}},
        {'title': 'Célula sem espaçamento', 'selector': 'td,th', 'styles': {'padding': '1px 6px'}},
    ],
    'fontsize_formats': '8px 9px 10px 11px 12px 14px 16px 18px 24px 36px 48px',
    'line_height_formats': '0.5 0.8 0.9 1 1.1 1.2 1.3 1.4 1.5 2',
    'font_family_formats': (
        'Calibri=Calibri,Helvetica,Arial,sans-serif;'
        'Arial=Arial,Helvetica,sans-serif;'
        'Times New Roman=Times New Roman,Times,serif;'
        'Georgia=Georgia,serif;'
        'Courier New=Courier New,Courier,monospace;'
        'Inter=Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif'
    ),
    # Uploads / mídia
    'image_title': True,
    'automatic_uploads': True,
    'file_picker_types': 'image',
    # O arquivo pt_BR.js é fornecido pelo pacote django-tinymce via staticfiles.
    'language': 'pt_BR',
    'language_url': STATIC_URL + 'tinymce/langs/pt_BR.js',
}

TINYMCE_CONFIGS = {
    # O config base já vem de TINYMCE_DEFAULT_CONFIG em _get_tinymce_config;
    # aqui 'default' apenas não acrescenta overrides.
    'default': {},
    'basic_suap': {
        'menubar': False,
        'toolbar': (
            'undo redo | blocks fontfamily fontsize case | '
            'bold italic underline strikethrough | '
            'alignleft aligncenter alignright alignjustify | '
            'numlist bullist | outdent indent | '
            'subscript superscript | forecolor backcolor removeformat formatpainter | '
            'link image tabelasuap | pagebreak | '
            'searchreplace preview fullscreen | code'
        ),
    },
    'basico_sem_imagem': {
        'menubar': False,
        'plugins': (
            'advlist autolink lists link charmap preview anchor '
            'searchreplace visualblocks code fullscreen '
            'table help wordcount pagebreak quickbars importcss'
        ),
        'toolbar': (
            'undo redo | blocks fontfamily fontsize case | '
            'bold italic underline strikethrough | '
            'alignleft aligncenter alignright alignjustify | '
            'numlist bullist | outdent indent | '
            'subscript superscript | forecolor backcolor removeformat formatpainter | '
            'link tabelasuap | pagebreak | '
            'searchreplace preview fullscreen | code'
        ),
        'image_title': False,
        'automatic_uploads': False,
        'file_picker_types': '',
    },
    'custom_ppc': {
        'menubar': False,
        'toolbar': (
            'undo redo | blocks fontsize case | '
            'bold italic underline strikethrough | '
            'numlist bullist | '
            'subscript superscript | removeformat formatpainter | '
            'link image tabelasuap | pagebreak | '
            'searchreplace preview fullscreen | code'
        ),
    },
}


AUTHENTICATION_BACKENDS = os.environ.get(
    'AUTHENTICATION_BACKENDS', 'djtools.contrib.auth.backends.ModelBackendPlus,ldap_backend.ldap_backend.LdapBackend'
).split(',')
DATABASE_ROUTERS = os.environ.get('DATABASE_ROUTERS', '')  # substituir por 'ldap_backend.router.SuapRouter' ao usar o módulo do guacamole
DATABASE_ROUTERS = DATABASE_ROUTERS and DATABASE_ROUTERS.split(',') or []

AUTH_USER_MODEL = 'comum.User'

SESSION_ENGINE = 'django.contrib.sessions.backends.file'
SESSION_FILE_PATH = join(BASE_DIR, 'deploy/sessions')

SESSION_COOKIE_AGE = 1 * 24 * 60 * 60  # tempo em segundos
SESSION_COOKIE_NAME = os.environ.get('SESSION_COOKIE_NAME', 'sessionid')
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'

SUAP_CONTROL_COOKIE_NAME = os.environ.get('SUAP_CONTROL_COOKIE_NAME', 'suap-control')

SECURE_BROWSER_XSS_FILTER = True


logging.captureWarnings(True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        }
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} "{asctime}" [{name}] >>> """{message}"""',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'formatter': 'verbose',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': join(BASE_DIR, 'deploy/logs/debug.log'),
        },
        'history': {
            'level': 'DEBUG',
            # WatchedFileHandler reabre o arquivo ao detectar mudança de inode (rotação do
            # logrotate). Com FileHandler, o FD persistente continuava escrevendo no arquivo
            # já renomeado e o fluentbit perdia esses registros após o Rotate_Wait.
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': join(BASE_DIR, 'deploy/logs/history/history.log'),
        },
        'email': {
            'level': 'DEBUG',
            # Idem history: reabre na rotação do logrotate para não escrever em arquivo órfão.
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': join(BASE_DIR, 'deploy/logs/email/email.log'),
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'py.warnings': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'behave': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'history': {
            'handlers': ['history'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'email': {
            'handlers': ['email'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

DEFAULT_DISABLED_LOGGING_APPS = [
    'TTFont',
    'fontTools.subset',
    'ttFont',
    'fontTools',
    'urllib3.connection',
    'weasyprint',
    'notifications_python_client.base',
    'suds.client',
    'health-check',
    'opensearch',
]

DISABLED_DEBUG_LOGGING_APPS = DEFAULT_DISABLED_LOGGING_APPS + os.environ.get('DISABLED_DEBUG_LOGGING_APPS', '').split(',')

for app in DISABLED_DEBUG_LOGGING_APPS:
    LOGGING['loggers'][app] = {
        'handlers': ['console'],
        'level': 'CRITICAL',
        'propagate': False,
    }

WSGI_APPLICATION = 'suap.wsgi.application'

OAUTH2_PROVIDER_APPLICATION_MODEL = os.environ.get('OAUTH2_PROVIDER_APPLICATION_MODEL', 'api.AplicacaoOAuth2')
# Os demais models swappable do django-oauth-toolkit não são substituídos pelo SUAP, mas precisam estar
# declarados: o autodetector do Django lê `getattr(settings, <swappable>)` sem default ao resolver as
# dependências das migrations (quebra o `create_db`, que roda `migrate --run-syncdb` sem migrations).
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = 'oauth2_provider.AccessToken'
OAUTH2_PROVIDER_ID_TOKEN_MODEL = 'oauth2_provider.IDToken'
OAUTH2_PROVIDER_GRANT_MODEL = 'oauth2_provider.Grant'
OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = 'oauth2_provider.RefreshToken'
OAUTH2_PROVIDER_DEVICE_GRANT_MODEL = 'oauth2_provider.DeviceGrant'
OAUTH2_PROVIDER = {
    'PKCE_REQUIRED': False,
    'REQUEST_APPROVAL_PROMPT': 'auto',
    'SCOPES': {
        'identificacao': 'Seu nome, campus e identificação/matrícula',
        'email': 'Seus endereços de e-mail (institucional, acadêmico e secundário/pessoal)',
        'contracheques': 'Seus contracheques',
        'documentos_pessoais': 'CPF, data de nascimento e sexo.',
        'integra': 'CPF e alguns outros dados dos servidores ativos para integração com o portal Integra.',
    },
    'SCOPES_BACKEND_CLASS': os.environ.get('OAUTH2_PROVIDER_SCOPES_BACKEND_CLASS', 'api.backends.SuapScopes'),
    'DEFAULT_SCOPES': ['identificacao', 'email'],
    'APPLICATION_ADMIN_CLASS': os.environ.get('OAUTH2_PROVIDER_APPLICATION_ADMIN_CLASS', 'api.admin.AplicacaoOAuth2Admin'),
    'ACCESS_TOKEN_ADMIN_CLASS': os.environ.get('OAUTH2_PROVIDER_ACCESS_TOKEN_ADMIN_CLASS', 'api.admin.AccessTokenAdmin'),
}

ACCESS_LOG = True
AUTHN_LOG = False
AUTHZ_LOG = True
ACCESS_LOG_MODULES = ['centralservicos']

# Documento Eletrônico
DOC_SECRET_KEY = 'xru6&52s_b&vv5%!f@hyd)m&059z^x54q(s-=2-x9b1up(xiwn'
CONTENT_TYPES = os.environ.get('CONTENT_TYPES', 'application/pdf').split(',')


DEFAULT_UPLOAD_ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png']
DEFAULT_UPLOAD_ALLOWED_DATA_EXTENSIONS = ['xlsx', 'xls', 'csv', 'txt']
DEFAULT_UPLOAD_ALLOWED_DOCUMENT_EXTENSIONS = ['docx', 'doc', 'pdf']
DEFAULT_UPLOAD_ALLOWED_EXTENSIONS = (
    DEFAULT_UPLOAD_ALLOWED_IMAGE_EXTENSIONS + DEFAULT_UPLOAD_ALLOWED_DATA_EXTENSIONS + DEFAULT_UPLOAD_ALLOWED_DOCUMENT_EXTENSIONS + ['zip']
)

# 1.00    MB  1024    KB  1048576     Bytes
# 2.50    MB  2560    KB  2621440     Bytes
# 5.00    MB  5120    KB  5242880     Bytes
# 10.00   MB  10240   KB  10485760    Bytes
# 20.00   MB  20480   KB  20971520    Bytes
# 50.00   MB  51200   KB  52428800    Bytes
# 100.00  MB  102400  KB  104857600   Bytes
# 250.00  MB  256000  KB  262144000   Bytes
# 500.00  MB  512000  KB  524288000   Bytes
BYTES_SIZE_1MB = 1048576
PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE = (
    int(os.environ.get('PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE', '10')) * BYTES_SIZE_1MB
)  # Padrão 10 MB

# Tamanho máximo aceitável para ser tratado diretamente na memória antes de ser enviado para o sistema de arquivos
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('FILE_UPLOAD_MAX_MEMORY_SIZE', '5')) * BYTES_SIZE_1MB  # Padrão 5 MB

# Tamanho máximo padrão para upload de arquivos
DEFAULT_FILE_UPLOAD_MAX_SIZE = int(os.environ.get('DEFAULT_FILE_UPLOAD_MAX_SIZE', '10')) * BYTES_SIZE_1MB  # Padrão 10 MB

# Tamanho máximo de informação presente num request (excluindo uploads de arquivo). Por padrão, o valor é 2.5 MB
# (2621440 bytes). Caso o tamanho exceda esse valor, será lançada uma exceção Bad Request 500 - RequestDataTooBig.
# Isso pode ocorrer nos documentos de texto criados dentro do módulo de Documento Eletrônico, uma vez que as imagens
# presentes acabam sendo texto (string base 64).
# /django/conf/global_settings.py
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('DATA_UPLOAD_MAX_MEMORY_SIZE', '100')) * BYTES_SIZE_1MB  # Padrão 100 MB

#
SIGNER_MAX_AGE = 60000
# Esse é o caminho da ferramenta usada para gerar os PDFs dos documentos criados.
# Lembrese de instalar no S.O:
# Mac OS X: brew install Caskroom/cask/wkhtmltopdf
WKHTMLTOPDF_CMD = os.environ.get('WKHTMLTOPDF_CMD', '/usr/bin/wkhtmltopdf')
# Absolute path to Ghostscript executable here or command name if Ghostscript is
# in your PATH.
GHOSTSCRIPT_CMD = os.environ.get('GHOSTSCRIPT_CMD', '/usr/bin/gs')

QPDF_CMD = os.environ.get('QPDF_CMD', '/usr/bin/qpdf')

# Configurações do CORS
CORS_ALLOW_ALL_ORIGINS = False

# Configurações do JWT
JWT_AUTH = {
    'JWT_VERIFY': True,
    'JWT_VERIFY_EXPIRATION': True,
    'JWT_ALLOW_REFRESH': True,
    'JWT_EXPIRATION_DELTA': datetime.timedelta(hours=24),
    'JWT_REFRESH_EXPIRATION_DELTA': datetime.timedelta(days=7),
    'JWT_AUTH_HEADER_PREFIX': 'JWT',
}

LPS = os.environ.get('LPS', '')
DATA_UPLOAD_MAX_NUMBER_FIELDS = None

# TEST_RUNNER = 'djtools.new_tests.runner.MyBehaveTestRunner'
TEST_INITIAL_DATA = ['djtools.new_tests.test_initial_data.start_database', 'djtools.new_tests.test_initial_data.initial_data']
TEST_COMMON_STEPS = [join(BASE_DIR, 'djtools/new_tests/common_steps')]

BEHAVE_CHROME_HEADLESS = os.environ.get('BEHAVE_CHROME_HEADLESS', 'True') != 'False'
BEHAVE_WINDOW_SIZE = '1920,1080'
BEHAVE_WINDOW_POSITION = ''

BEHAVE_AUTO_DOC = False
BEHAVE_AUTO_DOC_PATH = join(MEDIA_ROOT, 'documentacao')
BEHAVE_AUTO_MOCK = False
BEHAVE_AUTO_MOCK_PATH = ''

USA_LEITOR_BIOMETRICO_GRIAULE = True

PIPELINE = {
    'JS_COMPRESSOR': 'pipeline.compressors.jsmin.JSMinCompressor',
    'COMPILERS': ('djtools.pipeline.LibSassCompiler',),
    'CSS_COMPRESSOR': 'pipeline.compressors.NoopCompressor',
    'JAVASCRIPT': {
        'jquery': {'source_filenames': ('comum/js/jquery.min.js',), 'output_filename': 'js/jquery.min.js'},
        'jquery.ui.custom': {'source_filenames': ('comum/js/jquery.ui.custom.min.js',), 'output_filename': 'js/jquery.ui.custom.min.js'},
        'nouislider': {'source_filenames': ('comum/js/nouislider.min.js',), 'output_filename': 'js/nouislider.min.js'},
        'main': {'source_filenames': ('comum/js/main.js',), 'output_filename': 'js/main.js'},
        'sentry': {'source_filenames': ('comum/js/sentry.js',), 'output_filename': 'js/sentry.js'},
        'highlight': {'source_filenames': ('comum/js/highlight.js',), 'output_filename': 'js/highlight.js'},
        'login': {'source_filenames': ('comum/js/login.js',), 'output_filename': 'js/login.js'},
        'index': {
            'source_filenames': ('djtools/graficos/highcharts.js', 'djtools/graficos/exporting.js', 'comum/js/index.js'),
            'output_filename': 'js/index.js',
        },
        'jstree': {'source_filenames': ('djtools/jstree/jstree.min.js',), 'output_filename': 'js/jstree.min.js'},
        'highcharts': {'source_filenames': ('djtools/graficos/highcharts.js',), 'output_filename': 'js/highcharts.js'},
        'exporting': {'source_filenames': ('djtools/graficos/exporting.js',), 'output_filename': 'js/exporting.js'},
        'actions': {'source_filenames': ('djtools/js/actions.js',), 'output_filename': 'js/actions.js'},
        'base64': {'source_filenames': ('djtools/base64/base64.js',), 'output_filename': 'js/base64.js'},
        'select2': {
            'source_filenames': ('djtools/select2/js/select2.min.js', 'djtools/select2/js/i18n/pt-BR.js', 'djtools/select2/js/select2.custom.js'),
            'output_filename': 'js/select2.js',
        },
        'fancybox': {'source_filenames': ('djtools/fancybox/fancybox-core.js', 'djtools/fancybox/custom.js'), 'output_filename': 'js/fancybox.js'},
        'tabs': {'source_filenames': ('djtools/js/tabs.js',), 'output_filename': 'js/tabs.js'},
        'widgets': {
            'source_filenames': ('djtools/jquery/jquery.maskedinput.js', 'djtools/jquery/widgets-core.js'),
            'output_filename': 'js/widgets.js',
        },
        'jsi18n': {'source_filenames': ('djtools/js/admin_i18n.js',), 'output_filename': 'js/admin_i18n.js'},
    },
    'STYLESHEETS': {
        'select2': {'source_filenames': ('djtools/select2/css/select2.min.css',), 'output_filename': 'css/select2.min.css'},
        'padrao': {'source_filenames': ('djtools/themes/default/main.scss',), 'output_filename': 'css/main_default.css'},
        'dunas': {'source_filenames': ('djtools/themes/dunas/main.scss',), 'output_filename': 'css/main_dunas.css'},
        'aurora': {'source_filenames': ('djtools/themes/aurora/main.scss',), 'output_filename': 'css/main_aurora.css'},
        'luna': {'source_filenames': ('djtools/themes/luna/main.scss',), 'output_filename': 'css/main_luna.css'},
        'govbr': {'source_filenames': ('djtools/themes/govbr/main.scss',), 'output_filename': 'css/main_govbr.css'},
        'alto-contraste': {'source_filenames': ('djtools/themes/alto_contraste/main.scss',), 'output_filename': 'css/main_alto_contraste.css'},
        'ifs': {'source_filenames': ('djtools/themes/ifs/main.scss',), 'output_filename': 'css/main_ifs.css'},
        'modo-daltonismo': {'source_filenames': ('djtools/themes/modo_daltonismo/main.scss',), 'output_filename': 'css/main_modo_daltonismo.css'},
        'anonima': {'source_filenames': ('djtools/css/anonima.css',), 'output_filename': 'css/anonima.css'},
        'anonima-govbr': {'source_filenames': ('djtools/css/anonima_govbr.css',), 'output_filename': 'css/anonima_govbr.css'},
        'design_system': {'source_filenames': ('djtools/css/design_system.scss',), 'output_filename': 'css/design_system.css'},
        'magnific-popup': {'source_filenames': ('djtools/magnific-popup/magnific-popup.css',), 'output_filename': 'css/magnific-popup.css'},
    },
}


ADMIN_QUICK_ACCESS = os.environ.get('ADMIN_QUICK_ACCESS', 'documents,webmail,groups,microsoft_azure,google_classroom,phones,scdp_siape,mobile')

SERVICE_PROVIDER_FACTORY = os.environ.get(
    'SERVICE_PROVIDER_FACTORY', 'catalogo_provedor_servico.providers.impl.default.factory.ServiceProviderFactory'
)

TRUSTED_CERTS_DIRECTORY = join(BASE_DIR, 'certs')

# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = False

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

CELERY_TIMEZONE = TIME_ZONE

# http://docs.celeryproject.org/en/latest/userguide/configuration.html#task-time-limit
CELERY_TASK_TRACK_STARTED = True

NOTA_DECIMAL = os.environ.get('NOTA_DECIMAL', 'False') == 'True'
CASA_DECIMAL = int(os.environ.get('CASA_DECIMAL', '0'))  # valores aceitos: 1 ou 2
COMPONENTE_CH_DECIMAL = os.environ.get('COMPONENTE_CH_DECIMAL', 'False') == 'True'
periodos = os.environ.get('PERIODO_LETIVO_CHOICES', '1:1,2:2').split(',')  # padrão [[1, '1'], [2, '2']]
PERIODO_LETIVO_CHOICES = []
for periodo in periodos:
    chave, valor = periodo.split(':')
    PERIODO_LETIVO_CHOICES.append([int(chave), valor])
horas_aula = os.environ.get('TIPO_HORA_AULA_CHOICES', '45:45 min,60:60 min').split(',')  # padrão [[45, '45 min'], [60, '60 min']]
TIPO_HORA_AULA_CHOICES = []
for hora_aula in horas_aula:
    chave, valor = hora_aula.split(':')
    TIPO_HORA_AULA_CHOICES.append([int(chave), valor])
IMPEDIR_CHOQUE_HORARIOS_PROFESSOR = os.environ.get('IMPEDIR_CHOQUE_HORARIOS_PROFESSOR', 'False') == 'True'
PERCENTUAL_CH_PREPARACAO_AULAS_PIT = int(os.environ.get('PERCENTUAL_CH_PREPARACAO_AULAS_PIT', '100'))
PERMITE_ALTERACAO_CH_PREPARACAO_AULAS_PIT = os.environ.get('PERMITE_ALTERACAO_CH_PREPARACAO_AULAS_PIT', 'True') == 'True'

REQUESTS_MAX_RETRIES = int(os.environ.get('REQUESTS_MAX_RETRIES', '5'))
REQUESTS_BACKOFF_FACTOR = float(os.environ.get('REQUESTS_BACKOFF_FACTOR', '1'))
REQUESTS_STATUS_FORCELIST = tuple(map(int, os.environ.get('REQUESTS_STATUS_FORCELIST', '104,429,500,502,503,504').split(',')))
REQUESTS_TIMEOUT = int(os.environ.get('REQUESTS_TIMEOUT', '60'))

# Oauth GOVBR

GOVBR = {
    'CLIENT_ID': os.environ.get('GOVBR_CLIENT_ID'),
    'SECRET_KEY': os.environ.get('GOVBR_SECRET_KEY'),
    'API_URL': os.environ.get('GOVBR_API_URL', 'https://api.staging.acesso.gov.br'),
    'JWK_URL': os.environ.get('GOVBR_JWK_URL', 'https://sso.staging.acesso.gov.br/jwk'),
    'REDIRECT_URI': os.environ.get('GOVBR_REDIRECT_URI', '/accounts/login/'),
    'AUTHORIZATION_URL': os.environ.get('GOVBR_AUTHORIZATION_URL', 'https://sso.staging.acesso.gov.br/authorize'),
    'ACCESS_TOKEN_URL': os.environ.get('GOVBR_ACCESS_TOKEN_URL', 'https://sso.staging.acesso.gov.br/token'),
    'USER_DATA_URL': os.environ.get('GOVBR_USER_DATA_URL', 'https://sso.staging.acesso.gov.br/userinfo'),
    'SCOPES': os.environ.get('GOVBR_SCOPES', 'openid,profile,phone,email,govbr_confiabilidades').split(','),
    'LOGOUT_URL': os.environ.get('GOVBR_LOGOUT_URL', 'https://sso.staging.acesso.gov.br/logout?post_logout_redirect_uri={}').format(SITE_URL),
    'PRIMARY_LOGIN': os.environ.get('GOVBR_PRIMARY_LOGIN', 'False') == 'True',
    'USER_AUTO_UPDATE': os.environ.get('GOVBR_USER_AUTO_UPDATE', 'False') == 'True',
    'USER_AUTO_CREATE': os.environ.get('GOVBR_USER_AUTO_CREATE', 'False') == 'True',
}

EXTRA_CSS = []
EXTRA_JS = []

ADMIN_FILTER_REQUIRED_MODELS = os.environ.get('ADMIN_FILTER_REQUIRED_MODELS', '')
ADMIN_FILTER_REQUIRED_MODELS = ADMIN_FILTER_REQUIRED_MODELS and ADMIN_FILTER_REQUIRED_MODELS.split(',') or []

# Session Lock
SESSION_LOCK = os.environ.get('SESSION_LOCK', 'False') == 'True'

# Recaptcha
RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY', '')
RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY', '')

for key, value in list(os.environ.items()):
    if key.startswith('SUAP_'):
        key = key.replace('SUAP_', '')
        try:
            globals()[key] = json.loads(value.replace("'", '"'))
        except ValueError:
            globals()[key] = value

# Ninja API
NINJA_JWT = {
    'ACCESS_TOKEN_LIFETIME': datetime.timedelta(days=1),
}

NUM_PROCESSO_DIVISOR_SUFIXO = os.environ.get('NUM_PROCESSO_DIVISOR_SUFIXO', '.')
