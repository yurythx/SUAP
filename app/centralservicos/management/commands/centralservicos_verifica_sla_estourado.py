from datetime import datetime

from django.db.models import F, OuterRef, Subquery

from centralservicos.models import Chamado, HistoricoStatus, StatusChamado
from djtools.management.commands import BaseCommandPlus

"""
python manage.py centralservicos_verifica_sla_estourado
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        status_em_atendimento = (StatusChamado.get_status_aberto(), StatusChamado.get_status_em_atendimento(), StatusChamado.get_status_reaberto())

        """ Se o chamado está ativo, deve verificar pela hora atual. """
        chamados = (
            Chamado.objects.filter(data_limite_atendimento__lt=datetime.now())
            .filter(status__in=status_em_atendimento)
            .exclude(sla_estourado=True)
            .update(sla_estourado=True)
        )
        self.stdout.write(self.style.SUCCESS(f'Atualizou {chamados} chamados ativos com SLA estourado. '))

        """ Se o chamado não está ativo, é necessário ver o tempo que levou para ser atendido, através do primeiro HistoricoStatus """
        # Subquery para pegar a data_hora do primeiro HistoricoStatus resolvido para o Chamado corrente
        primeiro_historico_resolvido = (
            HistoricoStatus.objects.filter(
                chamado=OuterRef('pk'),  # Referência ao Chamado corrente
                status=StatusChamado.get_status_resolvido(),
            )
            .order_by('data_hora')
            .values('data_hora')[:1]
        )

        # Filtra os Chamado cujo primeiro status "resolvido" tem data_hora maior que a data_limite_atendimento
        chamados_com_sla_estourado = (
            Chamado.objects.annotate(primeiro_resolvido_data_hora=Subquery(primeiro_historico_resolvido))
            .filter(primeiro_resolvido_data_hora__gt=F('data_limite_atendimento'))
            .exclude(sla_estourado=True)
            .update(sla_estourado=True)
        )

        self.stdout.write(self.style.SUCCESS(f'Atualizou {chamados_com_sla_estourado} chamados com SLA estourado. '))
