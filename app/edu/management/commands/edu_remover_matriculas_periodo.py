"""
Remove as matrículas período que foram excluídas do Q-Acadêmico após serem importadas para o Suap
"""

from django.db import connection
from django.db.models.deletion import Collector

from djtools.management.commands import BaseCommandPlus
from edu.models import HistoricoSituacaoMatriculaPeriodo, MatriculaPeriodo, SituacaoMatriculaPeriodo


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        collector = Collector('default')
        related_fields_mp = [
            f for f in MatriculaPeriodo._meta.get_fields(include_hidden=True) if (f.one_to_many or f.one_to_one) and f.auto_created and not f.concrete
        ]
        matriculas_periodo = MatriculaPeriodo.objects.filter(excluida=True, aluno__matriz__isnull=True).exclude(
            situacao=SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL
        )
        total = matriculas_periodo.count()

        for related_field in related_fields_mp:
            objs = collector.related_objects(related_field, matriculas_periodo)
            if objs:
                for obj in objs:
                    if obj.__class__ != HistoricoSituacaoMatriculaPeriodo:
                        print('Abortando...')
                        return

                        # cur = connection.cursor()
                        # for pk in matriculas_periodo.values_list('id', flat=True):
                        # cur.execute('delete from edu_historicosituacaomatriculaperiodo where matricula_periodo_id = {};'.format(pk))
                        # cur.execute('delete from edu_matriculaperiodo where id = {};'.format(pk))
        print(total)
        connection._commit()
