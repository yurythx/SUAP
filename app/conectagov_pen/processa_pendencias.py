import base64
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404

from comum.models import Configuracao, User, Vinculo
from conectagov_pen.utils import (
    as_pdf,
    get_hash_documento,
    get_nivel_acesso_documento,
    get_tipos_de_documentos_nao_mapeados_no_recebimento,
    monta_recibo,
    processo_possui_tipos_de_documentos_nao_mapeados_no_envio,
    processo_possui_tipos_de_documentos_nao_mapeados_no_recebimento,
    tamanho_em_bytes,
)
from djtools.middleware import threadlocals as tl
from djtools.utils import mask_cnpj, mask_numbers
from djtools.views import httprr
from documento_eletronico.models import DocumentoDigitalizado
from processo_eletronico.models import DocumentoDigitalizadoProcesso, Processo, Tramite
from rh.models import Setor

from .api_pen_services import (
    barramento_disponivel,
    enviar_recibo_tramite,
    get_estrutura_por_id,
    get_metadados,
    get_recibo_tramite,
    get_tramite,
    get_tramites_pendentes,
    receber_componente_digital,
    recusar_tramite,
)
from .connect_pen import API_PEN_Exception
from .models import DocumentoProcessoBarramento, HipoteseLegalPEN, MapeamentoTiposDocumento, ProcessoBarramento, TramiteBarramento
from .serializers import ProcessoConectaGOVSchema

logger = logging.getLogger(__name__)

MSG_USUARIO_RECEBIMENTO_NAO_CONFIGURADO = (
    'Recebimento de trâmite do barramento sem usuário: configure o "Usuário Responsável pelos Processos Recebidos do Barramento" '
    '(conectagov_pen.usuario_recebimento_pen). O trâmite segue pendente para a próxima execução.'
)


def _usuario_de_recebimento() -> User | None:
    """Usuário em nome de quem o processo recebido é criado: o logado (tela) ou, sem ele (Beat, comando), o configurado."""
    usuario = tl.get_user()
    if getattr(usuario, 'is_authenticated', False):
        return usuario
    usuario_id = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='usuario_recebimento_pen')
    return User.objects.filter(pk=usuario_id).first() if usuario_id else None


@contextmanager
def _em_nome_do_usuario_de_recebimento() -> Iterator[None]:
    """Põe no threadlocal o usuário de recebimento durante a criação do processo, restaurando o anterior ao final.

    `Processo.modificado_por` e `DocumentoProcesso.usuario_inclusao` são NOT NULL e vêm do threadlocal (`CurrentUserField`).
    """
    usuario = _usuario_de_recebimento()
    if usuario is None:
        raise ImproperlyConfigured(MSG_USUARIO_RECEBIMENTO_NAO_CONFIGURADO)
    usuario_anterior = tl.get_user()
    tl.context.user = usuario
    try:
        yield
    finally:
        tl.context.user = usuario_anterior


@transaction.atomic()
def processo_pen(processo):
    obj = get_object_or_404(Processo, pk=processo.id)
    if processo_possui_tipos_de_documentos_nao_mapeados_no_envio(obj.get_todos_documentos_processo()):
        msg = f'Processo {processo.numero_protocolo_fisico} possui tipos de documentos não mapeados para o Tramita Gov.BR.'
        return httprr(obj.get_absolute_url(), msg, tag='warning')

    tamanho_maximo_doc_config = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='tamanhoMaximoDocumento_pen')
    # Cria um novo registro de tramite_barramento para o processo
    documentos_processo = []
    documentos_conteudo = []
    ordem = 0
    for doc in obj.get_partes_processo_pdf(leitura_para_barramento=False):
        if doc['tipo_parte_processo'] != 'CAPA':
            ordem += 1
            if doc['objeto_fonte'].id:
                documento = {
                    'ordem': ordem,
                    'id_documento': doc['objeto_fonte'].id,
                    'hash_documento': get_hash_documento(doc['pdf']),
                    'tipo_parte_processo': doc['tipo_parte_processo'],
                    'tamanho_bytes': tamanho_em_bytes(doc['pdf']),
                }
            else:
                documento = {
                    'ordem': ordem,
                    'hash_documento': get_hash_documento(doc['pdf']),
                    'tipo_parte_processo': doc['tipo_parte_processo'],
                    'tamanho_bytes': tamanho_em_bytes(doc['pdf']),
                }
            documento_com_conteudo = {'documento': documento, 'conteudo': doc['pdf']}

            msg = (
                f'Existe(m) documento(s) com tamanho maior que os {tamanho_maximo_doc_config} MB permitidos pelo SUAP para envios via Tramita Gov.BR.'
            )
            if (documento['tamanho_bytes'] / 1024 / 1024) > float(tamanho_maximo_doc_config):
                return httprr(processo.get_absolute_url(), msg, tag='warning')

            documentos_conteudo.append(documento_com_conteudo)
            documentos_processo.append(documento)
    qtd_docs = len(documentos_processo)

    if ProcessoBarramento.objects.filter(processo=obj).exists():
        processo_barramento = ProcessoBarramento.objects.get(processo=obj)
    else:
        processo_barramento = ProcessoBarramento()
        processo_barramento.processo = obj
        processo_barramento.save()

    tramite_barramento = TramiteBarramento.objects.filter(processo_barramento=processo_barramento.id, status=TramiteBarramento.STATUS_PENDENTE_ENVIO)
    if tramite_barramento.exists():
        tramite_barramento = tramite_barramento[0]
    else:
        tramite_barramento = TramiteBarramento()
        tramite_barramento.processo_barramento = processo_barramento
        tramite_barramento.documentos = json.dumps(documentos_processo)
        tramite_barramento.qtd_documentos = qtd_docs
        tramite_barramento.status = TramiteBarramento.STATUS_PENDENTE_ENVIO
        tramite_barramento.save()

    for doc in documentos_conteudo:
        if DocumentoProcessoBarramento.objects.filter(processo_barramento=processo_barramento.id, ordem=doc['documento']['ordem']).exists():
            documento_processo_barramento = DocumentoProcessoBarramento.objects.get(
                processo_barramento=processo_barramento.id, ordem=doc['documento']['ordem']
            )
            documentos_processo[doc['documento']['ordem'] - 1]['hash_documento'] = documento_processo_barramento.hash_para_barramento
            documentos_conteudo[doc['documento']['ordem'] - 1]['documento']['hash_documento'] = documento_processo_barramento.hash_para_barramento
            documentos_conteudo[doc['documento']['ordem'] - 1]['documento']['tamanho_bytes'] = tamanho_em_bytes(
                documento_processo_barramento.conteudo_arquivo
            )
            documentos_conteudo[doc['documento']['ordem'] - 1]['conteudo'] = documento_processo_barramento.conteudo_arquivo
            if documento_processo_barramento.enviado:
                documentos_conteudo[doc['documento']['ordem'] - 1]['documento']['tamanho_bytes'] = tamanho_em_bytes(
                    documento_processo_barramento.conteudo_arquivo
                )
                documentos_conteudo[doc['documento']['ordem'] - 1]['conteudo'] = documento_processo_barramento.conteudo_arquivo
            elif documento_processo_barramento.recebido:
                documentos_conteudo[doc['documento']['ordem'] - 1]['documento']['tamanho_bytes'] = tamanho_em_bytes(
                    base64.b64decode(documento_processo_barramento.conteudo_arquivo)
                )
                documentos_conteudo[doc['documento']['ordem'] - 1]['conteudo'] = base64.b64decode(documento_processo_barramento.conteudo_arquivo)
        elif not DocumentoProcessoBarramento.objects.filter(processo_barramento=processo_barramento.id, ordem=doc['documento']['ordem']).exists():
            documento_processo_barramento = DocumentoProcessoBarramento()
            documento_processo_barramento.processo_barramento = processo_barramento
            documento_processo_barramento.ordem = doc['documento']['ordem']
            documento_processo_barramento.enviado = False
            documento_processo_barramento.conteudo_arquivo = doc['conteudo']
            documento_processo_barramento.hash_para_barramento = doc['documento']['hash_documento'].decode()
            documento_processo_barramento.save()

    if documentos_processo:
        context = {'documentos': documentos_processo, 'processo_barramento': processo_barramento}
        data = ProcessoConectaGOVSchema.from_orm(obj, context=context).dict()
        return [data, documentos_conteudo, processo_barramento, tramite_barramento]
    else:
        return None


def processar_pendencias():
    """
    Processa dos tramites pendented do barramento de acordo com o status, sendo:
    1 - Aguardando envio de arquivos digitais
    2 - Arquivos digitais recebidos pela solução
    3 - Metadados recebidos pelo destinatário
    4 - Arquivos digitais recebidos pelo destinatário
    5 - Recibo de conclusão do trâmite recebido pelo barramento
    6 - Recibo de conclusão do trâmite recebido pelo remetente
    7  - Cancelado pelo remetente (Pode ser cancelado até que os metadados ainda não tenham sido recebidos pelo destinataria)
    """
    if barramento_disponivel():
        pendentes = get_tramites_pendentes()
        if pendentes:
            processar_pendencias_recebimento(pendentes)
            processar_pendencias_envio(pendentes)
            return True
        if not pendentes:
            # Caso tenha ocorrido alguma interrupção e o o trâmite não tenha sido totalmente recebido ou recusado, será realizado o recebimento
            processar_tramites_nao_recebidos()
            return True
    return None


def processar_tramites_nao_recebidos():
    """

    :return:
    """
    tramites_a_receber = TramiteBarramento.objects.filter(status=TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO)
    for tramite_barramento in tramites_a_receber:
        processo_hashs = []
        processo_barramento = tramite_barramento.processo_barramento
        if processo_barramento:
            processo_hashs = processo_barramento.get_hashs_documentos_processo()

        # Se não possui componentes digitais a receber não há o que processar
        if tramite_barramento.componentes_digitais_a_receber:
            processar_recebimento_tramite_a_receber(tramite_barramento, processo_hashs)
        else:
            logger.info(f'Trâmite pendente de recebimento mas sem componentes digitais a receber: {tramite_barramento.id}')
            tramite_barramento.status = TramiteBarramento.STATUS_CANCELADO
            tramite_barramento.save()


def processar_pendencias_recebimento(pendentes):
    status_de_envio = [5, 8]
    if pendentes:
        for pendente in pendentes:
            if pendente['status'] not in status_de_envio:
                processo_metadados = get_metadados(pendente['IDT'])
                tramite = get_tramite(pendente['IDT'])

                # Cria lista com hashs dos documentos que existem no SUAP
                processo_hashs = []
                processo_barramento = ProcessoBarramento.objects.filter(nre_barramento_pen=processo_metadados['nre']).first()

                if processo_barramento:
                    processo_hashs = processo_barramento.get_hashs_documentos_processo()
                else:
                    processo_barramento = ProcessoBarramento()
                    processo_barramento.nre_barramento_pen = processo_metadados['nre']
                    processo_barramento.criado_no_suap = False
                    processo_barramento.save()

                tramite_barramento = None
                if pendente['status'] == 4 and 'IDT' in tramite:
                    tramite_barramento = TramiteBarramento.objects.filter(
                        processo_barramento__nre_barramento_pen=processo_metadados['nre'],
                        status__in=[TramiteBarramento.STATUS_RECEBIDO, TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO],
                        id_tramite_barramento=tramite['IDT'],
                    ).first()

                if not tramite_barramento:
                    id_tramite = tramite.get('IDT') or pendente.get('IDT')
                    tramites_barramento = TramiteBarramento.objects.filter(
                        processo_barramento__nre_barramento_pen=processo_metadados['nre'],
                        status__in=[TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO, TramiteBarramento.STATUS_RECUSADO],
                        id_tramite_barramento=id_tramite,
                    )

                    tramite_barramento = tramites_barramento.last()
                    # TESTE
                    if tramites_barramento:
                        logger.info('TRAMITE BARRAMENTO LOCALIZADO: NRE: {}, IDT: {}'.format(processo_metadados['nre'], id_tramite))

                    # FIM TESTE
                    tramite_barramento, created = tramites_barramento.update_or_create(
                        metadados_processo=processo_metadados,
                        processo_barramento=processo_barramento,
                        documentos=processo_metadados['processo']['documentos'],
                        id_tramite_barramento=id_tramite,
                        status=TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO,
                    )

                    # teste
                    if created:
                        logger.info(
                            f'NOVO TRAMITE CRIADO: id {tramite_barramento.id} NRE {tramite_barramento.processo_barramento.nre_barramento_pen} Componenetes Digitais {tramite_barramento.componentes_digitais_a_receber}'
                        )
                    else:
                        logger.info(
                            f'TRAMITE JA EXISTE: id {tramite_barramento.id} NRE {tramite_barramento.processo_barramento.nre_barramento_pen} Componenetes Digitais {tramite_barramento.componentes_digitais_a_receber}'
                        )
                    # fim teste

                # Verifica se possui documentos não mapeados e rejeita o tramite caso existam
                if processo_possui_tipos_de_documentos_nao_mapeados_no_recebimento(processo_metadados['processo']['documentos']):
                    lista_nao_mapeados = get_tipos_de_documentos_nao_mapeados_no_recebimento(processo_metadados['processo']['documentos'])
                    msg_retorno = 'Existem tipos de documentos do PEN não mapeados para o SUAP: {}'.format(', '.join(lista_nao_mapeados))
                    recusar_tramite_barramento(tramite_barramento, id_tramite, processo_metadados, msg_retorno)
                    continue

                try:
                    if pendente['status'] == 2 and 'hashDosComponentesPendentesDeRecebimento' in tramite:  # Novo tramite externo a receber
                        componentes_digitais_a_receber = tramite['hashDosComponentesPendentesDeRecebimento']
                        tramite_barramento.componentes_digitais_a_receber = componentes_digitais_a_receber
                        tramite_barramento.save()
                        # Se não possui componentes (documentos) a receber então recusa o trâmite
                        if not tramite_barramento.componentes_digitais_a_receber:
                            msg_retorno = 'Trâmite recusado pois ocorreu erro ao gerar o Recibo de Conclusão'
                            recusar_tramite_barramento(tramite_barramento, id_tramite, processo_metadados, msg_retorno)
                            continue

                        processar_recebimento_tramite_a_receber(tramite_barramento, processo_hashs)
                    elif pendente['status'] == 4:  # Falta somente enviar o recibo de conclusao
                        # teste
                        logger.info(
                            f'ENVIAR RECIBO - TRAMITE BARRAMENTO: id {tramite_barramento.id} NRE {tramite_barramento.processo_barramento.nre_barramento_pen} Componenetes Digitais {tramite_barramento.componentes_digitais_a_receber}'
                        )
                        # fim teste

                        if tramite_barramento:
                            # Se não possui componentes (documentos) a receber então recusa o trâmite
                            if not tramite_barramento.componentes_digitais_a_receber:
                                msg_retorno = 'Trâmite recusado pois ocorreu erro ao gerar o Recibo de Conclusão'
                                recusar_tramite_barramento(tramite_barramento, id_tramite, processo_metadados, msg_retorno)
                                continue

                            recibo_json = monta_recibo(
                                tramite_barramento.id_tramite_barramento,
                                tramite_barramento.processo_barramento.nre_barramento_pen,
                                tramite_barramento.componentes_digitais_a_receber,
                            )
                            try:
                                tramite_barramento.tramite_externo_recibo_conclusao_json = recibo_json
                                tramite_barramento.save()
                                recibo_conclusao_tramite = enviar_recibo_tramite(
                                    tramite_barramento.id_tramite_barramento, tramite_barramento.tramite_externo_recibo_conclusao_json
                                )
                                if recibo_conclusao_tramite['status_code'] == 200:
                                    atualizar_tramite_barramento_recebido(
                                        tramite_barramento,
                                        tramite_barramento.metadados_processo,
                                        tramite_barramento.tramite_externo_recibo_conclusao_json,
                                        tramite_barramento.documentos,
                                    )
                                    if (
                                        getattr(tramite_barramento, 'tramite_suap_barramento', None)
                                        and tramite_barramento.tramite_suap_barramento.processo.esta_em_tramite_externo()
                                    ):
                                        tramite_barramento.tramite_suap_barramento.processo.colocar_em_tramite()
                                        tramite_barramento.tramite_suap_barramento.processo.save()
                                else:
                                    msg_retorno = json.loads(recibo_conclusao_tramite['content'])['mensagem']
                                    recusar_tramite_barramento(tramite_barramento, id_tramite, processo_metadados, msg_retorno)
                                    # Finaliza o processo que foi recebido no SUAP mas que o recibo de conslusão não foi recebido pelo barramento
                                    tramite_barramento.processo_barramento.processo.observacao_finalizacao = (
                                        'Este processo '
                                        'foi recebido/criado no SUAP através do barramento do Processo Eletrônico Nacional. '
                                        'Entretanto, não houve êxito ao enviar o recibo de conclusão do trâmite para o barramento, '
                                        'portanto, o processo foi finalizado pelo sistema.'
                                    )
                                    tramite_barramento.processo_barramento.processo.data_finalizacao = datetime.now()
                                    tramite_barramento.processo_barramento.processo.finalizar_processo()
                                    tramite_barramento.processo_barramento.processo.save()
                            except Exception as e:
                                raise e
                except API_PEN_Exception:
                    raise API_PEN_Exception('Erro ao processar recebimento do processo {}'.format(pendente['IDT']))


def processar_pendencias_envio(pendentes):
    """
    Rotina que envia os processos que estiverem na fila de tramitação externa com status de pendente de envio.
    Se o tramite estiver com status de recusado (8) e o motivo da recusa for falha de comunicacao 99 é realizada a ciência da
    da recusa"""
    if pendentes:
        for pendente in pendentes:
            if pendente['status'] == 8:
                if TramiteBarramento.objects.filter(id_tramite_barramento=pendente['IDT']).exists():
                    tramite_barramento = TramiteBarramento.objects.get(id_tramite_barramento=pendente['IDT'])
                    tramite_barramento.registrar_ciencia_recusa()
            elif pendente['status'] == 5:
                recibo_tramite = get_recibo_tramite(pendente['IDT'])
                if recibo_tramite.get('status_code') == 200 and 'recibo' in recibo_tramite['data']:
                    if TramiteBarramento.objects.filter(id_tramite_barramento=pendente['IDT']).exists():
                        tramite_barramento = TramiteBarramento.objects.get(id_tramite_barramento=pendente['IDT'])
                        tramite_barramento.registrar_recebimento(recibo_tramite['data'])


@transaction.atomic()
def criar_documento_processo_barramento(processo_barramento, ordem, hash_componente, conteudo, nome_arquivo):
    """
    Cria uma nova instância de DocumentoProcessoBarramento
    :param processo_barramento:
    :param ordem:
    :param hash_componente:
    :param conteudo:
    :return: DocumentoProcessoBarramento object
    """
    documento_processo_barramento = DocumentoProcessoBarramento.objects.filter(
        processo_barramento=processo_barramento, ordem=ordem, hash_para_barramento=hash_componente
    ).first()
    if not documento_processo_barramento:
        documento_processo_barramento = DocumentoProcessoBarramento()
        documento_processo_barramento.processo_barramento = processo_barramento
        documento_processo_barramento.ordem = ordem
        documento_processo_barramento.conteudo_arquivo = bytes(conteudo)
        documento_processo_barramento.hash_para_barramento = hash_componente
        documento_processo_barramento.recebido = True
        documento_processo_barramento.save()
    return documento_processo_barramento


@transaction.atomic()
def criar_tramite_barramento(processo_barramento, idt_tramite, processo_metadados):
    """
    Cria uma nova instância de  tramite barramento para o tramite atual
    :param processo_barramento:
    :param idt_tramite:
    :param processo_metadados:
    :return: TramiteBarramento object
    """
    tramite_barramento = TramiteBarramento()
    tramite_barramento.metadados_processo = processo_metadados['processo']
    tramite_barramento.documentos = processo_metadados['processo']['documentos']
    # Remetente
    tramite_barramento.remetente_repositorio_id = processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.remetente_estrutura_id = processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.remetente_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas'], processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    )['nome']
    # Destinatario
    tramite_barramento.destinatario_repositorio_id = processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.destinatario_estrutura_id = processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.destinatario_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas'],
        processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura'],
    )['nome']
    tramite_barramento.id_tramite_barramento = idt_tramite
    tramite_barramento.processo_barramento = processo_barramento
    tramite_barramento.status = TramiteBarramento.STATUS_PENDENTE_RECEBIMENTO
    tramite_barramento.save()
    return tramite_barramento


def atualizar_tramite_barramento_recebido(tramite_barramento, processo_metadados, recibo_json, documentos):
    tramite_barramento.remetente_repositorio_id = processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.remetente_estrutura_id = processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.remetente_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas'], processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    )['nome']
    tramite_barramento.destinatario_repositorio_id = processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.destinatario_estrutura_id = processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.destinatario_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas'],
        processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura'],
    )['nome']
    tramite_barramento.tramite_externo_recibo_conclusao_json = recibo_json
    tramite_barramento.documentos = documentos
    tramite_barramento.status = TramiteBarramento.STATUS_RECEBIDO
    tramite_barramento.save()
    return tramite_barramento


@transaction.atomic()
def recusar_tramite_barramento(tramite_barramento, idt_tramite, processo_metadados, mensagem_retorno):
    """
    Método que realiza a chamada a API do barramento registrando a recusa do trâmite
    por algum erro no recebimento pelo SUAP
    :param tramite_barramento: objeto do modelo TramiteBarramento que será atualizado com as infos da recusa
    :param idt_tramite: idt do tramite atual no barramento
    :param processo_metadados: metadados do processo que estava sendo recebido
    :param mensagem_retorno: mensagem de retorno referente ao erro que motivou a recusa
    :return:
    """
    if not mensagem_retorno:
        mensagem_retorno = 'Erro no recebimento do processo pelo SUAP'

    justificativa_json = {'justificativa': mensagem_retorno, 'motivo': '99'}
    recusar_tramite(idt_tramite, justificativa_json)
    tramite_barramento.remetente_repositorio_id = processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.remetente_estrutura_id = processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.remetente_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['remetente']['identificacaoDoRepositorioDeEstruturas'], processo_metadados['remetente']['numeroDeIdentificacaoDaEstrutura']
    )['nome']
    tramite_barramento.destinatario_repositorio_id = processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas']
    tramite_barramento.destinatario_estrutura_id = processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura']
    tramite_barramento.destinatario_externo_estrutura_descricao = get_estrutura_por_id(
        processo_metadados['destinatario']['identificacaoDoRepositorioDeEstruturas'],
        processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura'],
    )['nome']
    tramite_barramento.status = TramiteBarramento.STATUS_RECUSADO
    tramite_barramento.retorno_situacao = mensagem_retorno
    tramite_barramento.save()
    return None


def _vinculo_pessoa_fisica(nome: str, cpf: str) -> Vinculo:
    """Vínculo da pessoa física do CPF; sem vínculo existente, cadastra uma pessoa externa."""
    from rh.models import PessoaExterna, PessoaFisica

    pessoa_fisica = PessoaFisica.objects.filter(cpf=cpf).first()
    vinculo = pessoa_fisica.get_vinculo() if pessoa_fisica else None
    return vinculo or PessoaExterna.objects.create(nome=nome, cpf=cpf).get_vinculo()


def _vinculo_pessoa_juridica(nome: str, cnpj: str) -> Vinculo:
    """Vínculo da pessoa jurídica do CNPJ (com máscara ou só dígitos); cadastra a pessoa se ela não existir."""
    from rh.models import PessoaJuridica

    cnpj_mascarado = mask_cnpj(cnpj)
    pessoa_juridica = PessoaJuridica.objects.filter(cnpj__in={cnpj, cnpj_mascarado}).first()
    if pessoa_juridica is None:
        pessoa_juridica = PessoaJuridica.objects.create(nome=nome, cnpj=cnpj_mascarado)
    # O vínculo nasce no save() da pessoa jurídica; regrava se ele não existir.
    return pessoa_juridica.get_vinculo() or pessoa_juridica.save().get_vinculo()


def _adicionar_interessados(processo_suap: Processo, interessados: list[dict]) -> None:
    """Vincula ao processo os interessados recebidos no trâmite SUAP - SUAP.

    Interessado com mais de 11 dígitos no documento é pessoa jurídica (CNPJ, com ou sem máscara); os demais, pessoa física.
    Documento inválido é registrado em log e o interessado é ignorado, sem recusar o trâmite.
    """
    for interessado in interessados:
        documento = interessado['documentosDeIdentificacao'][0]
        if 'codigo' not in documento:
            continue
        codigo = documento['codigo']
        try:
            if len(mask_numbers(codigo)) > 11:
                vinculo = _vinculo_pessoa_juridica(documento['nomeNoDocumento'], codigo)
            else:
                vinculo = _vinculo_pessoa_fisica(documento['nomeNoDocumento'], codigo)
        except ValidationError:
            logger.warning(f'Interessado {documento["nomeNoDocumento"]} do processo {processo_suap.pk} não incluído: documento inválido.')
            continue
        processo_suap.interessados.add(vinculo)


def _criar_processo_recebido(processo_metadados: dict, setor_recebimento: Setor) -> Processo:
    """Cria o processo SUAP a partir dos metadados do trâmite recebido: hipótese legal e, no trâmite SUAP - SUAP, os interessados."""
    processo_suap = Processo.objects.create(
        numero_protocolo_fisico=processo_metadados['processo']['protocolo'],
        tipo_processo_id=Configuracao.get_valor_por_chave(app='conectagov_pen', chave='tipo_processo_recebimento_pen'),
        nivel_acesso=processo_metadados['processo']['nivelDeSigilo'],
        assunto=processo_metadados['processo']['descricao'],
        data_hora_criacao=processo_metadados['processo']['dataHoraDeProducao'],
        setor_criacao=setor_recebimento,
    )

    # Salva hipótese legal para processos restritos ou privados
    if processo_suap.nivel_acesso == Processo.NIVEL_ACESSO_RESTRITO and processo_metadados.get('hipoteseLegal', {}):
        hipotese_legal_suap = (
            HipoteseLegalPEN.objects.filter(id_hipotese_legal_pen=processo_metadados.get('hipoteseLegal').get('identificacao'))
            .first()
            .hipotese_legal_suap
        )
        hipotese_padrao = HipoteseLegalPEN.get_hipotese_padrao()
        processo_suap.hipotese_legal = hipotese_legal_suap or hipotese_padrao
        processo_suap.save()

    # Se for um trâmite SUAP - SUAP vincula ou adiciona os interessados (PessoaExterna ou PessoaJuridica)
    if processo_metadados['processo']['produtor']['nome'] == 'suap':
        _adicionar_interessados(processo_suap, processo_metadados['processo']['interessados'])
    return processo_suap


def _criar_documento_recebido(documento: dict, processo_suap: Processo, setor_recebimento: Setor) -> None:
    """Cria o documento digitalizado recebido do barramento e o anexa ao processo."""
    if MapeamentoTiposDocumento.objects.filter(
        tipo_doc_barramento_pen__id_tipo_doc_pen=documento['id_tipo_doc_pen'], tipo_para_recebimento_suap=True
    ).exists():
        mapeamento_tipo = MapeamentoTiposDocumento.objects.get(
            tipo_doc_barramento_pen__id_tipo_doc_pen=documento['id_tipo_doc_pen'], tipo_para_recebimento_suap=True
        )
        id_tipo_documento = mapeamento_tipo.tipo_doc_suap.id
    elif MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen__id_tipo_doc_pen=documento['id_tipo_doc_pen']).exists():
        mapeamento_tipo = MapeamentoTiposDocumento.objects.filter(tipo_doc_barramento_pen__id_tipo_doc_pen=documento['id_tipo_doc_pen'])[0]
        id_tipo_documento = mapeamento_tipo.tipo_doc_suap.id

    doc = DocumentoDigitalizado.objects.create(
        assunto=documento['assunto'],
        data_ultima_modificacao=datetime.now(),
        setor_dono=setor_recebimento,
        tipo_conferencia_id=3,
        tipo_id=id_tipo_documento,
        nivel_acesso=get_nivel_acesso_documento(documento['nivel_acesso']),
    )

    if documento['hipoteseLegal']:
        hipotese_legal_suap = (
            HipoteseLegalPEN.objects.filter(id_hipotese_legal_pen=documento['hipoteseLegal'].get('identificacao')).first().hipotese_legal_suap
        )
        hipotese_padrao = HipoteseLegalPEN.get_hipotese_padrao().hipotese_legal_suap
        doc.hipotese_legal = hipotese_legal_suap or hipotese_padrao
        doc.save()

    if (documento['complemento_tipo_arquivo'] == 'application/pdf') or (documento['tipo_arquivo'] == 'application/pdf'):
        doc.arquivo.save(documento['nome_arquivo'], ContentFile(base64.b64decode(documento['conteudo'])))
    elif (documento['tipo_arquivo'] == 'text/html') or (documento['tipo_conteudo'] == 'txt'):
        conteudo_pdf = as_pdf(base64.b64decode(documento['conteudo']))
        doc.arquivo.save('documento_' + str(doc.id), ContentFile(conteudo_pdf))
    DocumentoDigitalizadoProcesso.objects.create(processo=processo_suap, documento=doc)


@_em_nome_do_usuario_de_recebimento()
@transaction.atomic()
def receber_processo(
    processo_metadados: dict, documentos_recebidos: list[dict], processo_barramento: ProcessoBarramento, tramite_barramento: TramiteBarramento
) -> Processo:
    """
    Executa rotina para recebimento de um processo enviado de outra instituicao atraves do barramento

    :param processo_metadados: Metadados do processo que está sendo recebido
    :param documentos_recebidos: Documentos do processo
    :param processo_barramento: Dados do Processo Externo recebido via barramento
    :param tramite_barramento: Dados do tramite externo recebido via barramento
    :return:
    """
    try:
        # Setor recebimento = Setor configurado na unidade, se não existe pega setor da configuração geral do SUAP
        from comum.models import Configuracao
        from rh.models import UnidadeOrganizacional

        uo = get_object_or_404(UnidadeOrganizacional, id_estrutura_pen=processo_metadados['destinatario']['numeroDeIdentificacaoDaEstrutura'])
        if uo.setor_recebimento_pen:
            setor_recebimento = uo.setor_recebimento_pen
        elif Configuracao.get_valor_por_chave(app='conectagov_pen', chave='setor_recebimento_pen'):
            id_setor_recebimento = int(Configuracao.get_valor_por_chave(app='conectagov_pen', chave='setor_recebimento_pen'))
            setor_recebimento = Setor.objects.suap_ativos().get(pk=id_setor_recebimento)

        # Verifica se o processo já existe e vincula o ProcessoBarramento, caso não exista cria um novo processo
        if Processo.objects.filter(numero_protocolo_fisico=processo_metadados['processo']['protocolo']):
            processo_suap = get_object_or_404(Processo, numero_protocolo_fisico=processo_metadados['processo']['protocolo'])
            processo_barramento.processo = processo_suap
            processo_barramento.save()
        else:
            processo_suap = _criar_processo_recebido(processo_metadados, setor_recebimento)
            processo_barramento.processo = processo_suap
            processo_barramento.save()

        # Ordena documentos para recebimento na ordem correta
        documentos_recebidos = sorted(documentos_recebidos, key=lambda i: i['ordem'])

        for documento in documentos_recebidos:
            _criar_documento_recebido(documento, processo_suap, setor_recebimento)

        tramite_novo = Tramite()
        tramite_novo.processo = processo_suap
        tramite_novo.destinatario_setor = setor_recebimento
        tramite_novo.tramite_barramento = tramite_barramento
        tramite_novo.save()
        return processo_suap
    except API_PEN_Exception:
        raise API_PEN_Exception('Erro ao receber processo no SUAP')


def _baixar_documentos_a_receber(tramite_barramento: TramiteBarramento, processo_hashs: list[str]) -> list[dict]:
    """Baixa do barramento os componentes digitais pendentes do trâmite, guardando os novos em DocumentoProcessoBarramento."""
    documentos_recebidos = []
    processo_metadados = tramite_barramento.metadados_processo
    for doc in processo_metadados['processo']['documentos']:
        for comp in doc['componentesDigitais']:
            hash_componente = comp['hash']['conteudo']
            if hash_componente in (tramite_barramento.componentes_digitais_a_receber or []):
                conteudo = receber_componente_digital(
                    tramite_barramento.id_tramite_barramento, processo_metadados['processo']['protocolo'], hash_componente
                )
                documentos_recebidos.append(
                    {
                        'idt': tramite_barramento.id_tramite_barramento,
                        'protocolo': processo_metadados['processo']['protocolo'],
                        'ordem': doc['ordem'],
                        'assunto': doc['descricao'],
                        'id_tipo_doc_pen': doc['especie']['codigo'],
                        'nome_tipo_doc_pen': doc['especie']['nomeNoProdutor'],
                        'conteudo': conteudo['content'].decode(),
                        'hash': hash_componente,
                        'nome_arquivo': comp['nome'],
                        'tipo_conteudo': comp['tipoDeConteudo'],  # txt = html,etc - #out
                        'tipo_arquivo': comp['mimeType'],
                        'complemento_tipo_arquivo': comp['dadosComplementaresDoTipoDeArquivo'],
                        'nivel_acesso': doc['nivelDeSigilo'],
                        'hipoteseLegal': doc['hipoteseLegal'],
                    }
                )
                if hash_componente not in processo_hashs:
                    if (
                        comp['mimeType'] == 'text/html'
                        or comp['mimeType'] == 'application/pdf'
                        or comp['dadosComplementaresDoTipoDeArquivo'] == 'application/pdf'
                    ):
                        criar_documento_processo_barramento(
                            tramite_barramento.processo_barramento, doc['ordem'], hash_componente, conteudo['content'], comp['nome']
                        )
                    else:
                        msg_retorno = 'Existem documentos com formatos não aceitos pelo SUAP. Os formatos aceitos são: html e pdf'
                        recusar_tramite_barramento(tramite_barramento, tramite_barramento.id_tramite_barramento, processo_metadados, msg_retorno)
                else:
                    # remove documento que já existem no SUAP
                    documentos_recebidos.pop(-1)
    return documentos_recebidos


def processar_recebimento_tramite_a_receber(tramite_barramento: TramiteBarramento, processo_hashs: list[str]) -> None:
    """
    Realiza os procedimentos necessários para receber um tramite no SUAP que é utilizado nos casos:
    1 - Novo tramite externo com status == 2
    2 - Tramite externo que foi iniciado
    :return:
    """
    # Sem usuário de recebimento, `receber_processo` falharia e o trâmite seria recusado no barramento. Pula antes de baixar os
    # componentes: os já gravados em DocumentoProcessoBarramento seriam descartados de `documentos_recebidos` na próxima execução.
    if _usuario_de_recebimento() is None:
        logger.warning(MSG_USUARIO_RECEBIMENTO_NAO_CONFIGURADO)  # error viraria um 2º evento no Sentry (LoggingIntegration)
        sentry_sdk.capture_message(MSG_USUARIO_RECEBIMENTO_NAO_CONFIGURADO, level='error')
        return None
    documentos_recebidos = _baixar_documentos_a_receber(tramite_barramento, processo_hashs)
    processo_metadados = tramite_barramento.metadados_processo

    """
    As validações do SUAP (tipo de documento, etc, devem ser feitas antes da chamada do receber processo.
    Pois o método receber processo é o que realmente criará o processo válido com os documentos no SUAP.
    """
    recibo_json = monta_recibo(
        tramite_barramento.id_tramite_barramento,
        tramite_barramento.processo_barramento.nre_barramento_pen,
        tramite_barramento.componentes_digitais_a_receber,
    )

    # Devido ao problema que pode ocorrer quando o tramite do barramento for recebido mas
    # aconteça  erro na criação do processo no SUAP, o recibo de conclusao somente sera enviado
    # se o processo for realmente recebido/criado no SUAP, caso contrario o tramite sera recusado

    try:
        tramite_barramento.tramite_externo_recibo_conclusao_json = recibo_json
        tramite_barramento.save()
        processo_suap = receber_processo(processo_metadados, documentos_recebidos, tramite_barramento.processo_barramento, tramite_barramento)
        recibo_conclusao_tramite = enviar_recibo_tramite(tramite_barramento.id_tramite_barramento, recibo_json)
        if recibo_conclusao_tramite['status_code'] == 200:
            atualizar_tramite_barramento_recebido(tramite_barramento, processo_metadados, recibo_json, documentos_recebidos)
            if processo_suap.esta_em_tramite_externo():
                processo_suap.colocar_em_tramite()
                processo_suap.save()
        elif recibo_conclusao_tramite['status_code'] == 500:
            atualizar_tramite_barramento_recebido(tramite_barramento, processo_metadados, recibo_json, documentos_recebidos)
            # Caso o barramento não aceite o recibo de conclusão
            retorno = json.loads(recibo_conclusao_tramite['content'])
            if 'codigoErro' in retorno and retorno['codigoErro'] == '0024':
                msg_retorno = retorno['mensagem'] + '. Falta enviar o recibo de conclusão.'

        else:
            msg_retorno = json.loads(recibo_conclusao_tramite['content'])['mensagem']
            recusar_tramite_barramento(tramite_barramento, tramite_barramento.id_tramite_barramento, processo_metadados, msg_retorno)
    except Exception as e:
        msg_retorno = 'Erro ao receber/criar processo no SUAP'
        recusar_tramite_barramento(tramite_barramento, tramite_barramento.id_tramite_barramento, processo_metadados, msg_retorno)
        raise e
