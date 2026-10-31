from bs4 import BeautifulSoup

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoTexto
from documento_eletronico.status import DocumentoStatus
from rh.models import Servidor


class Command(BaseCommandPlus):
    """
    Esse comando vai atualizar a vinculação dos documentos com os usuários do sistema.
    """

    def handle(self, *args, **options):
        title = 'Doc. Eletrônico - Command para vincular os vinculos dos servidores aos documentos do sistema'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))
        for documento in DocumentoTexto.objects.filter(
            modelo__tipo_documento_texto__nome='Portaria', interessados__isnull=True, status=DocumentoStatus.STATUS_FINALIZADO
        ):
            texto_documento = BeautifulSoup(documento.corpo, 'html.parser').text
            servidores = Servidor.objects.all()
            for servidor in servidores:
                if servidor.matricula in texto_documento:
                    documento.interessados.add(servidor)
        print('Fim do processamento.')
