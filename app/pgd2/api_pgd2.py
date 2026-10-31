import copy
import datetime
import json
import time
import traceback

import tqdm
from django.conf import settings
from django.db.models import F, Q

from comum.models import APIExterna, Configuracao
from comum.utils import get_sigla_reitoria
from djtools.utils import requests
from pgd2.models import (
    LogApi,
    LogApiDetalhe,
    ParticipantePgd,
    PitSetores,
    PitSolicitacaoAnalise,
    PitSolicitacaoAnaliseSetor,
    PlanoEntregasSetorial,
    PlanoIndividualTrabalho,
    RegistroAcaoPES,
    RegistroAcaoPlanoIndividualTrabalho,
    SetorPgdApi,
    SolicitacaoAdesaoServidor,
)
from pgd2.utils import (
    get_datetime_now,
    get_metodo_obter_codigo_siape_setor,
    get_setor_siape_lotacao_servidor_no_periodo,
    get_setores_pgd,
    get_timeout_pgd2,
)
from rh.models import Setor, UnidadeOrganizacional

TOKEN_API_PGD_2 = None


# ===================================
# Funções auxiliares - Gerais
# ===================================


def get_versao_suap():
    try:
        primeira_linha = None
        with open(f'{settings.BASE_DIR}/CHANGELOG.md') as f:
            primeira_linha = f.readline().strip()
            return primeira_linha.split(' ')[1]
    except Exception:
        return 0


def get_config_api():
    config_api = None
    try:
        # Em "admin/comum/apiexterna/"
        # - Nome: PGD
        # - URL Base da API: "https://api-pgd.dth.api.gov.br" ou "https://api.pgd.gestao.gov.br"
        # - Tipo autenticacao: Usuário/Senha
        # - Client ID: usuário
        # - Secret: senha
        if settings.DEBUG and hasattr(settings, 'CREDENCIAIS_API_PGD2'):
            credencias = settings.CREDENCIAIS_API_PGD2
            APIExternaFake = type(
                'APIExternaFake',
                (object,),
                {
                    'url_base': credencias.get('url_base'),
                    'client_id': credencias.get('client_id'),
                    'secret': credencias.get('secret'),
                },
            )
            config_api = APIExternaFake()
        else:
            config_api = APIExterna.PGD
            if not config_api.ativo:
                raise Exception('API PGD2 não está ativa')
    except Exception:
        log_api = LogApi()
        log_api.data_hora_inicio = get_datetime_now()
        log_api.data_proximo_envio_por_sucesso = amanha()  # Força envio todos os dias -- proximo_domingo()
        log_api.data_proximo_envio_por_erro = amanha()
        log_api.save()
        erro = 'Não foram encontradas as configurações da API do PGD em "API Externa"'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
    return config_api


def get_url_api():
    try:
        return get_config_api().url_base
    except Exception:
        pass
    return None


def get_timeout():
    return get_timeout_pgd2()


def get_token_envio_manual():
    api_externa = get_config_api()
    if api_externa:
        URL_API = api_externa.url_base
        dados = {
            'username': api_externa.client_id,
            'password': api_externa.secret,
        }

        header = {'User-agent': f'User-Agent: SUAP/{get_versao_suap()} (https://portal.suap.ifrn.edu.br/)'}
        url_token = f'{URL_API}/token'
        response_login = requests.post(url=url_token, data=dados, headers=header, timeout=get_timeout())
        return response_login.json().get('access_token')
    return None


def get_token(obter_novo=True):
    global TOKEN_API_PGD_2
    erro_token = None
    status_code = None

    try:
        if not obter_novo and not TOKEN_API_PGD_2:
            obter_novo = True

        if obter_novo:
            api_externa = get_config_api()

            if api_externa:
                URL_API = api_externa.url_base
                dados = {
                    'username': api_externa.client_id,
                    'password': api_externa.secret,
                }

                header = {'User-agent': f'User-Agent: SUAP/{get_versao_suap()} (https://portal.suap.ifrn.edu.br/)'}
                url_token = f'{URL_API}/token'
                response_login = requests.post(url=url_token, data=dados, headers=header, timeout=get_timeout())

                if response_login.ok:
                    TOKEN_API_PGD_2 = response_login.json().get('access_token')
                else:
                    erro_token = f'Erro ao obter token {response_login.status_code} - {response_login.text}'
                    status_code = response_login.status_code
            else:
                TOKEN_API_PGD_2 = None
                erro_token = 'Não existe configuração de credencial da API'
        else:
            return TOKEN_API_PGD_2

    except Exception as e:
        detalhe = traceback.format_exc().replace('\n', '\n\t')
        erro_token = f'Erro ao tentar obter token \n Erro:\n {e} \n Detalhe:\n {detalhe} \n {erro_token}'
        TOKEN_API_PGD_2 = None

    if not TOKEN_API_PGD_2:
        log_api = LogApi()
        log_api.data_hora_inicio = get_datetime_now()
        log_api.data_proximo_envio_por_sucesso = amanha()  # Força envio todos os dias -- proximo_domingo()
        log_api.data_proximo_envio_por_erro = amanha()
        log_api.url = URL_API
        log_api.save()
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=status_code, erro_impeditivo=erro_token, erro_nao_impeditivo=None)

    return TOKEN_API_PGD_2


def get_header(token):
    return {
        'User-agent': f'User-Agent: SUAP/{get_versao_suap()} (https://portal.suap.ifrn.edu.br/)',
        'accept': 'application/json',
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def enviar_dados(action, dados_enviar, eh_envio_manual=False):
    response_code_text = {'url': None, 'status_code': None, 'text': None}

    def enviar():
        origem_unidade = dados_enviar.get('origem_unidade')
        cod_unidade_autorizadora = dados_enviar.get('cod_unidade_autorizadora')
        id_plano_entregas = dados_enviar.get('id_plano_entregas')
        cod_unidade_lotacao = dados_enviar.get('cod_unidade_lotacao')
        matricula_siape = dados_enviar.get('matricula_siape')
        id_plano_trabalho = dados_enviar.get('id_plano_trabalho')

        if action == 'enviar_dados_pes_api':
            url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_entregas/{id_plano_entregas}'
        if action == 'enviar_dados_participantes_para_api':
            url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}'
        if action == 'enviar_dados_pits':
            url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'

        token = get_token_envio_manual() if eh_envio_manual else get_token(obter_novo=False)
        header = get_header(token)
        response = requests.put(url=url, data=json.dumps(dados_enviar), headers=header, timeout=get_timeout())

        if response.status_code == 401:
            token = get_token_envio_manual() if eh_envio_manual else get_token(obter_novo=True)
            header = get_header(token)
            response = requests.put(url=url, data=json.dumps(dados_enviar), headers=header, timeout=get_timeout())

        if response.ok:
            return True, url, None, None
        else:
            return False, url, response.status_code, response.text

    try:
        retorno = enviar()
        response_code_text = {'url': retorno[1], 'status_code': retorno[2], 'text': retorno[3]}
        return retorno[0], response_code_text

    except requests.exceptions.Timeout:
        try:
            time.sleep(2)

            retorno = enviar()
            response_code_text = {'url': retorno[1], 'status_code': retorno[2], 'text': retorno[3]}
            return retorno[0], response_code_text

        except Exception as e:
            response_code_text['text'] = f'Exceção\n{e}'

    except Exception as e:
        response_code_text['text'] = f'Exceção\n{e}'

    return False, response_code_text


def proximo_domingo():
    hoje = datetime.date.today()  # Obtém a data de hoje
    dias_para_domingo = (6 - hoje.weekday()) % 7  # Calcula os dias até domingo
    if dias_para_domingo == 0:  # Se hoje já for domingo, pega o próximo
        dias_para_domingo = 7
    return hoje + datetime.timedelta(days=dias_para_domingo)


def amanha():
    # Obtém a data de hoje
    hoje = datetime.date.today()

    # Calcula a data de amanhã
    return hoje + datetime.timedelta(days=1)


# ===================================
# Funções auxiliares - Identificadores do PES
# ===================================


def get_setor_siape_do_setor_suap(_sigla_setor, _uo_sigla_setor):
    """
    _sigla_setor: sigla do setor que vai ser buscado
    _uo_sigla_setor: sigla da UO do setor que vai ser buscado

    - Considerando os diferentes padrões de nomenclatura de setor
      - Precisamos elaborar várias estratégias de busca partindo de um padrão definido em configuração
    """

    if not (_sigla_setor and _uo_sigla_setor):
        return None

    # Veja em comum/comnfiguracao/pdd2
    padrao_sigla = int(Configuracao.get_valor_por_chave('pgd2', 'api_padrao_sigla_setor') or 1)

    # Pega o separador da _sigla_setor
    separador = '/'
    if '-' in _sigla_setor:
        separador = '-'

    # Pega o setor e a uo na _sigla_setor de acordo com o padrao_sigla
    setor_sigla_setor = None
    uo_sigla_setor = None
    if padrao_sigla == 1:
        split_sigla_setor = _sigla_setor.split(separador)
        setor_sigla_setor = split_sigla_setor[0]
        if len(split_sigla_setor) > 1:
            uo_sigla_setor = split_sigla_setor[1]
    else:
        # 2
        split_sigla_setor = _sigla_setor.split(separador)
        uo_sigla_setor = split_sigla_setor[0]
        if len(split_sigla_setor) > 1:
            setor_sigla_setor = split_sigla_setor[1]
        else:
            setor_sigla_setor = split_sigla_setor[0]
            uo_sigla_setor = None

    if not setor_sigla_setor:
        return None

    # Estratégia 1: busca direta pela Sigla do Setor
    setor_siape = Setor.objects.siape().filter(sigla=setor_sigla_setor, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Estratégia 2: busca direta pela Sigla do Setor / sigla da UO do Setor
    sigla_busca = None
    if padrao_sigla == 1:
        sigla_busca = f'{setor_sigla_setor}{separador}{_uo_sigla_setor}'
    else:
        sigla_busca = f'{_uo_sigla_setor}{separador}{setor_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Estratégia 3
    try:
        # Buscando a sigla do campus do setor equivalente da UO relacionada ao _sigla_setor
        # - Exemplo de problema que resolve: COAES/SPO (siape) e COAES/SPP (suap)
        # Troca a sigla da UO do setor para resolver o problema do exemplo
        sigla_uo = (
            UnidadeOrganizacional.objects.filter(sigla=_uo_sigla_setor, equivalente=Setor.objects.suap().get(sigla=_sigla_setor).uo)
            .first()
            .setor.sigla
        )
        sigla_uo = sigla_uo.split(separador)[1]

        sigla_busca = None
        if padrao_sigla == 1:
            sigla_busca = f'{setor_sigla_setor}{separador}{sigla_uo}'
        else:
            sigla_busca = f'{sigla_uo}{separador}{setor_sigla_setor}'
        setor_siape = Setor.objects.siape().filter(sigla=sigla_busca)
        if setor_siape:
            return setor_siape.first().codigo
    except Exception:
        pass

    # Outras estratégias
    # - Serão exeuctadas independentemente do padrao_sigla e do separador
    # ----------------------
    # Busca pelo padrão "SETORUO"
    sigla_busca = f'{setor_sigla_setor}{uo_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Busca pelo padrão "SETOR-UO"
    sigla_busca = f'{setor_sigla_setor}-{uo_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Busca pelo padrão "UO - SETOR"
    sigla_busca = f'{uo_sigla_setor} - {setor_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Busca pelo padrão "SETOR.UO"
    sigla_busca = f'{setor_sigla_setor}.{uo_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Busca pelo padrão "SETOR/CUO: onde o C é um prefixo da UO"
    sigla_busca = f'{setor_sigla_setor}/C{uo_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    # Busca pelo padrão "SETOR"
    sigla_busca = f'{setor_sigla_setor}'
    setor_siape = Setor.objects.siape().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
    if setor_siape:
        return setor_siape.first().codigo

    return None


def get_codigo_siape_setor_metodo1(setor):
    """
    Método PADRÃO
    Pega o código SIAPE de um setor SUAP usando o rh.models.Setor
    - TENTA inferir de acordo com a aestrura de setores SUJAP e SIAPE
    - Podem ocorrer erros devido diferençã no padrão das siglas de setor entre setores SIAPE e SUAP
    - Recomendamos que cada instituição revise a sua árvore SIAPE e SUAP para saber se as regras
      de get_setor_siape_do_setor_suap atendem aos seus padrões de sigla
    """
    if not setor:
        return None

    # setor_original get_setores_pgd().filter(sigla=sigla_setor).first()
    # setor = setor get_setores_pgd().filter(sigla=sigla_setor).first()
    setor_original = copy.deepcopy(setor)

    # Busca no próprio setor
    codigo_siape = get_setor_siape_do_setor_suap(setor.sigla, setor.uo.sigla)
    if codigo_siape:
        return codigo_siape

    # Se não tiver busca nos superiores
    setor = setor.superior
    while setor is not None:
        codigo_siape = get_setor_siape_do_setor_suap(setor.sigla, setor.uo.sigla)
        if codigo_siape:
            break
        setor = setor.superior

    if setor.uo.sigla == get_sigla_reitoria():
        try:
            # Vai usar o setor equivalente do campus siape relacionado ao campus suap do setor suap original
            uo_siape = UnidadeOrganizacional.objects.siape().filter(sigla=setor_original.uo.sigla).first()
            setor_equivalente = uo_siape.setor
            setor_siape = Setor.objects.siape().filter(sigla=setor_equivalente.sigla)
            if setor_siape:
                codigo_siape = setor_siape.first().codigo
        except Exception:
            pass

    return codigo_siape


def get_codigo_siape_setor_metodo2(setor):
    """
    Obter código SIAPE direto do setor SIAPE (caso utilize árvore SIAPE)
    """
    return setor.codigo


def get_codigo_siape_setor_metodo3(setor):
    """
    Utilizado inicialmente APENAS PELO IFRN

    Pega o código SIAPE de um setor SUAP usando o pgd2.models.SetorPgdApi
    - Esse model tem a relação de cada setor SIAPE com seu SUAP correspondente
    - Esse trabalho foi feito de forma automática e foi conferido manualmente
      - Automático: mesma rotina get_setor_siape_do_setor_suap
      - Manual: os dados gerados automaticamente foram conferido manualmente
    - Os setores foram carregados manualmente pelo comando "carregar_setores_siape_inicial"
    """

    def get_codigo_siape(setor):
        setor_api = SetorPgdApi.objects.filter(setor_suap=setor).first()
        if setor_api:
            return setor_api.setor_siape.codigo
        return None

    if not setor:
        return None

    # Busca no próprio setor
    codigo_siape = get_codigo_siape(setor)
    if codigo_siape:
        return codigo_siape

    # Se não tiver busca nos superiores
    setor = setor.superior
    while setor is not None:
        codigo_siape = get_codigo_siape(setor)
        if codigo_siape:
            break
        setor = setor.superior

    return codigo_siape


def get_codigo_siape_setor(setor):
    metodo = get_metodo_obter_codigo_siape_setor()
    if metodo == 1:
        return get_codigo_siape_setor_metodo1(setor)
    if metodo == 2:
        return get_codigo_siape_setor_metodo2(setor)
    return get_codigo_siape_setor_metodo3(setor)


# ===================================
# Funções auxiliares - Dados
# ===================================


def get_cod_unidade_lotacao_parcipante(pit):
    cod_unidade_lotacao = get_setor_siape_lotacao_servidor_no_periodo(pit.adesao.servidor, pit.data_inicio, pit.data_fim)
    if cod_unidade_lotacao:
        cod_unidade_lotacao = int(cod_unidade_lotacao.codigo)
    else:
        cod_unidade_lotacao = int(pit.get_cod_unidade_executora_para_api())
    return cod_unidade_lotacao


def get_dados_api_grupo_pes(pes):
    # teste
    # pes = PlanoEntregasSetorial.objects.filter(identificador_externo=identificador_externo)
    # pes = pes.first()
    identificador_externo = pes.identificador_externo

    cod_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')

    # Dados do PES
    # ------------------
    dados = {}
    dados['origem_unidade'] = 'SIAPE'
    dados['cod_unidade_autorizadora'] = int(cod_instituicao)
    dados['cod_unidade_instituidora'] = int(cod_instituicao)
    dados['cod_unidade_executora'] = int(pes.cod_siape_grupo)

    dados['id_plano_entregas'] = pes.identificador_externo
    dados['status'] = pes.get_situacao_para_api()
    dados['data_inicio'] = str(pes.periodo_pes.data_inicio)
    dados['data_termino'] = str(pes.periodo_pes.data_fim)

    dados['avaliacao'] = pes.get_avaliacao_para_api()

    dados['data_avaliacao'] = pes.get_data_avaliacao_para_api()

    # Dados das entregas do PES do grupo
    # ------------------
    lista_se = []
    grupo_pess = PlanoEntregasSetorial.objects.filter(identificador_externo=identificador_externo)
    if grupo_pess:
        for _pes in grupo_pess:
            entregas = _pes.get_entregas()
            if entregas:
                for entrega in entregas:
                    dadose = {}
                    dadose['id_entrega'] = str(entrega.id)
                    dadose['entrega_cancelada'] = entrega.cancelado
                    dadose['nome_entrega'] = entrega.titulo
                    dadose['meta_entrega'] = int(entrega.meta)
                    dadose['tipo_meta'] = entrega.get_metrica_para_api()
                    dadose['data_entrega'] = entrega.get_data_entrega_para_api()
                    dadose['nome_unidade_demandante'] = entrega.get_demandante_para_api()
                    dadose['nome_unidade_destinataria'] = entrega.get_destinatario_para_api()
                    lista_se.append(dadose)
    dados['entregas'] = lista_se

    return dados


"""
def get_dados_parcipante_ativo_api(pit):
    dados = {}
    dados['origem_unidade'] = 'SIAPE'
    dados['cod_unidade_autorizadora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))

    # cod_unidade_lotacao = get_setor_siape_lotacao_servidor_no_periodo(pit.adesao.servidor, pit.data_inicio, pit.data_fim)
    # if cod_unidade_lotacao:
    #    cod_unidade_lotacao = int(cod_unidade_lotacao.codigo)
    # else:
    #    cod_unidade_lotacao = int(pit.get_cod_unidade_executora_para_api())
    # dados['cod_unidade_lotacao'] = cod_unidade_lotacao
    dados['cod_unidade_lotacao'] = get_cod_unidade_lotacao_parcipante(pit)

    dados['matricula_siape'] = pit.adesao.servidor.matricula.zfill(7)
    dados['cod_unidade_instituidora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
    dados['cpf'] = pit.adesao.servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
    dados['situacao'] = 1
    dados['modalidade_execucao'] = pit.get_modalidade_execucao_para_api()
    dados['data_assinatura_tcr'] = str(pit.get_data_assinatura_tcr_para_api())

    return dados
"""


def get_dados_parcipante_api(participante):
    dados = {}
    dados['origem_unidade'] = 'SIAPE'
    dados['cod_unidade_autorizadora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
    dados['cod_unidade_lotacao'] = participante.cod_unidade_lotacao
    dados['matricula_siape'] = participante.servidor.matricula.zfill(7)
    dados['cod_unidade_instituidora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
    dados['cpf'] = participante.servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
    dados['situacao'] = participante.situacao
    dados['modalidade_execucao'] = participante.modalidade_execucao
    dados['data_assinatura_tcr'] = participante.data_assinatura_tcr

    return dados


def get_dados_api_pit(pit, com_entregas_e_avaliacao=True):
    dados = {}
    dados['origem_unidade'] = 'SIAPE'
    dados['cod_unidade_autorizadora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
    dados['id_plano_trabalho'] = str(pit.id)
    dados['status'] = pit.get_situacao_api()
    dados['cod_unidade_executora'] = int(pit.get_cod_unidade_executora_para_api())
    dados['cpf_participante'] = pit.adesao.servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
    dados['matricula_siape'] = pit.adesao.servidor.matricula.zfill(7)

    cod_unidade_lotacao = get_setor_siape_lotacao_servidor_no_periodo(pit.adesao.servidor, pit.data_inicio, pit.data_fim)
    if cod_unidade_lotacao:
        cod_unidade_lotacao = int(cod_unidade_lotacao.codigo)
    else:
        cod_unidade_lotacao = int(pit.get_cod_unidade_executora_para_api())
    dados['cod_unidade_lotacao_participante'] = cod_unidade_lotacao

    dados['data_inicio'] = str(pit.data_inicio)
    dados['data_termino'] = str(pit.data_fim)
    dados['carga_horaria_disponivel'] = int(pit.tempo_planejado_total)
    dados['contribuicoes'] = None
    dados['avaliacoes_registros_execucao'] = None

    if com_entregas_e_avaliacao:
        # Dados das contribuicoes
        contribuicoes = []
        for contribuicao in pit.get_entregas_pit_para_rit():
            dados_contribuicao = {}
            dados_contribuicao['id_contribuicao'] = str(contribuicao.id)
            dados_contribuicao['tipo_contribuicao'] = contribuicao.get_tipo_contribuicao_para_api()
            dados_contribuicao['percentual_contribuicao'] = contribuicao.get_percentual_contribuicao_para_api()

            id_plano_entregas_para_api = contribuicao.get_id_plano_entregas_para_api()
            if id_plano_entregas_para_api:
                dados_contribuicao['id_plano_entregas'] = str(id_plano_entregas_para_api)

            id_entrega_para_api = contribuicao.get_id_entrega_para_api()
            if id_entrega_para_api:
                dados_contribuicao['id_entrega'] = str(id_entrega_para_api)

            contribuicoes.append(dados_contribuicao)
        if contribuicoes:
            dados['contribuicoes'] = contribuicoes

        # Dados da avaliação
        avaliacoes = []
        if pit.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT:
            dados_avaliacao = {}
            dados_avaliacao['id_periodo_avaliativo'] = str(pit.get_ultima_analise_de_homologacao_do_rit().id)
            dados_avaliacao['data_inicio_periodo_avaliativo'] = str(pit.data_inicio)
            dados_avaliacao['data_fim_periodo_avaliativo'] = str(pit.data_fim)
            # Avaliação dos registros de execução do plano de trabalho no respectivo período avaliativo, em uma das seguintes escalas:
            # 1 - excepcional: plano de trabalho executado muito acima do esperado;
            # 2 - alto desempenho: plano de trabalho executado acima do esperado;
            # 3 - adequado: plano de trabalho executado dentro do esperado;
            # 4 - inadequado: plano de trabalho executado abaixo do esperado ou parcialmente executado;
            # 5 - não executado: plano de trabalho integralmente não executado.
            dados_avaliacao['avaliacao_registros_execucao'] = pit.avaliacao_rit
            dados_avaliacao['data_avaliacao_registros_execucao'] = str(pit.get_ultima_analise_de_homologacao_do_rit().data_parecer.date())
            avaliacoes.append(dados_avaliacao)
        if avaliacoes:
            dados['avaliacoes_registros_execucao'] = avaliacoes

    return dados


def resetar_envio_pits():
    PlanoIndividualTrabalho.objects.all().update(deve_enviar_pela_api=False, data_hora_ultimo_envio_api=None, situacao_api_no_ultimo_envio=None)


def resetar_envio_dados():
    LogApi.objects.all().delete()
    resetar_envio_dados_exceto_log()


def resetar_envio_dados_exceto_log():
    ParticipantePgd.objects.all().delete()
    PlanoEntregasSetorial.objects.all().update(
        cod_siape_grupo=None,
        principal_siape_grupo=False,
        identificador_externo=None,
        data_hora_ultima_alteracao_apos_aprovacao=None,
        data_hora_ultimo_envio_api=None,
    )
    resetar_envio_pits()


def deve_enviar_hoje():
    ultimo_log = LogApi.objects.filter(eh_preparacao_para_primeiro_envio=False).order_by('-id').first()
    if ultimo_log:
        if ultimo_log.executado_sem_erro_impeditivo():
            return get_datetime_now().date() >= ultimo_log.data_proximo_envio_por_sucesso
        return get_datetime_now().date() >= ultimo_log.data_proximo_envio_por_erro
    return True


# ===================================
# Envio e preparação dos dados
# ===================================


# PES
# --------------------
def preparar_pess_para_api(log_api=None):
    pes_atual = None

    # Seta a ultima alteracao de cada PES após sua aprovacao.
    try:
        pess = PlanoEntregasSetorial.get_pess_aprovados()
        lista_pess_atualizar = []
        for pes in tqdm.tqdm(pess):
            pes_atual = pes
            pes.data_hora_ultima_alteracao_apos_aprovacao = (
                RegistroAcaoPES.objects.filter(pes=pes, realizada_apos_aprovacao_pes=True).order_by('-data').first().data
            )
            lista_pess_atualizar.append(pes)
        if lista_pess_atualizar:
            PlanoEntregasSetorial.objects.bulk_update(lista_pess_atualizar, fields=['data_hora_ultima_alteracao_apos_aprovacao'])
    except Exception as e:
        erro = f'Erro ao preparar dados do PES: {e} \n\n\n {pes_atual}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
        return False

    return True


def gerar_identificadores(log_api=None):
    try:
        # ==========================================
        # Sabendo os setores que tem PES e para cada um deles saber o seu SIAPE
        # ==========================================
        ids_setores_com_pes = PlanoEntregasSetorial.get_pess_aprovados().filter(cod_siape_grupo__isnull=True).values_list('setor_id', flat=True)
        ids_setores_com_pes = list(ids_setores_com_pes)
        ids_setores_com_pes = set(ids_setores_com_pes)
        setores_pgd = get_setores_pgd().filter(id__in=ids_setores_com_pes)

        # cod_siape_grupo
        # - seta o SIAPE do setor do PES
        # - os setores que forem apenas SUAP recebem o siape do setor superior mais próximo a ele
        # ------------------------
        if setores_pgd:
            lista_setores_pes_siape = []
            for setor_pgd in tqdm.tqdm(setores_pgd):
                cs = get_codigo_siape_setor(setor_pgd)
                if cs:
                    lista_setores_pes_siape.append((setor_pgd.id, cs))
            if lista_setores_pes_siape:
                for lsp in tqdm.tqdm(lista_setores_pes_siape):
                    pess = PlanoEntregasSetorial.get_pess_aprovados().filter(cod_siape_grupo__isnull=True, setor_id=lsp[0])
                    pess.update(cod_siape_grupo=lsp[1])

        # Seta identificador_externo para quem ainda nao tem
        # - dentro de um mesmo grupo de PESs o identificador define a qual período o PES está relacionado
        # - este identificador é o que será enviado pela API para identificar o PES
        # ------------------------
        pess = PlanoEntregasSetorial.get_pess_aprovados().filter(cod_siape_grupo__isnull=False, identificador_externo__isnull=True)
        if pess:
            for pes in tqdm.tqdm(pess):
                pes.identificador_externo = f'{pes.periodo_pes.id}{pes.cod_siape_grupo}'
                pes.save(update_fields=['identificador_externo'])

    except Exception as e:
        erro = f'Erro ao gerar/atualizar identificadores dos PESs: {e}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
        return False

    return True


def enviar_dados_pes_api(log_api=None):
    # ============================================
    # Enviar dados
    # ============================================
    pes_atual = None
    dados_atual = None

    qtd_envios_sucesso_pes = 0
    qtd_envios_erro_pes = 0

    try:
        pess_enviar = PlanoEntregasSetorial.get_pess_aprovados().filter(identificador_externo__isnull=False)
        pess_enviar = pess_enviar.filter(
            Q(data_hora_ultimo_envio_api__isnull=True)
            | (Q(data_hora_ultimo_envio_api__isnull=False) & Q(data_hora_ultima_alteracao_apos_aprovacao__gt=F('data_hora_ultimo_envio_api')))
        )

        # ************** TESTE
        pess_enviar = pess_enviar.filter(setor__sigla='ETEP/NC')
        #

        pess_enviar = pess_enviar.order_by('identificador_externo').distinct('identificador_externo')

        lista_pess_atualizar = []
        for pes in tqdm.tqdm(pess_enviar):
            dados_atual = None
            pes_atual = pes

            # dados = get_dados_api_grupo_pes(pes.identificador_externo)
            dados = get_dados_api_grupo_pes(pes)
            dados_atual = dados

            retorno = enviar_dados('enviar_dados_pes_api', dados)
            if not retorno[0]:
                qtd_envios_erro_pes += 1
                if log_api:
                    log_api.qtd_envios_sucesso_pes = qtd_envios_sucesso_pes
                    log_api.qtd_envios_erro_pes = qtd_envios_erro_pes
                    log_api.save()
                erro = f'>>> Erro ao enviar dados dos PESs ------------ \n > PES: \n{pes} \n > RETORNO API: \n{retorno[1]} \n\n\n'
                LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
                if lista_pess_atualizar:
                    PlanoEntregasSetorial.objects.bulk_update(lista_pess_atualizar, fields=['data_hora_ultimo_envio_api'])
                return False
            else:
                qtd_envios_sucesso_pes += 1
                pes.data_hora_ultimo_envio_api = get_datetime_now()
                lista_pess_atualizar.append(pes)

        if lista_pess_atualizar:
            PlanoEntregasSetorial.objects.bulk_update(lista_pess_atualizar, fields=['data_hora_ultimo_envio_api'])

        if log_api:
            log_api.qtd_envios_sucesso_pes = qtd_envios_sucesso_pes
            log_api.qtd_envios_erro_pes = qtd_envios_erro_pes
            log_api.save()

    except Exception as e:
        erro = f'>>> Erro ao enviar dados dos PESs ------------ \n > PES: \n{pes_atual} \n > ERRO: \n{e} \n > DADOS: {dados_atual} \n\n\n'
        if log_api:
            log_api.qtd_envios_sucesso_pes = qtd_envios_sucesso_pes
            log_api.qtd_envios_erro_pes = qtd_envios_erro_pes
            log_api.save()
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
        return False

    return True


# Participante
# --------------------
def preparar_participantes_para_api(log_api=None):
    participante_atual = None

    # Seta a ultima alteracao de cada PES após sua aprovacao.
    try:
        """
        Pega as adesões de todo mundo que está no PGD
        - Pega o ultimo pit homologado de cada adesao
        - Cria novo participante
            - Se o ultimo participante tiver nao mesmo setor do PIT (ver como faz isso em get_dados_parcipante_ativo_api)
            - Se o ultimo participante nao tiver a mesma modalidade execução do PIT
            - Marca para envio caso crie
        """
        lista_participantes_criar = []
        # TESTE
        adesoes_em_pgd = SolicitacaoAdesaoServidor.get_adesoes_em_pgd().filter(servidor__setor__sigla='ETEP/NC')

        for adesao in tqdm.tqdm(adesoes_em_pgd):
            participante_atual = adesao.servidor
            ultimo_pit = PlanoIndividualTrabalho.get_ultimo_pit_homologado_adesao(adesao)
            cod_unidade_lotacao = get_cod_unidade_lotacao_parcipante(ultimo_pit)
            modalidade_execucao = ultimo_pit.get_modalidade_execucao_para_api()

            participante = ParticipantePgd.objects.filter(servidor=adesao.servidor)
            participante = participante.filter(cod_unidade_lotacao=cod_unidade_lotacao)
            participante = participante.filter(modalidade_execucao=modalidade_execucao).first()

            if not participante:
                participante_novo = ParticipantePgd()
                participante_novo.servidor = adesao.servidor
                participante_novo.cod_unidade_lotacao = cod_unidade_lotacao
                participante_novo.modalidade_execucao = modalidade_execucao
                participante_novo.data_assinatura_tcr = str(ultimo_pit.get_data_assinatura_tcr_para_api())
                participante_novo.deve_enviar_pela_api = True
                lista_participantes_criar.append(participante_novo)

        if lista_participantes_criar:
            ParticipantePgd.objects.bulk_create(lista_participantes_criar)

        """
        Atualiza desligamentos
        - Pega todos os partipantes
            - Seta todos para ativo (0: Inativo; 1: Ativo)
            - Lista os desligados dentre os que estão nos partipantes
            - Desliga o partipante que tiver entre os desligados desligado
                - marca para enviar
        """
        ParticipantePgd.objects.all().update(situacao=1)
        participantes = ParticipantePgd.objects.exclude(servidor_id__in=adesoes_em_pgd.values_list('servidor_id'))
        participantes.update(situacao=0, deve_enviar_pela_api=True)

    except Exception as e:
        erro = f'Erro ao preparar dados do Participante: {e} \n\n\n {participante_atual}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
        return False

    return True


# antigo enviar_dado_participante_ativo_api
def enviar_dados_participantes_para_api(eh_envio_manual=False, log_api=None):
    partipante_atual = None

    qtd_envios_sucesso_participante = 0
    qtd_envios_erro_participante = 0

    try:
        lista_participantes_enviados = []
        for participante in tqdm.tqdm(ParticipantePgd.objects.filter(deve_enviar_pela_api=True)):
            partipante_atual = participante

            dados = get_dados_parcipante_api(participante)

            partipante_atual = dados
            retorno = enviar_dados('enviar_dados_participantes_para_api', dados, eh_envio_manual)
            if not retorno[0]:
                erro = f'Erro ao enviar dados do participante {partipante_atual} \n {retorno[1].get("text")}'
                LogApiDetalhe.registrar(
                    log=log_api, url=retorno[1].get('url'), status_code=retorno[1].get('status_code'), erro_impeditivo=None, erro_nao_impeditivo=erro
                )
                qtd_envios_erro_participante += 1
            else:
                qtd_envios_sucesso_participante += 1
                participante.deve_enviar_pela_api = False
                lista_participantes_enviados.append(participante)

        if lista_participantes_enviados:
            ParticipantePgd.objects.bulk_update(lista_participantes_enviados, fields=['deve_enviar_pela_api'])

        if log_api:
            log_api.qtd_envios_sucesso_participante = qtd_envios_sucesso_participante
            log_api.qtd_envios_erro_participante = qtd_envios_erro_participante
            log_api.save()

    except Exception as e:
        erro = f'Erro ao enviar dados do participante {partipante_atual} - {e}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
        if log_api:
            log_api.qtd_envios_sucesso_participante = qtd_envios_sucesso_participante
            log_api.qtd_envios_erro_participante = qtd_envios_erro_participante
            log_api.save()
        return False

    return True


# PIT
# --------------------


def preparar_pits_para_api(deve_enviar_todos, eh_envio_manual, servidor_envio_manual, log_api=None):
    # Preparação
    # - Para todos os que não estão marcados para enviar por padrão OU nao tem data envio (nunca foram enviados)
    #   - Algumas funcionalidades já marcam o PIT para enviar
    # - Marca para enviar pelas alteracoes

    if not deve_enviar_todos:
        try:
            pits_ajustar = PlanoIndividualTrabalho.objects.filter(Q(deve_enviar_pela_api=False) | Q(data_hora_ultimo_envio_api__isnull=True)).exclude(
                Q(situacao=PlanoIndividualTrabalho.EM_CADASTRO) | Q(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
            )

            if eh_envio_manual:
                pits_ajustar = pits_ajustar.filter(adesao__servidor=servidor_envio_manual)

            lista_pits_atualizar = []

            # *************************************
            # TESTE
            # *************************************
            pits_ajustar = pits_ajustar.filter(adesao__servidor__setor__sigla='ETEP/NC')

            for pit in tqdm.tqdm(pits_ajustar):
                if pit.data_hora_ultimo_envio_api:
                    ultima_alteracao = (
                        RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=pit, realizada_apos_aprovacao_pit=True).order_by('-data').first()
                    )
                    if ultima_alteracao:
                        if ultima_alteracao.data >= pit.data_hora_ultimo_envio_api:
                            pit.deve_enviar_pela_api = True
                else:
                    pit.deve_enviar_pela_api = True
                lista_pits_atualizar.append(pit)

            if lista_pits_atualizar:
                PlanoIndividualTrabalho.objects.bulk_update(lista_pits_atualizar, fields=['deve_enviar_pela_api'])

        except Exception as e:
            erro = f'Erro ao preparar os PITs que devem ser enviados:\n{e}'
            LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=erro, erro_nao_impeditivo=None)
            return False, erro

    return True, None


def selecionar_pits(deve_enviar_todos, eh_envio_manual, envio_manual_forcar, servidor_envio_manual, log_api=None):
    # Busca pelos PITs
    if deve_enviar_todos:
        resetar_envio_pits()
        pits_enviar = PlanoIndividualTrabalho.objects.all().exclude(
            Q(situacao=PlanoIndividualTrabalho.EM_CADASTRO) | Q(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
        )
    else:
        pits_enviar = PlanoIndividualTrabalho.objects.filter(deve_enviar_pela_api=True).exclude(
            Q(situacao=PlanoIndividualTrabalho.EM_CADASTRO) | Q(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
        )
        if eh_envio_manual:
            if envio_manual_forcar:
                pits_enviar = PlanoIndividualTrabalho.objects.exclude(
                    Q(situacao=PlanoIndividualTrabalho.EM_CADASTRO) | Q(situacao=PlanoIndividualTrabalho.AGUARDANDO_PARECER)
                )
            pits_enviar = pits_enviar.filter(adesao__servidor=servidor_envio_manual)

    # Filtra pelos que já foram homologados ao menos uma vez
    ja_foram_homologados = PitSolicitacaoAnaliseSetor.objects.filter(
        solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
        solicitacao__finalizado=True,
        parecer=True,
        tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
    ).values('solicitacao__pit__id')
    pits_enviar = pits_enviar.filter(id__in=ja_foram_homologados)

    # Procurando por PITs que não tenham PES principal
    # - Isso pode ocorrer quando o PIT do servidor está relacionado a um setor que não tem PES
    # - OU pode ocorrer quando se tem algum problema no histórico de setor do servidor
    # --------------------------------------------
    lista_ids_exclude_pits_envio = []
    lista_problema_nao_tem_setor_pode_homologar = pits_enviar.filter(setor_pode_homologar_pit_rit__isnull=True)
    lista_problema_nao_tem_pes_principal = PitSetores.objects.filter(pit_id__in=pits_enviar.values('id'), pode_homologar=True, pes__isnull=True)
    if lista_problema_nao_tem_setor_pode_homologar:
        lista_ids_exclude_pits_envio += list(lista_problema_nao_tem_setor_pode_homologar.values_list('id', flat=True))
        # erro_nao_impeditivo.append('\n\n\n >>> PITs sem setor que pode homologar ------------------')
        for p in lista_problema_nao_tem_setor_pode_homologar:
            # erro_nao_impeditivo.append(f'[{p.id}] {p}')
            add_erro_nao_impeditivo = 'PIT sem setor que pode homologar ------------------ \n'
            add_erro_nao_impeditivo += f'[{p.id}] {p}'
            LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=None, erro_nao_impeditivo=add_erro_nao_impeditivo)
    if lista_problema_nao_tem_pes_principal:
        lista_ids_exclude_pits_envio += list(lista_problema_nao_tem_pes_principal.values_list('pit_id', flat=True))
        # erro_nao_impeditivo.append('\n\n\n >>> PITs sem PES principal aprovado ------------------')
        for p in lista_problema_nao_tem_pes_principal:
            # erro_nao_impeditivo.append(f'[{p.pit.id}] {p.pit} - {p}')
            add_erro_nao_impeditivo = 'PIT sem PES principal aprovado ------------------ \n'
            add_erro_nao_impeditivo += f'[{p.pit.id}] {p.pit} - {p}'
            LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=None, erro_nao_impeditivo=add_erro_nao_impeditivo)

    if lista_ids_exclude_pits_envio:
        pits_enviar = pits_enviar.exclude(id__in=lista_ids_exclude_pits_envio)

    pits_enviar = pits_enviar.select_related('adesao', 'adesao__servidor')
    pits_enviar = pits_enviar.order_by('periodo_pit_rit__data_inicio', 'id')
    return pits_enviar


def enviar_dados_pits(servidor_envio_manual=None, envio_manual_forcar=False, log_api=None, retornar_erros=False):
    eh_envio_manual = False
    if servidor_envio_manual:
        eh_envio_manual = True

    # ============================================
    # Antes do primeiro envio de pit
    # - Se nao tem algum marcado com data de ultimo envio
    # - Deve enviar todos
    # ============================================
    deve_enviar_todos = not PlanoIndividualTrabalho.objects.filter(data_hora_ultimo_envio_api__isnull=False).exists()
    if eh_envio_manual:
        deve_enviar_todos = False

    # ============================================
    # Enviar dados
    # ============================================
    pit_atual = None

    qtd_envios_sucesso_pit = 0
    qtd_envios_erro_pit = 0

    try:
        retorno_preparar_pits_para_api = preparar_pits_para_api(deve_enviar_todos, eh_envio_manual, servidor_envio_manual, log_api=None)
        if not retorno_preparar_pits_para_api[0]:
            if retornar_erros:
                return False, retorno_preparar_pits_para_api[1]

        pits_enviar = selecionar_pits(deve_enviar_todos, eh_envio_manual, envio_manual_forcar, servidor_envio_manual, log_api)

        # *************************************
        # TESTE
        # *************************************
        pits_enviar = pits_enviar.filter(adesao__servidor__setor__sigla='ETEP/NC')

        for pit in tqdm.tqdm(pits_enviar):
            pit_atual = pit

            participante_existe = ParticipantePgd.objects.filter(servidor=pit.adesao.servidor).exists()

            if not participante_existe:
                add_erro_nao_impeditivo = f'Erro ao enviar dados do PIT {pit.id} - {pit} \n Participamnte não existe em ParticipantePgd'
                LogApiDetalhe.registrar(
                    log=log_api,
                    url=None,
                    status_code=None,
                    erro_impeditivo=None,
                    erro_nao_impeditivo=add_erro_nao_impeditivo,
                )
                qtd_envios_erro_pit += 1

            if participante_existe:
                # Envia PIT
                dados = get_dados_api_pit(pit, com_entregas_e_avaliacao=True)
                retorno_envio_pit = enviar_dados('enviar_dados_pits', dados)

                if not retorno_envio_pit[0]:
                    add_erro_nao_impeditivo = f'Erro ao enviar dados do PIT {pit.id} - {pit} \n {retorno_envio_pit[1].get("text")}'
                    LogApiDetalhe.registrar(
                        log=log_api,
                        url=retorno_envio_pit[1].get('url'),
                        status_code=retorno_envio_pit[1].get('status_code'),
                        erro_impeditivo=None,
                        erro_nao_impeditivo=add_erro_nao_impeditivo,
                    )
                    qtd_envios_erro_pit += 1
                    if retornar_erros:
                        return False, add_erro_nao_impeditivo
                else:
                    pit.marcar_como_enviado_pela_api()
                    qtd_envios_sucesso_pit += 1

        # Contabilização final
        if log_api:
            log_api.qtd_envios_sucesso_pit = qtd_envios_sucesso_pit
            log_api.qtd_envios_erro_pit = qtd_envios_erro_pit
            log_api.save()

    except Exception as e:
        # Contabilização final
        if log_api:
            log_api.qtd_envios_sucesso_pit = qtd_envios_sucesso_pit
            log_api.qtd_envios_erro_pit = qtd_envios_erro_pit
            log_api.save()

        detalhe = traceback.format_exc().replace('\n', '\n\t')
        erro_outros = None
        if pit_atual:
            erro_outros = f'Erro ao enviar dados de PITs: {pit_atual.id} - {pit_atual} \n Erro:\n {e} \n Detalhe:\n {detalhe}'
        else:
            erro_outros = f'Erro ao enviar dados de PITs: \n Erro:\n {e} \n Detalhe:\n {detalhe}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=None, erro_nao_impeditivo=erro_outros)
        if retornar_erros:
            return False, erro_outros

    return True, None


"""
def enviar_dados_desligamento_participantes(servidor_envio_manual=None, log_api=None, retornar_erros=False):
    partipante_atual = None

    try:
        part_dados_auxiliares = ParticipantePgd.objects.all()
        if servidor_envio_manual:
            part_dados_auxiliares = part_dados_auxiliares.filter(servidor=servidor_envio_manual)

        qtd_envios_sucesso_desligamento = 0
        qtd_envios_erro_desligamento = 0

        for participante in tqdm.tqdm(part_dados_auxiliares):
            partipante_atual = str(participante.servidor)

            desligado, data_desligamento = SolicitacaoAdesaoServidor.get_situacao_desligamento_atual_para_api(participante.servidor)

            if desligado:
                dados = {}
                dados['origem_unidade'] = 'SIAPE'
                dados['cod_unidade_autorizadora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
                dados['cod_unidade_lotacao'] = participante.cod_unidade_lotacao
                dados['matricula_siape'] = participante.servidor.matricula.zfill(7)
                dados['cod_unidade_instituidora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
                dados['cpf'] = participante.servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
                dados['situacao'] = 0
                dados['modalidade_execucao'] = participante.modalidade_execucao
                dados['data_assinatura_tcr'] = str(data_desligamento)

                partipante_atual = dados
                retorno = enviar_dados('enviar_dados_desligamento_participantes', dados)
                if not retorno[0]:
                    qtd_envios_erro_desligamento += 1
                    erro = f'\n Erro ao enviar dados de desligamento do participante {partipante_atual} \n {retorno[1].get("text")} \n'
                    LogApiDetalhe.registrar(
                        log=log_api,
                        url=retorno[1].get('url'),
                        status_code=retorno[1].get('status_code'),
                        erro_impeditivo=None,
                        erro_nao_impeditivo=erro,
                    )
                    if retornar_erros:
                        return False, erro
                else:
                    qtd_envios_sucesso_desligamento += 1

        if log_api:
            log_api.qtd_envios_sucesso_desligamento = qtd_envios_sucesso_desligamento
            log_api.qtd_envios_erro_desligamento = qtd_envios_erro_desligamento
            log_api.save()

    except Exception as e:
        detalhe = traceback.format_exc().replace('\n', '\n\t')
        erro = f'Erro ao enviar dados de desligamento do participante: {partipante_atual} \n Erro:\n {e} \n Detalhe:\n {detalhe}'
        LogApiDetalhe.registrar(log=log_api, url=None, status_code=None, erro_impeditivo=None, erro_nao_impeditivo=erro)
        if retornar_erros:
            return False, erro
        return False

    if retornar_erros:
        return True, None
    return True
"""


# Envio
# --------------------


def enviar_dados_api(forcar_envio=False):
    # print('============================')
    # print(' API PGD 2')
    # print('============================')

    pode_seguir = forcar_envio or deve_enviar_hoje()

    if pode_seguir and not get_config_api():
        pode_seguir = False

    get_token()
    if not TOKEN_API_PGD_2:
        pode_seguir = False

    # -----------------------------------------------------
    # Envio e preparação dos dados específicos
    # -----------------------------------------------------
    log_api = LogApi()
    if pode_seguir:
        log_api.eh_preparacao_para_primeiro_envio = False
        log_api.data_hora_inicio = get_datetime_now()
        log_api.data_proximo_envio_por_sucesso = amanha()  # Força envio todos os dias -- proximo_domingo()
        log_api.data_proximo_envio_por_erro = amanha()
        log_api.url = get_url_api()
        log_api.save()

    # PES
    # -----------------------------------------------------
    if pode_seguir:
        # print('>>> Preparar dados dos PESs')
        retorno = preparar_pess_para_api(log_api)
        if not retorno:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    if pode_seguir:
        # print('>>> Identificadores dos PESs')
        retorno = gerar_identificadores(log_api)
        if not retorno:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    if pode_seguir:
        # print('>>> Envio dos PESs')
        retorno = enviar_dados_pes_api(log_api)
        if not retorno:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    # Participantes
    # -----------------------------------------------------

    if pode_seguir:
        # print('>>> Preparar dados dos Participantes')
        retorno = preparar_participantes_para_api(log_api)
        if not retorno:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    if pode_seguir:
        # print('>>> Enviar participantes')
        retorno = enviar_dados_participantes_para_api(log_api=log_api)
        if not retorno:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    # PITs
    # -----------------------------------------------------
    if pode_seguir:
        # print('>>> Peparar e Enviar PITs')
        retorno = enviar_dados_pits(log_api=log_api)
        if not retorno[0]:
            log_api.data_hora_fim = get_datetime_now()
            log_api.save()
            pode_seguir = False

    # Finalizando
    # -----------------------------------------------------
    if pode_seguir:
        log_api.data_hora_fim = get_datetime_now()
        log_api.save()

    # print('> Fim do procedimento da API')


# ===================================
# Funções para PESs e PITs específicos
# - Não são utlizadas no fluxo de envio normal (enviar_dados_api)
# - São utilizadas apenas nas telas de PES e PIT
# ===================================


def get_pit_api(pit):
    erro = None
    try:
        tk = get_token_envio_manual()
        hd = get_header(tk)

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')
        id_plano_trabalho = str(pit.id)

        url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'
        response = requests.get(url=url, headers=hd, timeout=get_timeout())
        if response.ok:
            return True, response.json()
        else:
            erro = f'Erro {response.status_code} - {response.text}'
            return False, erro
    except Exception as e:
        erro = f'Erro - {e}'

    return False, erro


def get_participante_api(servidor):
    erro = None
    try:
        participante = ParticipantePgd.objects.filter(servidor=servidor).first()

        tk = get_token_envio_manual()
        hd = get_header(tk)

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')
        cod_unidade_lotacao = participante.cod_unidade_lotacao
        matricula_siape = participante.servidor.matricula

        url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}'

        response = requests.get(url=url, headers=hd, timeout=get_timeout())
        if response.ok:
            return True, response.json()
        else:
            erro = f'Erro {response.status_code} - {response.text}'
            return False, erro
    except Exception as e:
        erro = f'Erro - {e}'

    return False, erro


def get_pes_api(pes):
    erro = None
    try:
        tk = get_token_envio_manual()
        hd = get_header(tk)

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
        id_plano_entregas = str(pes.identificador_externo)

        url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_entregas/{id_plano_entregas}'
        response = requests.get(url=url, headers=hd, timeout=get_timeout())
        if response.ok:
            return True, response.json()
        else:
            erro = f'Erro {response.status_code} - {response.text}'
            return False, erro
    except Exception as e:
        erro = f'Erro - {e}'

    return False, erro


"""
def put_pit_api(pit):
    ja_foram_homologados = PitSolicitacaoAnaliseSetor.objects.filter(
        solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
        solicitacao__finalizado=True,
        parecer=True,
        tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
        solicitacao__pit__id=pit.id,
    ).exists()
    if not ja_foram_homologados:
        return False, 'SUAP: PIT precisa ter sido homologado ao menos uma vez', None

    if not pit.setor_pode_homologar_pit_rit:
        return False, 'SUAP: não existe setor que possa homologar o PIT', None

    nao_tem_pes_principal = PitSetores.objects.filter(pit_id=pit.id, pode_homologar=True, pes__isnull=True).exists()
    if nao_tem_pes_principal:
        return False, 'SUAP: não existe PES principal', None

    erro = None
    response = None

    try:
        tk = get_token_envio_manual()
        hd = get_header(tk)

        dados_pit = get_dados_api_pit(pit, com_entregas_e_avaliacao=False)
        origem_unidade = dados_pit.get('origem_unidade')
        cod_unidade_autorizadora = dados_pit.get('cod_unidade_autorizadora')
        id_plano_trabalho = dados_pit.get('id_plano_trabalho')
        #
        url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'
        response = requests.put(url=url, data=json.dumps(dados_pit), headers=hd, timeout=get_timeout())

        if response.ok:
            dados_pit = get_dados_api_pit(pit, com_entregas_e_avaliacao=True)
            origem_unidade = dados_pit.get('origem_unidade')
            cod_unidade_autorizadora = dados_pit.get('cod_unidade_autorizadora')
            id_plano_trabalho = dados_pit.get('id_plano_trabalho')
            #
            url = f'{get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'
            response = requests.put(url=url, data=json.dumps(dados_pit), headers=hd, timeout=get_timeout())
            if not response.ok:
                return False, response.json(), dados_pit
        else:
            return False, response.json(), dados_pit

    except Exception as e:
        erro = f'Erro - {e}'

    if erro:
        return False, erro, None

    return True, response.json(), None

"""
