from datetime import datetime, timedelta

import tqdm
from django.apps import apps
from sentry_sdk import capture_exception

from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument(
            '--alterado_em',
            action='store',
            dest='alterado_em',
            default=0,
            type=int,
            help='Informe a quantidade de horas da última alteração para restringir a sincronia.',
        )

    def handle(self, *args, **options):
        Servidor = apps.get_model('rh', 'Servidor')
        verbosity = options['verbosity']
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhuma configuração LDAP ativa encontrada.')

        filter_kw = {}
        if options['alterado_em']:
            filter_kw['alterado_em__gte'] = datetime.now() - timedelta(hours=int(options['alterado_em']))

        qs = Servidor.objects.filter(**filter_kw).select_related('setor__uo__setor', 'cargo_emprego__grupo_cargo_emprego')

        if verbosity >= 2:
            qs = tqdm.tqdm(qs)

        for s in qs:
            try:
                conf.sync_user(s)
            except Exception as e:
                capture_exception(e)
