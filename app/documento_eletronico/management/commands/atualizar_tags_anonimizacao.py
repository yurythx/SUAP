import tqdm

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoTexto
from documento_eletronico.status import DocumentoStatus


class Command(BaseCommandPlus):
    """
    Um comando de gerenciamento Django para atualizar tags de anonimização para documentos finalizados.

    Este comando processa todos os documentos finalizados (DocumentoTexto) que não possuem
    tags de anonimização definidas, recupera suas tags processadas pelo suap IA e atualiza
    os documentos com essas tags, se disponíveis.

    Atributos:
        verbosity (bool): Quando ativado, exibe uma barra de progresso usando tqdm

    Uso:
        python manage.py atualizar_tags_anonimizacao [--verbosity]
    """

    def handle(self, *args, **options):
        qs = DocumentoTexto.objects.filter(tags_anonimizacao__isnull=True, status=DocumentoStatus.STATUS_FINALIZADO)
        if options['verbosity']:
            qs = tqdm.tqdm(qs)
        for doc in qs:
            tags = doc.get_tags_suap_ai_processadas()
            if tags:
                doc.tags_anonimizacao = doc.get_tags_suap_ai_processadas()
                doc.save()
