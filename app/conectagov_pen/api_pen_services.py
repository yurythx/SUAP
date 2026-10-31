from comum.models import Configuracao

from .connect_pen import request_delete, request_get, request_post, request_put, request_test_api


def _url(path=None):
    url_ws = Configuracao.get_valor_por_chave(app='conectagov_pen', chave='urlProducaoWS_pen') or ''
    return f'{url_ws}{path}' if path else url_ws


def barramento_disponivel():
    resposta = request_test_api(_url())
    return resposta.get('status_code', 0) == 200


def get_motivo_barramento_indisponivel():
    resposta = request_test_api(_url())
    return resposta.get('mensagem', 'Erro na conexão com o TramitaGov.')


def get_repositorios(ativos='true'):
    path = '/repositorios-de-estruturas'
    params = {'ativos': ativos}
    if barramento_disponivel():
        resposta = request_get(_url(path), params)
        if resposta:
            return resposta.get('data', {})
        else:
            return {}
    else:
        return None


def get_estrutura(repositorio_id, nome=None):
    path = f'/repositorios-de-estruturas/{repositorio_id:d}/estruturas-organizacionais'
    params = {'nome': nome}
    if barramento_disponivel():
        resposta = request_get(_url(path), params)
        if resposta:
            return resposta.get('data', {}).get('estruturas', None)
        else:
            return None


def get_estrutura_por_id(repositorio_id, estrutura_id):
    path = f'/repositorios-de-estruturas/{repositorio_id}/estruturas-organizacionais/{estrutura_id}'
    resposta = request_get(_url(path))
    if resposta:
        return resposta.get('data', {})
    else:
        return {}


def get_estrutura_por_pai(repositorio_id, estrutura_id, nome=None):
    path = f'/repositorios-de-estruturas/{repositorio_id:d}/estruturas-organizacionais/{estrutura_id:d}/filhas'
    params = {'nome': nome}
    resposta = request_get(_url(path), params)
    if resposta:
        return resposta.get('data', {})
    else:
        return {}


def get_hipoteses(status='true'):
    path = '/hipoteses'
    params = {'status': status}
    resposta = request_get(_url(path), params)
    if resposta:
        return resposta.get('data', {}).get('hipotesesLegais', '')
    else:
        return {}


def get_recibo_envio(id_tramite_pen):
    """Recebe da Solução uma assinatura digital, representando que a Solução entende que o SPE remetente concluiu todos os passos
    necessários para que o trâmite possa ser encaminhado para o destinatário, caso não possua recibo retorna codigo de erro"""
    path = f'/tramites/{id_tramite_pen:d}/recibo-de-envio'
    resposta = request_get(_url(path))
    return resposta


def get_recibo_tramite(id_tramite_pen):
    """Recebe recibo do tramite pelo id, caso não possua recibo retorna codigo de erro"""
    path = f'/tramites/{id_tramite_pen:d}/recibo'
    resposta = request_get(_url(path))
    return resposta


def get_ciencia_recusa(id_tramite_pen):
    """Informa para a solucao (Tramita Gov.BR) que esta ciente que o tramite foi recusado pelo SPE de destino"""
    path = f'/tramites/{id_tramite_pen:d}/ciencia'
    if get_tramite(id_tramite_pen)['situacaoAtual'] == 8:
        resposta = request_get(_url(path))
        if resposta:
            return resposta.get('status_code', -1)
        else:
            return -1
    else:
        raise Exception('Tramite não está com a situação de recusado.')


def get_tramites_pendentes():
    """Retorna uma uma lista com todos os trâmites pendentes que estão aguardando algum tipo de ação"""
    path = '/tramites/pendentes'
    resposta = request_get(_url(path))
    if resposta:
        return resposta.get('data', {})
    else:
        return {}

    # envio


def enviar_processo(json):
    """Iniciar um trâmite de processo administrativo. Os metadados do processo e de todos os componentes digitais são
    enviados neste passo. Na resposta, a Solução indica quais os componentes digitais que devem ser enviados para que o
    processo siga para o destinatário"""
    path = '/tramites/processo'
    resposta = request_post(_url(path), json)
    return resposta


def enviar_documento(json):
    """Iniciar um trâmite de documento avulso. Os metadados do documento e seus componentes digitais são informados"""
    path = '/tramites/documento'
    resposta = request_post(_url(path), json)
    return resposta


def enviar_componente_digital(id_tramite_pen, numero_protocolo, json_data):
    """Efetuar o envio do componente digital (repr binaria) para a Solução"""
    path = f'/tickets-de-envio-de-componente/{id_tramite_pen:d}/protocolos/componentes-a-enviar'
    json_data['protocolo'] = numero_protocolo
    resposta = request_put(_url(path), json_data)
    return resposta


def cancelar_tramite(id_tramite_pen):
    "Cancela o trâmite. Apenas o SPE remetente pode executar se ainda não tiver resgatado o recibo de envio"
    path = f'/tramites/{id_tramite_pen:d}'
    resposta = request_delete(_url(path))
    return resposta


# recebimento
def get_metadados(id_tramite_pen):
    """Recebe os dados do processo que está sendo tramitado, depois dessa
    chamada pode iniciar o recebimento dos componentes digitais"""
    path = f'/tramites/{id_tramite_pen:d}'
    resposta = request_get(_url(path))
    if resposta:
        return resposta.get('data', {})
    else:
        return {}


def get_tramite(id_tramite_pen):
    "Recebe dados do tramite  e informa lista com componentes a receber ou enviar"
    path = f'/tramites/?IDT={id_tramite_pen:d}'
    resposta = request_get(_url(path))
    if resposta:
        return resposta.get('data', {}).get('tramites', [{}])[0]
    else:
        return {}


def receber_componente_digital(id_tramite_pen, numero_protocolo, hash_componente):
    """Receber o conteúdo binário de cada componente digital tramitado. Após o recebimento do último, fica permitido
    ao destinatário o envio do recebimento de trâmite, processo necessário para efetivação e conclusão do fluxo."""
    path = f'/tramites/{id_tramite_pen:d}/protocolos/componentes-digitais'
    print(path)
    json_data = {'hashDoComponenteDigital': hash_componente, 'protocolo': numero_protocolo}
    print(json_data)
    resposta = request_post(_url(path), json_data)
    return resposta


def enviar_recibo_tramite(id_tramite_pen, json):
    """Registrar o recebimento do conteúdo tramitado. Esse recibo é validado pela Solução (Tramita Gov.BR)
    e disponibilizado para o SPE que solicitou o trâmite (remetente)."""
    path = f'/tramites/{id_tramite_pen:d}/recibo'
    resposta = request_post(_url(path), json)
    return resposta


def recusar_tramite(id_tramite_pen, json):
    """Recusa o trâmite. Só pode recusar antes  de enviar o recibo de trâmite assinado."""
    path = f'/tramites/{id_tramite_pen:d}/recusa'
    resposta = request_post(_url(path), json)
    return resposta
