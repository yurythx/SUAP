import datetime
import logging

from beat.models import ResultadoExecucao
from djtools.management.commands import BaseCommandPlus

logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    help = 'Limpa os resultados de execução de tarefas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            help='Número de segundos para aguardar antes de finalizar o comando.',
        )

    def handle(self, *args, **options):
        data_limite_exclusao = datetime.datetime.now() - datetime.timedelta(days=options.get('days', 30))
        total, _ = ResultadoExecucao.objects.filter(datetime_start__lt=data_limite_exclusao).delete()
        logger.info(f'{total} Resultados de execução mais antigos que "{data_limite_exclusao}" foram removidos.')
        data_limite_finalizacao = datetime.datetime.now() - datetime.timedelta(days=1)
        total = ResultadoExecucao.objects.filter(datetime_start__lt=data_limite_finalizacao, datetime_end__isnull=True).update(
            datetime_end=datetime.datetime.now(),
            status=ResultadoExecucao.STATUS_TIMEOUT,
        )
        logger.info(f'{total} Resultados de execução mais antigos que "{data_limite_finalizacao}" foram atualizados para timeout.')
