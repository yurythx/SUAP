import datetime

from django.apps import apps
from django.db import transaction
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.status import NivelAcesso


class Command(BaseCommandPlus):
    @transaction.atomic()
    def handle(self, *args, **options):
        ini = datetime.datetime.now()

        title = 'Processo Eletronico - Command que atualiza o nivel de acesso dos termos de ciencias publicos para restritos.'
        self.stdout.write('')
        self.stdout.write('- ' * len(title))
        self.stdout.write(f'{title}')
        self.stdout.write('- ' * len(title))

        DocumentoDigitalizadoProcesso = apps.get_model('processo_eletronico', 'DocumentoDigitalizadoProcesso')

        docs_digitalizados = DocumentoDigitalizadoProcesso.objects.filter(
            Q(documento__nivel_acesso=NivelAcesso.NIVEL_ACESSO_PUBLICO) & Q(documento__assunto__icontains='Termo de Ciência: Conhecimento/Notifição')
        ).order_by('processo__numero_protocolo_fisico')
        qtd_docs_digitalizados = docs_digitalizados.count()

        title = 'Quantidade de Documentos'
        self.stdout.write('')
        self.stdout.write('- ' * len(title))
        self.stdout.write(f'{title}')
        self.stdout.write('- ' * len(title))
        self.stdout.write(f'Termos de Ciencias a serem atualizados: {qtd_docs_digitalizados}')
        self.stdout.write('- ' * len(title))
        self.stdout.write('')

        if docs_digitalizados.exists():
            title = 'Lista de Documentos'
            self.stdout.write('- ' * len(title))
            self.stdout.write(f'{title}')
            self.stdout.write('- ' * len(title))
            for doc_digital in docs_digitalizados:
                self.stdout.write(f'{doc_digital.documento} #{str(doc_digital.documento.id).ljust(5)} - {doc_digital.processo}')
                doc_digital.documento.nivel_acesso = NivelAcesso.NIVEL_ACESSO_RESTRITO
                doc_digital.documento.save()
            self.stdout.write('- ' * len(title))

        fim = datetime.datetime.now()
        self.stdout.write('')
        self.stdout.write('- ' * len(title))
        self.stdout.write(f'Início: {ini} - Final: {fim}')
        self.stdout.write(f'Total de documentos atualizados para o nível de acesso restrito: {qtd_docs_digitalizados}.')
        self.stdout.write('- ' * len(title))
