from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db.models import CharField
from django.db.models.functions import Cast
from reversion.models import Version

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoStatus, DocumentoTexto


class Command(BaseCommandPlus):
    """
    Command para deletar as revisões do documento texto quando: Finalizados e Cancelados; e
    Para deixar apenas 3 revisões dos documentos não finalizados e não cancelados

    """

    def handle(self, *args, **options):
        verbosity = int(options['verbosity'])
        # 1. Criamos a subquery transformando o ID em String (CharField)
        documentos_ids_string = (
            DocumentoTexto.objects.filter(status__in=[DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO])
            .annotate(pk_as_string=Cast('pk', CharField()))
            .values('pk_as_string')
        )
        # 2. Agora o banco conseguirá comparar character varying com character varying
        Version.objects.using(None).get_for_model(DocumentoTexto).filter(
            content_type=ContentType.objects.get_for_model(DocumentoTexto), object_id__in=documentos_ids_string
        ).delete()

        # KEEP 3 Revisions
        call_command('deleterevisions', keep=3, verbosity=verbosity)
