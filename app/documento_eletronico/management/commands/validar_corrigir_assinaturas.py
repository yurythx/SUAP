from __future__ import annotations

import datetime
import os
from typing import TYPE_CHECKING

from django.apps import apps
from django.db.models import Count

from comum.management.commands.terminal_utils import Terminal
from djtools.management.commands import BaseCommandPlus
from documento_eletronico.assinar_documento import gerar_assinatura_documento_senha, verificar_assinatura_senha

if TYPE_CHECKING:
    from documento_eletronico.models import AssinaturaDocumentoTexto as AssinaturaDocumentoTextoModel

Assinatura = apps.get_model('documento_eletronico', 'Assinatura')
DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
TipoDocumentoTexto = apps.get_model('documento_eletronico', 'TipoDocumentoTexto')
AssinaturaDocumentoTexto = apps.get_model('documento_eletronico', 'AssinaturaDocumentoTexto')


class Command(Terminal, BaseCommandPlus):
    MSG_CONCLUSAO_ALERTA = (
        'Processamento finalizado com ALERTA. Assinaturas invalidas nao corrigidas devido a parametro "corrigir_assinaturas_invalidas=False"'
    )
    MSG_CONCLUSAO_ERRO = 'Processamento finalizado com ERRO'
    MSG_CONCLUSAO_SUCESSO = 'Processamento finalizado com SUCESSO'

    def __init__(self):
        Terminal.__init__(self)
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    def get_documento_id_para_reiniciar_processamento(self):
        documento_id = None

        if os.path.exists(self.log_file):
            with open(self.log_file) as file:
                lines = file.readlines()
                lines.reverse()
                for line in lines:
                    if self.MSG_CONCLUSAO_ERRO in line:
                        documento_id = int(line.split('=')[-1])
                        break
                    elif self.MSG_CONCLUSAO_SUCESSO in line:
                        break
        return documento_id

    def corrigir_assinatura(self, assinatura_documento_texto: AssinaturaDocumentoTextoModel) -> tuple[bool, str, str]:
        nova_assinatura_hmac = gerar_assinatura_documento_senha(
            documento=assinatura_documento_texto.documento, vinculo=assinatura_documento_texto.assinatura.vinculo
        )

        # Descomente esta linha caso queira invalidar a assinatura de propósito para simular uma assinatura que
        # nao cosegue ser regerada de maneira valida.
        # nova_assinatura_hmac = nova_assinatura_hmac + '[InvalidandoAssinatura]'
        nova_assinatura_eh_valida = verificar_assinatura_senha(
            documento=assinatura_documento_texto.documento,
            vinculo=assinatura_documento_texto.assinatura.vinculo,
            assinatura_hmac=nova_assinatura_hmac,
        )
        if nova_assinatura_eh_valida:
            # O método save da entidade Assinatura esta impedindo edições, por isso estamos fazendo o ajuste via
            # update no banco.
            Assinatura.objects.filter(id=assinatura_documento_texto.assinatura.id).update(hmac=nova_assinatura_hmac)
            msg = 'SUCESSO: Assinatura regerada com sucesso.'
        else:
            msg = 'ERRO: Nao foi possivel gerar uma nova assinatura valida.'

        return nova_assinatura_eh_valida, nova_assinatura_hmac, msg

    def handle(self, *args, **options):
        self.log_title(f'Documento Eletronico - {__name__}')

        self.add_empty_line()
        self.log(
            'O objetivo deste command eh varrer todos os documentos que tem pelo menos uma assinatura e verificar se \n'
            'todas as assinaturas existentes estao validas. Em tese nenhuma assinatura eh pra estar invalida, mas por \n'
            'conta de bug que havia na funcionalidade "remocao de solicitacao de assinatura", pode ter ocorrido de \n'
            'um documento ao inves de estar AGUARDANDO ASSINATURA estivesse com o status CONCLUIDO, o que permitiria \n'
            'indevidamente a edicao de um documento assinado.'
        )

        executar_command = options.get('executar_command')
        if executar_command is None:
            executar_command = self.ask_yes_or_no('Deseja continuar')
        if not executar_command:
            self.add_empty_line()
            self.log('Processamento abortado.')
            return

        corrigir_assinaturas_invalidas = options.get('corrigir_assinaturas_invalidas')
        if corrigir_assinaturas_invalidas is None:
            corrigir_assinaturas_invalidas = self.ask_yes_or_no('Deseja corrigir assinaturas invalidas?')

        self.add_empty_line()
        self.log('Inicio do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

        self.add_empty_line()
        self.log_title('Verificando para cada documento assinado se todas as suas assinaturas estao validas')
        documentos_assinados = DocumentoTexto.objects.all()
        documentos_assinados = documentos_assinados.annotate(qtd_assinaturas=Count('assinaturadocumentotexto'))
        documentos_assinados = documentos_assinados.filter(qtd_assinaturas__gte=1)

        documento_id_para_reiniciar_processamento = self.get_documento_id_para_reiniciar_processamento()
        if documento_id_para_reiniciar_processamento:
            self.log(f'Reiniciando processamento a partir do documento de id {documento_id_para_reiniciar_processamento}...')
            documentos_assinados = documentos_assinados.filter(id__gte=documento_id_para_reiniciar_processamento)

        # documentos_assinados = documentos_assinados.filter(id__in=[8253, 13400])
        documentos_assinados_pks = documentos_assinados.order_by('id').values_list('id', flat=True)

        self.log(f'Total de documentos assinados: {documentos_assinados_pks.count()}')
        self.log('Verificando se existem documentos com assinaturas invalidas...')
        docs_com_assinaturas_invalidas = []
        docs_com_assinaturas_invalidas_impossiveis_corrigir = []

        for doc_assinado_pk in documentos_assinados_pks:
            doc = DocumentoTexto.objects.get(id=doc_assinado_pk)
            assinaturas_doc_texto = doc.assinaturadocumentotexto_set.all()
            assinaturas_doc_texto_validas = []
            assinaturas_doc_texto_invalidas = []
            for ass_doc_texto in assinaturas_doc_texto:
                if ass_doc_texto.validar_documento():
                    assinaturas_doc_texto_validas.append(ass_doc_texto)
                else:
                    assinaturas_doc_texto_invalidas.append(ass_doc_texto)

            dados_doc_com_assinaturas_invalidas = {}
            if assinaturas_doc_texto_invalidas:
                dados_doc_com_assinaturas_invalidas['documento'] = doc
                dados_doc_com_assinaturas_invalidas['assinatura_documento_texto_validas'] = assinaturas_doc_texto_validas
                dados_doc_com_assinaturas_invalidas['assinatura_documento_texto_invalidas'] = assinaturas_doc_texto_invalidas
                docs_com_assinaturas_invalidas.append(dados_doc_com_assinaturas_invalidas)

        if docs_com_assinaturas_invalidas:
            self.add_empty_line()
            self.log(f'PROBLEMA: Foram encontrados {len(docs_com_assinaturas_invalidas)} documentos com assinaturas invalidas.')

            if corrigir_assinaturas_invalidas:
                self.log('Iniciando reprocessamento das assinaturas invalidas para tentar corrigi-las...')
                for doc_ass_invalida in docs_com_assinaturas_invalidas:
                    doc = doc_ass_invalida['documento']
                    assinaturas_doc_texto_validas = doc_ass_invalida['assinatura_documento_texto_validas']
                    assinaturas_doc_texto_invalidas = doc_ass_invalida['assinatura_documento_texto_invalidas']

                    self.log_title(f'Documento: {doc.identificador} (id: {doc.id})')
                    self.log('Assinaturas validas:')
                    if assinaturas_doc_texto_validas:
                        for ass_doc_texto_valida in assinaturas_doc_texto_validas:
                            assinatura = ass_doc_texto_valida.assinatura
                            self.log(
                                ' - {} em {} (id: {}, hmac: {})'.format(
                                    assinatura.pessoa.nome_usual,
                                    assinatura.data_assinatura.strftime('%d/%m/%Y %H:%M:%S'),
                                    assinatura.id,
                                    assinatura.hmac,
                                )
                            )
                    else:
                        self.log(' - Nenhuma')

                    self.log('Assinaturas invalidas:')
                    if assinaturas_doc_texto_invalidas:
                        for ass_doc_texto_invalida in assinaturas_doc_texto_invalidas:
                            assinatura = ass_doc_texto_invalida.assinatura
                            self.log(
                                ' - {} em {} (id: {}, hmac: {})'.format(
                                    assinatura.pessoa.nome_usual,
                                    assinatura.data_assinatura.strftime('%d/%m/%Y %H:%M:%S'),
                                    assinatura.id,
                                    assinatura.hmac,
                                )
                            )

                            nova_assinatura_eh_valida, nova_assinatura_hmac, msg = self.corrigir_assinatura(ass_doc_texto_invalida)
                            self.log(f'   {msg} (id: {assinatura.id}, hmac: {nova_assinatura_hmac})')

                            if not nova_assinatura_eh_valida:
                                docs_com_assinaturas_invalidas_impossiveis_corrigir.append(doc_ass_invalida)
                    else:
                        self.log(' - Nenhuma')
        else:
            self.log('SUCESSO: Todos os documentos estao com suas assinaturas validas.')

        self.add_empty_line()

        if docs_com_assinaturas_invalidas and not corrigir_assinaturas_invalidas:
            self.log(f'{self.MSG_CONCLUSAO_ALERTA}')
        elif docs_com_assinaturas_invalidas_impossiveis_corrigir:
            self.log(
                '{}. Documento para reiniciar processamento: id={}'.format(
                    self.MSG_CONCLUSAO_ERRO, docs_com_assinaturas_invalidas_impossiveis_corrigir[0]['documento'].id
                )
            )
        else:
            self.log(f'{self.MSG_CONCLUSAO_SUCESSO}')

        self.add_empty_line()
        self.log('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.save_log(self.log_file)
        self.log(f'Log da operacao salvo em {self.log_file}', color='green', opts=('bold',))

        if docs_com_assinaturas_invalidas_impossiveis_corrigir:
            msg = f'ERRO: Existem um total de {len(docs_com_assinaturas_invalidas_impossiveis_corrigir)} assinaturas invalidas que nao poderam ser corrigidas. Ver detalhes no log.'
            raise Exception(msg)
