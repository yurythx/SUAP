import json
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404

from comum.utils import get_uo
from conectagov_pen.models import DocumentoProcessoBarramento, HipoteseLegalPEN, TramiteBarramento
from conectagov_pen.utils import processo_possui_tipos_de_documentos_nao_mapeados_no_envio, strdecode
from djtools.utils import JsonResponse
from djtools.views import httprr, rtr
from processo_eletronico.models import DocumentoDigitalizado, DocumentoTexto, Processo, Tramite

from .api_pen_services import (
    barramento_disponivel,
    cancelar_tramite,
    enviar_componente_digital,
    enviar_processo,
    get_estrutura_por_id,
    get_hipoteses,
    get_recibo_envio,
    get_tramite,
)
from .connect_pen import API_PEN_Exception
from .forms import HipoteseLegalPadraoPENForm
from .processa_pendencias import processo_pen


@rtr()
@login_required()
@transaction.atomic()
def envia_processo(request, processo_id, id_repositorio, id_estrutura):
    """
     Rotina que envia um processo pelo Tramita Gov.BR, em caso de falha o processo irá para a lista de pendentes de envio
    :param request:
    :param processo_id:
    :param id_repositorio:
    :param id_estrutura:
    :return:
    """
    if barramento_disponivel():
        msg = None
        tipo_msg = 'warning'
        processo = get_object_or_404(Processo, pk=processo_id)
        serializador_processo = processo_pen(processo)
        if not get_uo(request.user).id_estrutura_pen:
            msg = f'Unidade {get_uo(request.user).sigla} não está configurada para enviar processos pelo Tramita Gov.BR.'
        elif not processo.esta_ativo():
            msg = f"Processo {processo.numero_protocolo_fisico} não está na situação 'Em trâmite'."
        elif processo.eh_privado():
            msg = f'Processo {processo.numero_protocolo_fisico} é privado e não pode ser encaminhado via Tramita Gov.BR.'
        elif processo.tem_documento_sigiloso():
            msg = f'Processo {processo.numero_protocolo_fisico} possui documento(s) sigiloso(s) e não pode ser encaminhado via Tramita Gov.BR.'
        elif not processo.interessados.all().exists():
            msg = f'Processo {processo.numero_protocolo_fisico} não possui interessados cadastrados.'
        elif not processo.get_todos_documentos_processo():
            msg = f'Processo {processo.numero_protocolo_fisico} não possui documentos.'
        elif processo_possui_tipos_de_documentos_nao_mapeados_no_envio(processo.get_todos_documentos_processo()):
            msg = f'Processo {processo.numero_protocolo_fisico} possui tipos de documentos não mapeados para o Tramita Gov.BR.'
        elif not serializador_processo:
            msg = f'Processo {processo.numero_protocolo_fisico} não possui novos documentos para enviar pelo Tramita Gov.BR.'
        else:
            processo_ = serializador_processo[0]  # metadados_para_barramento
            documentos_com_conteudo = serializador_processo[1]
            processo_barramento = serializador_processo[2]
            tramite_barramento = serializador_processo[3]
            processo_['cabecalho']['destinatario']['identificacaoDoRepositorioDeEstruturas'] = id_repositorio
            processo_['cabecalho']['destinatario']['numeroDeIdentificacaoDaEstrutura'] = id_estrutura
            envia_metadados = enviar_processo(processo_)

        if not msg:
            if envia_metadados['status_code'] == 200:
                metadados = json.loads(envia_metadados['content'])
                idt = metadados['IDT']
                nre = metadados['NRE']
                tramite = get_tramite(idt)
                tramite_barramento.metadados_processo = metadados
                tramite_barramento.id_tramite_barramento = idt
                tramite_barramento.save()
                hashDosComponentesPendentesDeEnvio = tramite['hashDosComponentesPendentesDeEnvio']
                msg_docs = ''
                for doc in documentos_com_conteudo:
                    conteudo_arquivo = doc['conteudo']
                    hash_documento = doc['documento']['hash_documento']
                    objeto_documento = None
                    if 'id_documento' in doc['documento']:
                        if doc['documento']['tipo_parte_processo'] == 'DOCUMENTO_TEXTO':
                            objeto_documento = DocumentoTexto.objects.get(id=doc['documento']['id_documento'])
                        elif doc['documento']['tipo_parte_processo'] == 'DOCUMENTO_DIGITALIZADO':
                            objeto_documento = DocumentoDigitalizado.objects.get(id=doc['documento']['id_documento'])

                    if strdecode(hash_documento) in hashDosComponentesPendentesDeEnvio:
                        componente = {'conteudo': conteudo_arquivo, 'hashDoComponenteDigital': hash_documento}
                        envia_comp = enviar_componente_digital(metadados['ticketParaEnvioDeComponentesDigitais'], tramite['protocolo'], componente)
                        t = 0
                        while envia_comp['status_code'] != 200:
                            t += 1
                            time.sleep(5)

                            """
                            Após 3 tentativas sem sucesso de enviar o componente digital o TramiteBarramento é cancelado
                            """
                            if t == 3:
                                cancelar_tramite(int(tramite['IDT']))
                                tramite_barramento.status = tramite_barramento.STATUS_CANCELADO
                                retorno = json.loads(envia_comp['content'])
                                tramite_barramento.retorno_situacao = retorno['mensagem']
                                tramite_barramento.save()
                                return httprr(processo.get_absolute_url(), retorno['mensagem'])

                        if envia_comp['status_code'] == 200:
                            DocumentoProcessoBarramento.objects.filter(
                                processo_barramento=processo_barramento.id, ordem=doc['documento']['ordem'], enviado=False, recebido=False
                            ).update(enviado=True)
                            if objeto_documento:
                                msg_docs += objeto_documento.assunto
                            else:
                                msg_docs += 'Capa/Despacho/Parecer'
                    else:
                        msg = f'Conflito na checagem de hash do documento {objeto_documento.assunto} - id: {objeto_documento.id}'
                recibo_envio = get_recibo_envio(idt)
                t = 0
                while recibo_envio['status_code'] != 200:
                    t += 1
                    time.sleep(5)
                    if t == 3:
                        cancelar_tramite(int(tramite['IDT']))
                        tramite_barramento.status = tramite_barramento.STATUS_CANCELADO
                        retorno = json.loads(recibo_envio['content'])
                        tramite_barramento.retorno_situacao = retorno['mensagem']
                        tramite_barramento.save()
                        return httprr(processo.get_absolute_url(), recibo_envio['content']['mensagem'])
                if recibo_envio['status_code'] == 200:
                    dados_tramite_barramento = {
                        'processo_barramento': processo_barramento,
                        'idt': idt,
                        'recibo_envio': recibo_envio,
                        'remetente_repositorio_id': processo_['cabecalho']['remetente']['identificacaoDoRepositorioDeEstruturas'],
                        'remetente_estrutura_id': processo_['cabecalho']['remetente']['numeroDeIdentificacaoDaEstrutura'],
                        'destinatario_repositorio_id': processo_['cabecalho']['destinatario']['identificacaoDoRepositorioDeEstruturas'],
                        'destinatario_estrutura_id': processo_['cabecalho']['destinatario']['numeroDeIdentificacaoDaEstrutura'],
                    }
                    dados_tramite = {
                        'processo': processo_barramento.processo,
                        'tramite_barramento': atualiza_tramite_barramento(tramite_barramento, dados_tramite_barramento),
                        'remetente_setor': processo_barramento.processo.get_setor_atual(),
                        'remetente_vinculo': request.user.get_vinculo(),
                    }
                    tramite = criar_tramite_envio(dados_tramite)
                    if tramite:
                        if not processo_barramento.nre_barramento_pen:
                            processo_barramento.nre_barramento_pen = nre
                            processo_barramento.save()
                        processo.colocar_em_tramite_externo()
                        processo.save()
                        msg = (
                            f'Processo tramitado externamente com sucesso por {tramite.remetente_vinculo.pessoa.nome}. Documentos enviados:'
                            + msg_docs
                        )
                        tipo_msg = 'success'
            else:
                msg = f'O SUAP não está conseguindo enviar este processo, por gentileza, tente novamente mais tarde {envia_metadados}.'
                tipo_msg = 'error'
        else:
            tipo_msg = 'error'
            return httprr(processo.get_absolute_url(), msg, tag=tipo_msg)
    else:
        msg = 'Tramita Gov.BR indisponível no momento, por gentileza, tente novamente mais tarde.'
        raise API_PEN_Exception(msg)
    return httprr(processo.get_absolute_url(), msg, tag=tipo_msg)


def atualiza_tramite_barramento(tramite_barramento, dados_tramite_barramento):
    tramite_barramento.processo_barramento = dados_tramite_barramento['processo_barramento']
    # dados_tramite_externo
    tramite_barramento.id_tramite_barramento = dados_tramite_barramento['idt']
    tramite_barramento.remetente_externo_repositorio_id = dados_tramite_barramento['remetente_repositorio_id']
    tramite_barramento.remetente_externo_estrutura_id = dados_tramite_barramento['remetente_estrutura_id']
    tramite_barramento.remetente_externo_estrutura_descricao = get_estrutura_por_id(
        dados_tramite_barramento['remetente_repositorio_id'], dados_tramite_barramento['remetente_estrutura_id']
    )['nome']
    tramite_barramento.destinatario_externo_repositorio_id = dados_tramite_barramento['destinatario_repositorio_id']
    tramite_barramento.destinatario_externo_estrutura_id = dados_tramite_barramento['destinatario_estrutura_id']
    tramite_barramento.destinatario_externo_estrutura_descricao = get_estrutura_por_id(
        dados_tramite_barramento['destinatario_repositorio_id'], dados_tramite_barramento['destinatario_estrutura_id']
    )['nome']
    # recibos_json
    tramite_barramento.tramite_externo_recibo_envio_json = dados_tramite_barramento['recibo_envio']['data']
    tramite_barramento.status = TramiteBarramento.STATUS_ENVIADO
    tramite_barramento.save()
    return tramite_barramento


def criar_tramite_envio(dados_tramite):
    tramite_novo = Tramite()
    tramite_novo.processo = dados_tramite['processo']
    tramite_novo.tramite_barramento = dados_tramite['tramite_barramento']
    tramite_novo.remetente_setor = dados_tramite['remetente_setor']
    tramite_novo.remetente_vinculo = dados_tramite['remetente_vinculo']
    tramite_novo.save()
    return tramite_novo


@login_required
def consulta_estrutura(request, repositorio_id):
    from conectagov_pen.api_pen_services import get_estrutura
    from conectagov_pen.utils import monta_retorno_autocomplete

    nome_busca = request.GET.get('q')
    retorno = monta_retorno_autocomplete(get_estrutura(int(repositorio_id), nome_busca))
    return JsonResponse(retorno)


@login_required
def processar_pendencias(request):
    from conectagov_pen.processa_pendencias import processar_pendencias

    if processar_pendencias():
        return httprr('/admin/conectagov_pen/tramitebarramento/', 'Trâmites Externos Atualizados Com Sucesso')
    else:
        return httprr('/admin/conectagov_pen/tramitebarramento/', 'Não Existem Trâmites Externos Pendentes', 'alert')


@login_required
def importar_hipoteses_legais_pen(request):
    try:
        hipoteses_pen = get_hipoteses()
        for hipotese_pen in hipoteses_pen:
            if not HipoteseLegalPEN.objects.filter(id_hipotese_legal_pen__exact=hipotese_pen.get('identificacao')).exists():
                HipoteseLegalPEN.objects.update_or_create(
                    id_hipotese_legal_pen=hipotese_pen.get('identificacao'),
                    nome=hipotese_pen.get('nome'),
                    descricao=hipotese_pen.get('descricao'),
                    base_legal=hipotese_pen.get('baseLegal'),
                    status=hipotese_pen.get('status'),
                )
        return httprr('/admin/conectagov_pen/hipoteselegalpen/', 'Hipóteses Legais do PEN importadas com sucesso.', 'success')
    except Exception as e:
        msg = 'Erro ao importar Hipóteses Legais do PEN.'
        if settings.DEBUG:
            msg = f'{msg} - Detalhes: {e!s}'
        return httprr('/admin/conectagov_pen/hipoteselegalpen/', msg, 'error')


@rtr()
def definir_hipotese_padrao_pen(request):
    title = 'Hipótese Legal Padrão para Trâmites via Tramita Gov.BR'
    hipoteses_padrao_exists = HipoteseLegalPEN.objects.filter(hipotese_padrao=True).exists()
    form = HipoteseLegalPadraoPENForm(request.POST or None)
    if form.is_valid():
        hipotese = form.cleaned_data['hipotese']
        try:
            if hipoteses_padrao_exists:
                HipoteseLegalPEN.objects.filter(hipotese_padrao=True).update(hipotese_padrao=False)
            HipoteseLegalPEN.objects.filter(pk=hipotese.id).update(hipotese_padrao=True)
            messages.add_message(request, messages.SUCCESS, f'Hipótese Padrão do PEN alterada para: {hipotese.nome}')
        except Exception:
            messages.add_message(request, messages.ERROR, 'Erro ao alterar Hipótese Padrão do PEN')
    hipotese_padrao = HipoteseLegalPEN.objects.filter(hipotese_padrao=True).first().nome if hipoteses_padrao_exists else 'Nenhuma'

    return locals()
