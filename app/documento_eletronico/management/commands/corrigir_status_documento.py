from django.apps import apps
from django.db.models import Count

from djtools.management.commands import BaseCommandPlus


# Classes copiadas de documento_eletronico.models já que não é recomendado fazer o import direto uma vez que esse
# command será executado dentro de uma migration.
class DocumentoStatus:
    STATUS_RASCUNHO = 1
    STATUS_CONCLUIDO = 2
    STATUS_EM_REVISAO = 3
    STATUS_REVISADO = 4
    STATUS_AGUARDANDO_ASSINATURA = 5
    STATUS_ASSINADO = 6
    STATUS_FINALIZADO = 7
    STATUS_CANCELADO = 8


class SolicitacaoStatus:
    STATUS_ESPERANDO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3


class Command(BaseCommandPlus):
    """
    Command criado corrigir status de documento
    """

    def handle(self, *args, **options):
        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        SolicitacaoAssinatura = apps.get_model('documento_eletronico', 'SolicitacaoAssinatura')

        title = 'Doc. Eletrônico - Command para Corrigir Status Documento'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print('Verificando se existem documentos assinados com status RASCUNHO, CONCLUÍDO, EM REVISÃO ou REVISADO.')
        documentos = DocumentoTexto.objects.filter(
            status__in=[
                DocumentoStatus.STATUS_RASCUNHO,
                DocumentoStatus.STATUS_CONCLUIDO,
                DocumentoStatus.STATUS_EM_REVISAO,
                DocumentoStatus.STATUS_REVISADO,
            ]
        )
        documentos = documentos.annotate(qtd_assinaturas=Count('assinaturadocumentotexto'))
        documentos = documentos.filter(qtd_assinaturas__gte=1)

        qtd_docs = documentos.count()
        if qtd_docs:
            print()
            print(f'Fora encontrados {qtd_docs} documentos neste cenário. Agora os status deles serão corrigidos.')
            for doc in documentos:
                qtd_solicitacoes_assinatura_pendentes = SolicitacaoAssinatura.objects.filter(
                    documento=doc, status=SolicitacaoStatus.STATUS_ESPERANDO
                ).count()

                print()
                print(f'Documento {doc.identificador} (id: {doc.id})')
                print(f'Qtd. Assinaturas: {doc.qtd_assinaturas}  /  Qtd. Solicitações Assinaturas Pendentes: {qtd_solicitacoes_assinatura_pendentes}')
                if qtd_solicitacoes_assinatura_pendentes == 0:
                    doc.marcar_como_assinado()
                    print('Status do documento alterado para ASSINADO.')
                else:
                    doc.solicitar_assinatura()
                    print('Status do documento alterado para AGUARDANDO ASSINATURA.')

                doc.save()
        else:
            print()
            print('Nenhum documento a ser ajustado.')

        print()
        print('Fim do processamento.')
