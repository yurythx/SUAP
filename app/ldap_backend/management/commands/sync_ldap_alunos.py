from datetime import datetime, timedelta

from django.apps import apps
from django.db.models import Q
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
        alunos = Aluno.objects.filter(situacao__ativo=True)

        if options['alterado_em']:
            alunos = alunos.filter(alterado_em__gte=datetime.now() - timedelta(hours=int(options['alterado_em'])))

        alunos = alunos.filter(Q(participanteturmaminicurso__turma__gerar_matricula=True) | Q(matriz_id__isnull=False))
        alunos = alunos.distinct()

        for a in alunos.select_related('pessoa_fisica', 'curso_campus__diretoria__setor__uo__setor', 'situacao'):
            try:
                if a.get_user():
                    conf.sync_user(a)
            except Exception as e:
                capture_exception(e)
