import datetime

from djtools.management.commands import BaseCommandPlus
from edu import tasks
from edu.models import ConfiguracaoPedidoMatricula, PedidoMatriculaDiario


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        pks = set(
            PedidoMatriculaDiario.objects.filter(
                pedido_matricula__configuracao_pedido_matricula__ano_letivo__ano__gte=2018,
                pedido_matricula__configuracao_pedido_matricula__data_fim__lt=datetime.date.today(),
                motivo__isnull=True,
            )
            .order_by('pedido_matricula__configuracao_pedido_matricula_id')
            .values_list('pedido_matricula__configuracao_pedido_matricula_id', flat=True)
            .distinct()
        )
        for configuracao in ConfiguracaoPedidoMatricula.objects.filter(pk__in=pks):
            tasks.processar_pedidos_matricula(configuracao)
