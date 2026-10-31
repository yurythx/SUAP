import datetime

from djtools.db import models
from djtools.management.commands import BaseCommandPlus
from gerenciador_projetos.enums import SituacaoProjeto, TipoRecorrencia
from gerenciador_projetos.models import Tarefa

""" python manage.py gp_tarefas_recorrentes """


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        """
        Verifica se existem tarefas a serem clonadas na data de hoje, com base na recorrencia cadastrada
        """
        hoje = datetime.date.today()
        dia_da_semana = hoje.weekday()
        dia_do_mes = hoje.day
        mes_do_ano = hoje.month
        for tarefa in (
            Tarefa.objects.filter(projeto__situacao__in=[SituacaoProjeto.ABERTO, SituacaoProjeto.EM_ANDAMENTO])
            .filter(models.Q(recorrenciatarefa__data_fim__isnull=True) | models.Q(recorrenciatarefa__data_fim__lte=hoje))
            .filter(
                models.Q(recorrenciatarefa__tipo_recorrencia=TipoRecorrencia.DIARIAMENTE)
                | models.Q(recorrenciatarefa__tipo_recorrencia=TipoRecorrencia.SEMANALMENTE, recorrenciatarefa__dia_da_semana=dia_da_semana)
                | models.Q(recorrenciatarefa__tipo_recorrencia=TipoRecorrencia.MENSALMENTE, recorrenciatarefa__dia_do_mes=dia_do_mes)
                | models.Q(
                    recorrenciatarefa__tipo_recorrencia=TipoRecorrencia.ANUALMENTE,
                    recorrenciatarefa__dia_do_mes=dia_do_mes,
                    recorrenciatarefa__mes_do_ano=mes_do_ano,
                )
            )
            .distinct()
        ):
            print(f'Clonando Tarefa - {tarefa} ')
            tarefa.clonar()

        print('Execução finalizada.')
