from djtools.management.commands import BaseCommandPlus
from edu.models import RegistroEmissaoDiploma


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        RegistroEmissaoDiploma.objects.filter(cancelado=True).update(situacao=RegistroEmissaoDiploma.CANCELADO)
        RegistroEmissaoDiploma.objects.filter(cancelado=False).update(situacao=RegistroEmissaoDiploma.FINALIZADO)
        RegistroEmissaoDiploma.objects.filter(assinaturadigital__status_documentacao_academica_digital__isnull=False).update(
            situacao=RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DOCUMENTACAO
        )
