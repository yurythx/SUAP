from django.apps import apps

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


class Command(BaseCommandPlus):
    """
    Command criado corrigir problema gerado na funcionallidade de solicitar asinatura com anexação
    a processo, onde não estava sendo registrada a ação de finalização do documento
    """

    def handle(self, *args, **options):
        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        DocumentoTextoProcesso = apps.get_model('processo_eletronico', 'DocumentoTextoProcesso')
        RegistroAcaoDocumentoTexto = apps.get_model('documento_eletronico', 'RegistroAcaoDocumentoTexto')
        SolicitacaoAssinatura = apps.get_model('documento_eletronico', 'SolicitacaoAssinatura')
        SessionInfo = apps.get_model('comum', 'SessionInfo')

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

        executar_simulacao = executar_command == 'SIMULAR'
        executar_pra_valer = executar_command == 'EXECUTAR'
        if not executar_simulacao and not executar_pra_valer:
            print()
            print('Processamento abortado.')
            return

        title = 'Doc. Eletrônico - Command registra a ação de finalizar para documentos finalizados quenão possuem o registro'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        print('Verificando se existem documentos finalizados que não possuem ação registrada do tipo 14 - TIPO_FINALIZACAO ')
        documentos = DocumentoTexto.objects.filter(status=7).exclude(registroacaodocumentotexto__tipo=14).distinct()

        qtd_docs = documentos.count()
        counter = 0
        counter_data_inclusao_no_processo = 0
        counter_data_ultima_assinatura_documento = 0
        count_erros = 0
        exceptions = {}
        if qtd_docs:
            print()
            print(f'Foram encontrados {qtd_docs} documentos neste cenário. Agora os status deles serão corrigidos.')
            for documento in documentos:
                try:
                    solicitacao = SolicitacaoAssinatura.objects.filter(documento=documento).first()
                    print(f'Solicitado {solicitacao.solicitado}')
                    # solicitado=documento.assinaturas.first(),
                    # data_resposta__isnull=True).first()
                    if SessionInfo.objects.filter(user=solicitacao.solicitado.user).exists():
                        ip_address = SessionInfo.objects.filter(user=solicitacao.solicitado.user).order_by('-date_time').first().ip_address
                    else:
                        ip_address = '127.0.0.1'
                    # Registrar ação
                    registro = RegistroAcaoDocumentoTexto()
                    registro.user = solicitacao.solicitante
                    registro.tipo = 14
                    registro.documento = documento
                    registro.ip = ip_address
                    registro.observacao = f'Documento finalizado automaticamente após assinatura de {solicitacao.solicitado}.'
                    if executar_pra_valer:
                        registro.save()
                        # Atualiza a data do registro
                    if documento.assinaturas():
                        if hasattr(DocumentoTextoProcesso.objects.filter(documento=documento).first(), 'data_hora_inclusao'):
                            data_hora_inclusao_no_processo = DocumentoTextoProcesso.objects.filter(documento=documento).first().data_hora_inclusao
                            counter_data_inclusao_no_processo += 1
                            if executar_simulacao:
                                print(
                                    f'Para o documento de ID {documento.id} esta sendo registrada a finalizacao com a data_hora da inclusao no processo'
                                )
                        else:
                            data_hora_inclusao_no_processo = (
                                documento.assinaturas().order_by('-assinatura__data_assinatura')[0].assinatura.data_assinatura
                            )
                            counter_data_ultima_assinatura_documento += 1
                            if executar_simulacao:
                                print(
                                    f'Para o documento de ID {documento.id} esta sendo registrada a finalizacao com a data_hora da ultima assinatura'
                                )

                        if executar_pra_valer:
                            RegistroAcaoDocumentoTexto.objects.filter(id=registro.id).update(data=data_hora_inclusao_no_processo)
                    #
                    print()
                    print(
                        f'Ação registrada para documento {documento.identificador} (id: {documento.id} - Data de Inclusao: {data_hora_inclusao_no_processo})'
                    )
                    counter += 1
                    percentual = counter / float(qtd_docs) * 100
                    print(f'{percentual}% executado - {counter} de {qtd_docs} registros atualizados')
                except Exception as e:
                    count_erros += 1
                    exceptions[documento] = e
                    continue

        else:
            print()
            print('Nenhum documento a ser corrigido.')

        print()
        print(
            f'{counter_data_inclusao_no_processo} registros de finalização de documentos foram registrados com  a data_hora de inclusao no processo'
        )
        print(
            f'{counter_data_ultima_assinatura_documento} registros de finalização de documentos foram registrados com  a data_hora da última assinatura do documento'
        )
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
