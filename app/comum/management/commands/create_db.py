from unittest.mock import patch

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from psycopg import sql

from djtools.management.commands import BaseCommandPlus


class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


# Objetos de banco criados por `RunSQL` nas migrations. O syncdb monta o schema a partir dos models e
# não enxerga nenhum deles, então cada um precisa ser tratado aqui: recriado (valor em banco novo) ou
# declarado com o motivo de não ser. `comum/tests/test_create_db.py` falha quando surge um objeto novo.
OBJETOS_SQL_DAS_MIGRATIONS = {
    'function validar_identificador': 'recriado por criar_objetos_sql_das_migrations (create_db e gerar_banco_mock)',
    'trigger check_identificador': 'recriado por criar_objetos_sql_das_migrations (create_db e gerar_banco_mock)',
    'index idx_dados_usuario_externo_email': 'declarado em Meta.indexes de avaliacao_integrada.Respondente (migration 0013)',
    'index edu_professordiario_diario_professor_uniq': 'declarado em Meta.constraints de edu.ProfessorDiario (UniqueConstraint; migration 0329)',
    'function drop_all_table_constraints': 'helper chamado apenas pela própria migration comum/0099',
    'index rh_pessoaexterna_pessoa_fisica_id_ed6e97e3': 'índice da FK PessoaExterna.pessoa_fisica: o syncdb o cria pelo model (rh/0109 só repõe onde faltava)',
}

# documento_eletronico/0029: garante a unicidade do identificador do documento no próprio banco.
TRIGGER_IDENTIFICADOR_DOCUMENTO = """
    CREATE OR REPLACE FUNCTION validar_identificador()
    RETURNS TRIGGER AS $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM documento_eletronico_documentotexto
            WHERE identificador = NEW.identificador
            AND (NEW.id IS NULL OR id != NEW.id)
            LIMIT 1
        ) THEN
            RAISE EXCEPTION 'Já existe um registro com o mesmo identificador';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    DROP TRIGGER IF EXISTS check_identificador ON documento_eletronico_documentotexto;
    CREATE TRIGGER check_identificador BEFORE INSERT OR UPDATE ON documento_eletronico_documentotexto
    FOR EACH ROW EXECUTE FUNCTION validar_identificador();
"""


def criar_objetos_sql_das_migrations() -> None:
    """Recria, no banco conectado, os objetos que só existem em `RunSQL` (ver `OBJETOS_SQL_DAS_MIGRATIONS`).

    Reusado por `gerar_banco_mock` (etapa `volume`): lá o schema vem dos models
    (`--no-migrations`), então nenhum `RunSQL` de migration roda e esses objetos ficariam
    ausentes do dump. Idempotente (`CREATE OR REPLACE` / `DROP ... IF EXISTS`): pode rodar
    em banco onde o trigger já existe sem duplicar nada.
    """
    if 'documento_eletronico' in settings.INSTALLED_APPS:
        with connection.cursor() as cursor:
            cursor.execute(TRIGGER_IDENTIFICADOR_DOCUMENTO)


class Command(BaseCommandPlus):
    help = 'Setup banco sem migrations'

    def handle(self, *args, **kwargs):
        self.stdout.write('0. Criando banco de dados (se não existir)...')
        self._create_database()

        self.stdout.write('1. Criando funções SQL...')
        self._create_functions()

        with patch.object(settings, 'MIGRATION_MODULES', DisableMigrations()):
            self.stdout.write('2. Rodando syncdb...')
            call_command('migrate', '--run-syncdb')

        self.stdout.write('3. Criando gatilhos...')
        self._create_triggers()

        self.stdout.write('4. Marcando migrations como aplicadas...')
        call_command('migrate', '--fake')

        self.stdout.write('5. Sincronizando...')
        call_command('sync')

        self.stdout.write('6. Criando superusuário...')
        call_command('createsuperuser')

        self.stdout.write(self.style.SUCCESS('Setup concluído!'))

    def _create_database(self):
        db = settings.DATABASES['default']
        name = db['NAME']
        conn_params = {
            'dbname': 'postgres',
            'user': db.get('USER') or None,
            'password': db.get('PASSWORD') or None,
            'host': db.get('HOST') or None,
            'port': db.get('PORT') or None,
        }
        conn_params = {k: v for k, v in conn_params.items() if v}
        with psycopg.connect(**conn_params, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', [name])
            if cur.fetchone():
                self.stdout.write(f'   Banco "{name}" já existe.')
                return
            cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            self.stdout.write(self.style.SUCCESS(f'   Banco "{name}" criado.'))

    def _create_triggers(self):
        """Recria os gatilhos que só existem em `RunSQL`. Roda após o syncdb: a tabela precisa existir."""
        if 'documento_eletronico' not in settings.INSTALLED_APPS:
            self.stdout.write('   documento_eletronico não instalado, nada a fazer.')
            return
        criar_objetos_sql_das_migrations()

    def _create_functions(self):
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS unaccent;')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements;')
            cursor.execute("""
                CREATE COLLATION IF NOT EXISTS ignore_accents_case (
                    provider = 'icu',
                    locale = 'pt-BR-u-ks-level1',
                    deterministic = false
                );
            """)
            cursor.execute("""
                CREATE OR REPLACE FUNCTION f_unaccent(text)
                    RETURNS text AS
                $func$
                SELECT unaccent('unaccent', upper($1))
                $func$  LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp;
            """)
