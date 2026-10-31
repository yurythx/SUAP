"""
Baseado no django_behave.
"""

import json
import logging
import os
import sys
import unittest
from os.path import abspath, basename, dirname, isdir, isfile, join

from behave.configuration import OPTIONS, Configuration
from behave.formatter._registry import make_formatters
from behave.formatter.ansi_escapes import escapes
from behave.runner import Context
from behave.runner import Runner as BehaveRunner
from behave.runner_util import parse_features
from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.backends.postgresql.creation import DatabaseCreation
from django.test import override_settings

from djtools.new_tests.keepdb_manager import (
    InitialDataMetaMixin,
    KeepDBManager,
    add_keepdb_cli_arguments,
    get_keepdb_mode_from_argv,
    refresh_initial_template_if_needed,
)
from djtools.new_tests.db_preflight import ensure_database_access
from djtools.new_tests.pdf_documentation import BehavePdfDocumentationService
from djtools.new_tests.reuse_successful_scenarios import (
    add_reuse_successful_scenarios_argument,
    resolve_reuse_successful_scenarios,
)
from djtools.tests.runner import DiscoverRunnerPlus


def get_app(label):
    appconfig = apps.get_app_config(label)
    return appconfig.models_module or appconfig.module


def get_app_dir(app_module):
    app_dir = dirname(app_module.__file__)
    if basename(app_dir) == 'models':
        app_dir = abspath(join(app_dir, '../'))
    return app_dir


def get_features(app_module):
    app_dir = get_app_dir(app_module)

    # if isdir(join(app_dir, 'lps/{}/features'.format(settings.LPS))):
    #     features_dir = abspath(join(app_dir, 'lps/{}/features'.format(settings.LPS)))
    #     return features_dir
    if isdir(join(app_dir, 'features')):
        features_dir = abspath(join(app_dir, 'features'))
        return features_dir
    else:
        return None


def parse_argv(argv, option_info):
    behave_options = list(option_info.keys())

    new_argv = ['behave']
    our_opts = {'browser': None}

    for index in range(len(argv)):
        if argv[index] in behave_options and argv[index].startswith('--'):
            # Convert to Behave option
            new_argv.append('--' + argv[index][9:])

            # Add option argument if there is one
            if option_info[argv[index]] is True:
                new_argv.append(argv[index + 1])
                index += 1  # Skip past option arg

    if '--behave_capture' not in argv:
        new_argv.extend(['--no-capture', '--no-capture-stderr', '--no-logcapture'])

    return (new_argv, our_opts)


def get_options():
    option_list = ()

    option_info = {}

    for fixed, keywords in OPTIONS:
        # Look for the long version of this option
        long_option = None
        for option in fixed:
            if option.startswith('--'):
                long_option = option
                break

        # Only deal with those options that have a long version
        if long_option:
            # remove function types, as they are not compatible with optparse
            if callable(keywords.get('type')):
                del keywords['type']

            # Remove 'config_help' as that's not a valid optparse keyword
            if 'config_help' in keywords:
                keywords.pop('config_help')

            name = '--behave_' + long_option[2:]

            option_list = (*option_list, (name, keywords))

            # Need to store a little info about the Behave option so that we
            # can deal with it later.  'has_arg' refers to if the option has
            # an argument.  A boolean option, for example, would NOT have an
            # argument.
            action = keywords.get('action', 'store')
            if action == 'store' or action == 'append':
                has_arg = True
            else:
                has_arg = False

            option_info.update({name: has_arg})

    return (option_list, option_info)


class MyBehaveRunner(BehaveRunner):
    def run_with_paths(self):
        extra_steps = [path + '/steps/' for path in self.config.paths]

        self.context = Context(self)
        self.context.debug = self.config.debug
        self.load_hooks()
        self.load_step_definitions(extra_step_paths=settings.TEST_COMMON_STEPS + extra_steps)

        # -- ENSURE: context.execute_steps() works in weird cases (hooks, ...)
        # self.setup_capture()
        # self.run_hook('before_all', self.context)

        # -- STEP: Parse all feature files (by using their file location).
        try:
            lps_path = self.config.paths[0].replace('features', f'lps/{settings.LPS}/features/')
        except IndexError:
            lps_path = ''

        feature_locations = []

        for obj_file in self.feature_locations():
            if self.config.include_re is None or self.config.include_re.search(obj_file.filename):
                if isfile(lps_path + obj_file.filename.split('/')[-1]):
                    obj_file.filename = lps_path + obj_file.filename.split('/')[-1]
                feature_locations.append(obj_file)

        features = parse_features(feature_locations, language=self.config.lang)

        self.features.extend(features)

        # -- STEP: Run all features.
        stream_openers = self.config.outputs
        self.formatters = make_formatters(self.config, stream_openers)
        return self.run_model()


@override_settings(DEBUG=settings.DEBUG)
class MyBehaveTestCase(InitialDataMetaMixin, StaticLiveServerTestCase):
    first_time = True

    def __initial_data(self):
        """
        Método executado uma vez no início dos testes. Nesse ponto pode-se realizar a carga inicial para os testes.
        """

        # Laço passando por todos os 'caminhos'(path) dos modulos a serem testados
        for path in self.get_features_dir():
            # Acrescenta o nome do arquivo ao caminho
            test_file = path + '/test_initial_data.py'
            # Verifica se o arquivo "teste_dados_iniciais" existe naquele modulo
            if isfile(test_file):
                # Pega o caminho a partir de 'suap/' ([modulo]/features)
                str_module = path[len(settings.BASE_DIR) + 1 :]
                # Substitui a '/' pelo '.'
                str_module = str_module.replace('/', '.')
                # Acrescenta o nome do arquivo e a função a ser chamada
                str_module += '.test_initial_data.initial_data'
                # Acrescenta a string à lista de caminhos de carga inicial
                settings.TEST_INITIAL_DATA.append(str_module)

        if self.first_time:
            keep_mode = get_keepdb_mode_from_argv()
            if keep_mode and self._initial_data_already_loaded():
                logging.getLogger(__name__).info('[test_behave] Carga inicial já executada (%s). Pulando...', keep_mode)
                self.first_time = False
                return
            self._run_initial_data_load()
            if keep_mode:
                self._mark_initial_data_loaded()
            self.first_time = False

    def __init__(self, **kwargs):
        self.features_dir = kwargs.pop('features_dir')
        self.option_info = kwargs.pop('option_info')
        self.verbosity = kwargs.pop('verbosity', 1)
        super().__init__(**kwargs)
        if settings.BEHAVE_AUTO_DOC_PATH:
            os.makedirs(settings.BEHAVE_AUTO_DOC_PATH, exist_ok=True)
        if settings.BEHAVE_AUTO_MOCK_PATH:
            os.makedirs(settings.BEHAVE_AUTO_MOCK_PATH, exist_ok=True)

    def setUp(self):
        self.__initial_data()
        refresh_initial_template_if_needed()
        self.setupBehave()

    def _fixture_teardown(self):
        """
        Controla o flush do banco ao final do teste conforme argumentos de keepdb.
        Útil para inspecionar os dados gerados ou manter somente a carga inicial.
        """
        keep_mode = get_keepdb_mode_from_argv()
        if keep_mode == 'with_data':
            from django.db import connections

            aliases = self._databases_names(include_mirrors=False)
            if aliases:
                alias = aliases[0]
                db_name = connections[alias].settings_dict.get('NAME', alias)
            else:
                db_name = 'N/A'
            sys.stderr.write(f'[WARN] keepdb-with-data: mantendo o banco de teste (sem flush). Dados anteriores permanecem. Banco: {db_name}\n')
            sys.stderr.flush()
            self._set_data_origin('with_data')
            return
        if keep_mode == 'initial_only':
            sys.stderr.write(
                '[INFO] keepdb-initial-only: preservando estado da execução atual; o banco será restaurado do template inicial no próximo início.\n'
            )
            sys.stderr.flush()
            self._set_data_origin('initial_only')
            return
        sys.stderr.write('[INFO] keepdb-default: limpando o banco de teste (flush)...\n')
        sys.stderr.flush()
        super()._fixture_teardown()

    def setupBehave(self):
        old_argv = sys.argv
        (sys.argv, _) = parse_argv(old_argv, self.option_info)

        self.behave_config = Configuration()
        sys.argv = old_argv

        self.behave_config.server_url = self.live_server_url  # property of LiveServerTestCase
        self.behave_config.paths = self.get_features_dir()
        self.behave_config.format = self.behave_config.format or ['pretty']
        self.behave_config.debug = '--noinput' not in sys.argv

        # disable these in case you want to add set_trace in the tests you're developing
        if self.behave_config.stdout_capture:
            self.behave_config.stdout_capture = self.behave_config.stdout_capture
        else:
            self.behave_config.stdout_capture = False

        if self.behave_config.stderr_capture:
            self.behave_config.stderr_capture = self.behave_config.stderr_capture
        else:
            self.behave_config.stderr_capture = False

    def get_features_dir(self):
        if isinstance(self.features_dir, str):
            return [self.features_dir]
        return self.features_dir

    def runTest(self, result=None):
        runner = MyBehaveRunner(self.behave_config)
        failed = runner.run()

        try:
            undefined_steps = runner.undefined_steps
        except AttributeError:
            undefined_steps = runner.undefined

        if self.behave_config.show_snippets and undefined_steps:
            msg = '\nYou can implement step definitions for undefined steps with '
            msg += 'these snippets:\n\n'
            printed = set()

            string_prefix = "('"

            for step in set(undefined_steps):
                if step in printed:
                    continue
                printed.add(step)

                msg += '@' + step.step_type + string_prefix + step.name + "')\n"
                msg += 'def impl(context):\n'
                msg += '    assert False\n\n'

            sys.stderr.write(escapes['undefined'] + msg + escapes['reset'])
            sys.stderr.flush()

        if failed:
            raise AssertionError('Existe(m) erro(s) nos testes!!!')


class UnloggedDatabaseCreationMixin(DatabaseCreation):
    """
    Mixin para converter todas as tabelas criadas no banco de dados de teste
    para UNLOGGED, acelerando operações de escrita em testes.
    """

    def create_test_db(self, verbosity=1, autoclobber=False, serialize=True, keepdb=False):
        # 1. Cria o banco de dados de teste normalmente
        super().create_test_db(verbosity, autoclobber, serialize, keepdb)

        if self.connection.vendor != 'postgresql':
            return

        with connection.cursor() as cursor:
            if verbosity >= 1:
                sys.stdout.write('... Configurando tabelas do banco de teste como UNLOGGED ...\n')

            # 2. Busca todas as tabelas criadas pelo Django
            # Isso evita a alteração de tabelas do sistema (ex: pg_catalog)
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)

            tables = [row[0] for row in cursor.fetchall()]

            # 3. Converte cada tabela para UNLOGGED
            for table_name in tables:
                # O comando ALTER TABLE exige que a tabela não esteja sendo usada ativamente
                # Durante a criação do DB, isso geralmente não é um problema
                try:
                    cursor.execute(f'ALTER TABLE "{table_name}" SET UNLOGGED;')
                except Exception as e:
                    # Pode falhar para tabelas do sistema ou outras razões.
                    if verbosity >= 2:
                        sys.stdout.write(f'Falha ao tornar {table_name} UNLOGGED: {e}\n')

        return self.connection.settings_dict['NAME']


class MyBehaveTestRunner(DiscoverRunnerPlus):
    def __init__(self, *args, **kwargs):
        self.verbosity = kwargs.pop('verbosity', 1)
        self.option_list, self.option_info = get_options()
        self.default_tablespace = kwargs.pop('default_tablespace', None)
        self.generate_pdf = kwargs.pop('generate_pdf', False)
        keepdb_initial_only = kwargs.pop('keepdb_initial_only', False)
        keepdb_with_data = kwargs.pop('keepdb_with_data', False)
        self.force_drop_test_db = kwargs.pop('force_drop_test_db', False)
        if keepdb_with_data:
            keepdb_initial_only = False
        self.keepdb_with_data = bool(keepdb_with_data)
        self.keepdb_initial_only = bool(keepdb_initial_only)
        self.reuse_successful_scenarios = resolve_reuse_successful_scenarios(kwargs, self.keepdb_with_data)
        if keepdb_initial_only or keepdb_with_data:
            kwargs['keepdb'] = True
        if self.keepdb_with_data:
            logging.getLogger(__name__).info('[test_behave] keepdb-with-data: banco será mantido com dados da execução.')
        elif self.keepdb_initial_only:
            logging.getLogger(__name__).info('[test_behave] keepdb-initial-only: banco será mantido apenas com dados iniciais.')
        self.admin_db_name = settings.DATABASES['default']['NAME']
        if self.generate_pdf:
            settings.BEHAVE_AUTO_DOC = True
        self.keepdb_manager = KeepDBManager(
            admin_db_name=self.admin_db_name,
            keepdb=getattr(self, 'keepdb', kwargs.get('keepdb', False)),
            keepdb_with_data=self.keepdb_with_data,
            keepdb_initial_only=self.keepdb_initial_only,
            force_drop_test_db=self.force_drop_test_db,
        )
        super().__init__(*args, **kwargs)

    @classmethod
    def add_arguments(cls, parser):
        # Set up to accept all of Behave's command line options and our own.  In
        # order to NOT conflict with Django's test command, we'll start all options
        # with the prefix "--behave_" (we'll only do the long version of an option).
        super().add_arguments(parser)
        option_list, cls.option_info = get_options()
        for fixed, keywords in option_list:
            parser.add_argument(fixed, **keywords)
        parser.add_argument(
            '--default-tablespace',
            dest='default_tablespace',
            default=None,
            help='Tablespace padrão a ser usada durante os testes.',
        )
        parser.add_argument(
            '--generate-pdf',
            action='store_true',
            dest='generate_pdf',
            default=False,
            help='Gera um PDF por app ao final do test_behave usando a documentação automática.',
        )
        keepdb_group = parser.add_mutually_exclusive_group()
        add_keepdb_cli_arguments(keepdb_group, parser)
        add_reuse_successful_scenarios_argument(parser)

    def make_bdd_test_suite(self, features_dir):
        return MyBehaveTestCase(features_dir=features_dir, option_info=self.option_info, verbosity=self.verbosity)

    def build_suite(self, test_labels, **kwargs):
        suites = []
        features_dirs = []
        features = []
        skipped_labels = []
        if not test_labels:
            test_labels = sorted(settings.INSTALLED_APPS_SUAP)

        for label in test_labels:
            if '.' in label:
                continue
            app = get_app(label)
            features_dir = get_features(app)
            if features_dir is not None:
                features_dirs.append(features_dir)
                features.append(label)
                if self.parallel > 1:
                    suite = unittest.TestSuite()
                    suite.addTest(self.make_bdd_test_suite(features_dir))
                    suites.append(suite)
            else:
                skipped_labels.append(label)

        if not features_dirs:
            suite = unittest.TestSuite()
            skipped_text = ' '.join(skipped_labels) if skipped_labels else 'nenhum modulo informado'
            sys.stdout.write(f'test_behave - sem features para executar em: {skipped_text}\n')
            sys.stdout.flush()
            return suite

        # Forçando parallel
        if self.parallel > 1:
            parallel_suite = self.parallel_test_suite(suites, self.parallel, failfast=True)
            self.parallel = min(self.parallel, len(features))

            # If there's only one TestCase, parallelization isn't needed.
            if self.parallel > 1:
                suite = parallel_suite

        else:
            suite = unittest.TestSuite()
            suite.addTest(self.make_bdd_test_suite(features_dirs))

        sys.stdout.write(f'test_behave {"parallel " + str(self.parallel) if self.parallel > 1 else ""} - {" ".join(features)} \n')
        sys.stdout.flush()
        return suite

    def _finalize_behave_auto_doc(self):
        if settings.BEHAVE_AUTO_DOC:
            folders = next(os.walk(settings.BEHAVE_AUTO_DOC_PATH))[1]
            aplicacoes = []
            for folder in folders:
                if os.path.exists(f'{settings.BEHAVE_AUTO_DOC_PATH}/{folder}/documentacao.json'):
                    aplicacoes.append(folder)

            pdf_service = BehavePdfDocumentationService(settings.BEHAVE_AUTO_DOC_PATH)
            dicionario = pdf_service.build_index(aplicacoes)
            json_file = f'{settings.BEHAVE_AUTO_DOC_PATH}/documentacao.json'
            with open(json_file, mode='w') as f:
                f.write(json.dumps(dicionario))
            if self.generate_pdf:
                pdf_service.generate_for_apps(aplicacoes)

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        self._finalize_behave_auto_doc()
        return result

    def teardown_test_environment(self, **kwargs):
        super().teardown_test_environment(**kwargs)

    def setup_databases(self, **kwargs):
        DatabaseWrapper.creation_class = UnloggedDatabaseCreationMixin
        if self.default_tablespace:
            settings.DEFAULT_TABLESPACE = self.default_tablespace
        logging.getLogger(__name__).info('[test_behave] Executando preflight de acesso ao banco antes do setup de testes...')
        ensure_database_access(purpose='test_behave')
        self.keepdb_manager.keepdb = self.keepdb
        self.keepdb_manager.prepare_before_setup()
        database = super().setup_databases(**kwargs)
        self.keepdb_manager.persist_migration_hash_if_needed()
        return database
