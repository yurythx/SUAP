from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, SituacaoMatricula


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for a in Aluno.objects.filter(codigo_academico__isnull=False, matriz__isnull=False, situacao__id=SituacaoMatricula.MATRICULADO):
            a.atualizar_situacao('Reprocessamento do Histórico Automático')
            a.save()
