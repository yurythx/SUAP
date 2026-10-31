from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import Group

from ae.models import Participacao
from comum.models import UsuarioGrupo
from djtools.management.commands import BaseCommandPlus
from djtools.utils import send_notification


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        titulo = '[SUAP] Encerramento de Participação do Aluno em Programa'
        grupo = Group.objects.get(name='Assistente Social')

        for participacao in Participacao.abertas.filter(aluno__situacao__ativo=False):
            participacao.data_termino = datetime.today()
            participacao.motivo_termino = 'O aluno possui situação de matrícula inativa na instituição.'
            participacao.save()
            texto = (
                '<h1>Encerramento de Participação do Aluno em Programa</h1>'
                f"<p>A participação do aluno '{participacao.aluno}' foi encerrada pois o mesmo possui situação de matrícula inativa na instituição.</p>"
            )

            for usuario in UsuarioGrupo.objects.filter(group=grupo, user__vinculo__setor__uo=participacao.aluno.curso_campus.diretoria.setor.uo):
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [usuario.user.get_vinculo()])
