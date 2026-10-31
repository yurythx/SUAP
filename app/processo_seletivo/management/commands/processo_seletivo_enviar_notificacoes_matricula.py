from datetime import date
from djtools.management.commands import BaseCommandPlus
from processo_seletivo.models import EditalPeriodoLiberacao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = (
            EditalPeriodoLiberacao.objects.filter(introducao_notifiacao_matricula__isnull=False, detalhamento_notifiacao_matricula__isnull=False)
            .exclude(introducao_notifiacao_matricula='')
            .exclude(detalhamento_notifiacao_matricula='')
            .filter(data_limite_avaliacao__gte=date.today())
        )
        for pedido_liberacao in qs:
            pedido_liberacao.enviar_notificacoes_matricula()
