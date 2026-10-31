import datetime

from django.apps import apps
from model_utils import Choices

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

    STATUS_CHOICES = Choices(
        (STATUS_ESPERANDO, 'Aguardando assinatura', 'Aguardando assinatura'),
        (STATUS_INDEFERIDA, 'Indeferida', 'Indeferida'),
        (STATUS_DEFERIDA, 'Deferida', 'Deferida'),
    )


class Command(BaseCommandPlus):
    """
    O tipo de documento Memorando ficou inativo no SUAP a partir de 01/01/2020. A medida atende às orientações do
    Manual de Redação da Presidência da República (2018) e do Manual de Redação Oficial do IFRN (2019).
     Este comando  cancelaa todas as solicitações pendentes existentes em documentos do tipo memorando.
    """

    def handle(self, *args, **options):
        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        TipoDocumento = apps.get_model('documento_eletronico', 'TipoDocumento')
        SolicitacaoAssinatura = apps.get_model('documento_eletronico', 'SolicitacaoAssinatura')
        RegistroAcaoDocumentoTexto = apps.get_model('documento_eletronico', 'RegistroAcaoDocumentoTexto')

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

        executar_simulacao = executar_command == 'SIMULAR'
        executar_pra_valer = executar_command == 'EXECUTAR'
        if not executar_simulacao and not executar_pra_valer:
            print()
            print('Processamento abortado.')
            return

        title = 'Doc. Eletrônico - Command cancela solcitações pendentes para tipos de documento inativo - Memorando'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print('Verificando se existem documentos pertecentes a tipos de documentos inativos ')
        tipos_inativos = TipoDocumento.objects.filter(ativo=False)
        estados_terminais = [DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO]
        documentos = (
            DocumentoTexto.objects.filter(modelo__tipo_documento_texto__in=tipos_inativos)
            .exclude(status__in=estados_terminais)
            .order_by('modelo__tipo_documento_texto')
        )

        qtd_docs = documentos.count()
        counter = 0
        counter_documentos_cancelados_concluido = 0
        counter_documentos_cancelados_aguardando_assinatura = 0
        counter_documentos_cancelados_rascunho = 0
        counter_documentos_cancelados_em_revisao = 0
        count_erros = 0
        exceptions = {}
        if qtd_docs:
            print()
            print(f'Foram encontrados {qtd_docs} documentos neste cenário. Agora os status deles serão corrigidos.')
            for documento in documentos:
                try:
                    print(f'Cancelando Documento {documento} Tipo {documento.modelo.tipo_documento_texto} - Status - {documento.get_status()}')
                    documento.data_cancelamento = datetime.datetime.now()
                    documento.justificativa_cancelamento = """Documento cancelado automaticamente pelo sistema pois
                                            o tipo de documento Memorando ficou inativo no SUAP a partir de 01/01/2020.
                                             A medida atende às orientações do Manual de Redação Oficial do IFRN (2019)."""

                    # Registrar ação
                    registro = RegistroAcaoDocumentoTexto()
                    registro.user = None
                    registro.tipo = 13  # Cancelar Documento
                    registro.documento = documento
                    registro.ip = '127.0.0.1'
                    registro.observacao = documento.justificativa_cancelamento

                    if documento.estah_concluido or documento.estah_assinado:
                        documento.cancelar_documento()
                        print(f'Documento {documento} Cancelado')
                        counter_documentos_cancelados_concluido += 1
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                            registro.save()
                    elif documento.estah_aguardando_assinatura:
                        solicitacoes = SolicitacaoAssinatura.objects.filter(documento=documento, status=SolicitacaoStatus.STATUS_ESPERANDO)
                        for solicitacao in solicitacoes:
                            SolicitacaoAssinatura.objects.filter(condicionantes=solicitacao).delete()
                            solicitacao.delete(ignore_clean=True)
                            print(f'Assinatura de {solicitacao.solicitado} Indeferida do Documento {documento}')
                        documento.cancelar_assinatura()
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                            documento.cancelar_documento()
                        print(f'Documento {documento} Cancelado')
                        counter_documentos_cancelados_aguardando_assinatura += 1
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                            registro.save()
                    elif documento.estah_em_rascunho or documento.estah_em_revisado:
                        documento.concluir()
                        print(f'Documento {documento} Concluido')
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                        documento.cancelar_documento()
                        print(f'Documento {documento} Cancelado')
                        counter_documentos_cancelados_rascunho += 1
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                            registro.save()
                    elif documento.estah_em_revisao:
                        documento.cancelar_revisao()
                        print(f'Revisão do Documento {documento} Cancelada')
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                        documento.cancelar_documento()
                        print(f'Documento {documento} Cancelado')
                        counter_documentos_cancelados_em_revisao += 1
                        if executar_pra_valer:
                            documento.save(ignore_clean=True)
                            registro.save()

                    print()
                    counter += 1
                    percentual = counter / float(qtd_docs) * 100
                    print(f'{percentual}% executado - {counter} de {qtd_docs} registros atualizados')
                except Exception as e:
                    count_erros += 1
                    exceptions[e] = e + documento.id
                    continue

        else:
            print()
            print('Nenhum documento a ser corrigido.')

        # print()
        print(f'{counter_documentos_cancelados_concluido}  documentos cancelados - Concluido')
        print(f'{counter_documentos_cancelados_aguardando_assinatura}  documentos cancelado - Aguardando Assinatura')
        print(f'{counter_documentos_cancelados_rascunho}  documentos cancelados -  Rascunho')
        print(f'{counter_documentos_cancelados_em_revisao}  documentos cancelados -  Em Revisão')
        total_docs_cancelados = (
            counter_documentos_cancelados_concluido
            + counter_documentos_cancelados_aguardando_assinatura
            + counter_documentos_cancelados_rascunho
            + counter_documentos_cancelados_em_revisao
        )
        print(f'{total_docs_cancelados} documentos cancelados de {counter} documentos analisados')
        # print("{} registros de finalização de documentos foram registrados com  a data_hora da última assinatura do documento".format(counter_data_ultima_assinatura_documento))
        print()
        if exceptions:
            print('HOUVE ERRO NA EXECUÇÃO DOS SEGUINTES ITENS')
            for exception in exceptions:
                print(exception)
        print('Fim do processamento.')
        if not executar_pra_valer:
            print(
                'OBS: Este processamento foi apenas uma SIMULAÇÃO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opção "EXECUTAR".'
            )
