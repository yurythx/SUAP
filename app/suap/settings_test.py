"""Settings de teste do SUAP, dirigido por ambiente (proposta committável).

Herda de ``suap.settings_base`` (compartilhado/versionado), portanto NÃO depende
do ``suap/settings.py`` pessoal — funciona em clone novo, em CI e em máquina sem
setup. Os testes constroem um banco de teste do zero a partir dos models
(``--no-migrations``); NÃO é preciso um banco SUAP populado, apenas um servidor
PostgreSQL acessível.

Conexão dirigida pelas mesmas variáveis do ``.env`` do projeto (com defaults):

    DATABASE_HOST (127.0.0.1)   DATABASE_PORT (5432)
    DATABASE_USER (postgres)    DATABASE_PASSWORD ('')
    DATABASE_NAME (postgres)    -> banco só de bootstrap; o Django cria o de teste
    TEST_DATABASE_NAME (test_suap) -> nome do banco de teste criado

Requisito do Postgres: ``max_locks_per_transaction`` alto o suficiente (o schema
completo do SUAP é criado numa única transação; o default 64 estoura). Sem
instalar nada localmente, um Postgres efêmero em Docker resolve:

    docker run --rm -d --name suap-test-db -p 5433:5432 \\
      -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:18 \\
      -c max_locks_per_transaction=4096 -c shared_preload_libraries=pg_stat_statements

    DATABASE_PORT=5433 DJANGO_SETTINGS_MODULE=suap.settings_test \\
      uv run pytest --create-db auditoria/tests   # --reuse-db nas próximas vezes
"""

import os

from suap.settings_base import *  # noqa: F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DATABASE_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
        # Banco de manutenção só para o Django conectar e emitir CREATE DATABASE.
        'NAME': os.environ.get('DATABASE_NAME', 'postgres'),
        'USER': os.environ.get('DATABASE_USER', 'postgres'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
        'CONN_MAX_AGE': 0,
        # A chave é POR BANCO (é assim que o Django a lê); o `DISABLE_SERVER_SIDE_CURSORS`
        # de módulo em `settings_base.py:70` não tem efeito nenhum — ninguém o consome.
        # `suap/settings.py:50` já declara esta chave, mas este módulo redefine `DATABASES`
        # do zero e ficava sem ela. Só os e2e notam, porque só eles renderizam tela de
        # verdade: um formulário que itera queryset por cursor (o `EventoForm` do admin de
        # eventos) estoura `InvalidCursorName: cursor "_django_curs_..." does not exist` no
        # meio do template e a página vira 500. Verificado em `eventos/tests/e2e`, onde a
        # falha aparecia em banco recém-criado e sumia no `--reuse-db` seguinte.
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'TEST': {'NAME': os.environ.get('TEST_DATABASE_NAME', 'test_suap'), 'MIGRATE': False, 'CONN_MAX_AGE': 0},
    }
}

# ``settings_base`` não define DEBUG, então sem isto ele fica no default do Django
# (False) e o django-pipeline liga o bundling: ``pipeline/conf.py`` avalia
# ``PIPELINE_ENABLED = not settings.DEBUG`` no *import*, e os templates passam a
# referenciar os arquivos concatenados (``css/select2.min.css`` etc.), que existem só em
# STATIC_ROOT. Como o ``StaticFilesHandler`` do ``live_server`` serve via finders, o
# resultado é 404 em todo CSS/JS — jQuery nem carrega e nenhum widget interativo
# funciona nos testes de browser. Com DEBUG=True o pipeline referencia os fontes, que os
# finders acham. As fixtures de comum/pytest_fixtures.py já forçavam isto por classe.
DEBUG = True

# Não há worker nos testes: com Celery ligado o decorator ``@task`` (djtools/assincrono) enfileira e a
# tarefa nunca roda. O ``.env`` do projeto traz ``USE_CELERY=True`` e ``load_dotenv()`` o acha inclusive
# a partir de um worktree em ``.claude/worktrees/``. O ``settings_sample.py`` faz o mesmo para
# ``suap.settings``.
USE_CELERY = False

# Hasher rápido só para testes: os fluxos fazem dezenas de logins (troca de papel
# secretário/professor/aluno), e o PBKDF2 de produção custava ~6s só em hashing no
# fluxo de pós. MD5 corta isso para ~0 sem afetar o que os testes verificam.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
