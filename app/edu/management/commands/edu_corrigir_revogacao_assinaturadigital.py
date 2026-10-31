import datetime

from djtools.management.commands import BaseCommandPlus
from edu.models import AssinaturaDigital


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = AssinaturaDigital.objects.filter(registro_emissao_diploma__cancelado=True, data_revogacao__isnull=True)
        for assinatura in qs:
            assinatura.motivo_revogacao = assinatura.registro_emissao_diploma.motivo_cancelamento
            assinatura.data_revogacao = datetime.datetime.now()
            assinatura.save()
