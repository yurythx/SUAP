from datetime import datetime, timedelta

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
        Aluno = apps.get_model('edu', 'Aluno')
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhuma configuração LDAP ativa encontrada.')

        filter_kw = {'situacao__ativo': False}
        if options['alterado_em']:
            filter_kw['alterado_em__gte'] = datetime.now() - timedelta(hours=int(options['alterado_em']))

        for a in Aluno.objects.filter(**filter_kw).select_related('pessoa_fisica', 'curso_campus__diretoria__setor__uo__setor', 'situacao'):
            try:
                conf.sync_user(a)
            except Exception as e:
                capture_exception(e)
