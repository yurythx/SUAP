from sentry_sdk import capture_exception

from centralservicos.models import Servico
from djtools.management.commands import BaseCommandPlus

"""
python manage.py centralservicos_atualizar_estatisticas_servicos

Recalcula as estatísticas de todos os serviços pendentes (execução manual). Para recalcular todos
os serviços, marque-os antes como pendentes: Servico.objects.update(estatisticas_pendentes=True).
"""


class Command(BaseCommandPlus):
    def handle(self, *args, **options) -> None:
        """Recalcula as estatísticas dos serviços pendentes, um de cada vez."""
        pendentes = list(Servico.objects.filter(estatisticas_pendentes=True).order_by('pk').values_list('pk', flat=True))
        for servico_id in pendentes:
            try:
                Servico.recalcular_estatisticas_pendentes(servico_id)
            except Exception as erro:
                # A marca já foi devolvida; a falha de um serviço não derruba os demais.
                capture_exception(erro)
                self.stderr.write(f'Estatísticas do serviço {servico_id} não atualizadas: {erro!r}')
