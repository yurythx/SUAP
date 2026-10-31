from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoTexto
from documento_eletronico.utils import indexar_documento_texto


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        qs = DocumentoTexto.objects.filter(modelo__tipo_documento_texto__permite_busca_corpo_conteudo=True, corpo_indexado__isnull=True)
        for pk, corpo in qs.values_list('pk', 'corpo'):
            indexar_documento_texto(pk, corpo)
