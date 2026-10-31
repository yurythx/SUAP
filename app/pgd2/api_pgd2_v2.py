import concurrent.futures
import copy
import json
import logging
import traceback

import tqdm
from django.conf import settings
from django.db.models import F, Q
from requests import Session
from requests.exceptions import HTTPError, RequestException

from comum.models import APIExterna, Configuracao
from comum.services import APIExternaService
from comum.utils import get_sigla_reitoria
from djtools.utils import requests
from pgd2.models import (
    LogApi,
    LogApiDetalhe,
    LogApiParticipanteEnvio,
    LogApiPesEnvio,
    LogApiPitEnvio,
    ParticipantePgd,
    PitSetores,
    PlanoEntregasSetorial,
    PlanoIndividualTrabalho,
    RegistroAcaoPES,
    SetorPgdApi,
    SolicitacaoAdesaoServidor,
)
from pgd2.utils import (
    amanha,
    get_datetime_now,
    get_max_workers,
    get_metodo_obter_codigo_siape_setor,
    get_setor_siape_lotacao_servidor_no_periodo,
    get_setores_pgd,
    get_timeout_pgd2,
)
from rh.models import Setor, UnidadeOrganizacional

logger = logging.getLogger(__name__)


def get_api_pgd2_v2():
    api_pgd = None
    if not settings.DEBUG:
        api_externa = APIExterna.PGD
        if not api_externa.ativo:
            logger.warning('API PGD2 não está ativa')
            return None
        api_pgd = api_externa.get_service()
    else:
        api_pgd = ApiPgd2V2()

    return api_pgd


class ApiPgd2V2(APIExternaService):
    max_workers = 10
    token_api_pgd2 = None
    log_api = None
    session = None
    header = None

    pits_para_enviar = []

    def __init__(self):
        super().__init__(APIExterna.PGD)

    # ===================================
    # Métodos auxiliares - Gerais
    # ===================================

    def get_versao_suap(self):
        try:
            primeira_linha = None
            with open(f'{settings.BASE_DIR}/CHANGELOG.md') as f:
                primeira_linha = f.readline().strip()
                return primeira_linha.split(' ')[1]
        except Exception:
            return 0

    def estah_acessivel(self, verbosity=False):
        try:
            self.set_token()
            self.set_header()

            api_externa = self.get_config_api()
            if api_externa and api_externa.client_id:
                url = f'{self.get_url_api()}/user/{api_externa.client_id}'
                response = requests.get(url=url, headers=self.header, timeout=self.get_timeout())
                return bool(response.ok and response.json())
            return False
        except Exception as e:
            if verbosity:
                logger.info(f'Erro ao verificar se a API PGD2 está acessível. Exception {e}')
            return False

    def get_config_api(self):
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
        except Exception:
            s_log_api = LogApi()
            if self.log_api:
                s_log_api = self.log_api
            s_log_api.data_hora_inicio = get_datetime_now()
            s_log_api.data_proximo_envio_por_sucesso = amanha()  # Força envio todos os dias -- proximo_domingo()
            s_log_api.data_proximo_envio_por_erro = amanha()
            s_log_api.save()
            erro = 'Não foram encontradas as configurações da API do PGD em "API Externa"'
            LogApiDetalhe.registrar(log=s_log_api, url=self.get_url_api(), erro_envio=erro)
        return config_api

    def get_url_api(self):
        try:
            return self.get_config_api().url_base
        except Exception:
            pass
        return None

    def get_timeout(self):
        return get_timeout_pgd2()

    def set_token_envio_manual(self):
        api_externa = self.get_config_api()
        if api_externa:
            URL_API = api_externa.url_base
            dados = {
                'username': api_externa.client_id,
                'password': api_externa.secret,
            }

            header = {'User-agent': f'User-Agent: SUAP/{self.get_versao_suap()} (https://portal.suap.ifrn.edu.br/)'}
            url_token = f'{URL_API}/token'
            response_login = requests.post(url=url_token, data=dados, headers=header, timeout=self.get_timeout())
            self.token_api_pgd2 = response_login.json().get('access_token')

    def set_token(self, obter_novo=True):
        erro_token = None

        try:
            if not obter_novo and not self.token_api_pgd2:
                obter_novo = True

            if obter_novo:
                api_externa = self.get_config_api()

                if api_externa:
                    URL_API = api_externa.url_base
                    dados = {
                        'username': api_externa.client_id,
                        'password': api_externa.secret,
                    }

                    header = {'User-agent': f'User-Agent: SUAP/{self.get_versao_suap()} (https://portal.suap.ifrn.edu.br/)'}
                    url_token = f'{URL_API}/token'
                    response_login = requests.post(url=url_token, data=dados, headers=header, timeout=self.get_timeout())

                    if response_login.ok:
                        self.token_api_pgd2 = response_login.json().get('access_token')
                    else:
                        erro_token = f'Erro ao obter token {response_login.status_code} - {response_login.text}'
                else:
                    self.token_api_pgd2 = None
                    erro_token = 'Não existe configuração de credencial da API'

        except Exception as e:
            detalhe = traceback.format_exc().replace('\n', '\n\t')
            erro_token = f'Erro ao tentar obter token \n Erro:\n {e} \n Detalhe:\n {detalhe} \n {erro_token}'
            self.token_api_pgd2 = None

        if not self.token_api_pgd2:
            s_log_api = LogApi()
            if self.log_api:
                s_log_api = self.log_api
            s_log_api.data_hora_inicio = get_datetime_now()
            s_log_api.data_proximo_envio_por_sucesso = amanha()  # Força envio todos os dias -- proximo_domingo()
            s_log_api.data_proximo_envio_por_erro = amanha()
            s_log_api.url = URL_API
            s_log_api.save()
            LogApiDetalhe.registrar(log=s_log_api, url=self.get_url_api(), erro_envio=erro_token)

    def set_header(self):
        self.header = {
            'User-agent': f'User-Agent: SUAP/{self.get_versao_suap()} (https://portal.suap.ifrn.edu.br/)',
            'accept': 'application/json',
            'Authorization': f'Bearer {self.token_api_pgd2}',
            'Content-Type': 'application/json',
        }

    def get_token(self):
        return self.token_api_pgd2

    def get_headers(self):
        return self.header

    def deve_enviar_hoje(self):
        ultimo_log = LogApi.objects.all().order_by('-id').first()
        if ultimo_log:
            if not ultimo_log.data_hora_fim:
                return False
        return True

    # ===================================
    # Funções auxiliares - Dados
    # ===================================

    def resetar_envio_pits(self):
        # inforna que todos os pits devem ser enviados (que ja foram homologados uma vez)
        PlanoIndividualTrabalho.objects.all().update(deve_enviar_pela_api=False)
        pits_enviar = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez()
        pits_enviar = pits_enviar.filter(situacao__in=[PlanoIndividualTrabalho.HOMOLOGADO, PlanoIndividualTrabalho.CANCELADO])
        pits_enviar = pits_enviar.update(deve_enviar_pela_api=True)

    def resetar_envio_dados_exceto_log(self):
        ParticipantePgd.objects.all().delete()
        PlanoEntregasSetorial.objects.all().update(
            cod_siape_grupo=None,
            principal_siape_grupo=False,
            identificador_externo=None,
            data_hora_ultima_alteracao_apos_aprovacao=None,
            data_hora_ultimo_envio_api=None,
        )
        self.resetar_envio_pits()

    def resetar_envio_dados(self):
        LogApi.objects.all().delete()
        self.resetar_envio_dados_exceto_log()

    def get_cod_unidade_lotacao_parcipante(self, pit):
        cod_unidade_lotacao = get_setor_siape_lotacao_servidor_no_periodo(pit.adesao.servidor, pit.data_inicio, pit.data_fim)
        if cod_unidade_lotacao:
            cod_unidade_lotacao = int(cod_unidade_lotacao.codigo)
        else:
            cod_unidade_lotacao = int(pit.get_cod_unidade_executora_para_api())
        return cod_unidade_lotacao

    def get_pits_sem_pes_ou_setor_pode_homologar(self, pits_enviar):
        pits_sem_pes_ou_setor_pode_homologar = PitSetores.objects.filter(pit__id__in=pits_enviar.values_list('id', flat=True), pode_homologar=True)
        pits_sem_pes_ou_setor_pode_homologar = pits_sem_pes_ou_setor_pode_homologar.filter(Q(pes__isnull=True) | Q(setor__isnull=True))
        return pits_sem_pes_ou_setor_pode_homologar.distinct('pit')

    def get_pits_com_pess_nao_enviados(self, pits_enviar):
        ids_pits_com_pess_nao_enviados = PitSetores.objects.filter(pit__id__in=pits_enviar.values_list('id', flat=True))
        ids_pits_com_pess_nao_enviados = ids_pits_com_pess_nao_enviados.filter(pes__data_hora_ultimo_envio_api__isnull=True)
        ids_pits_com_pess_nao_enviados = ids_pits_com_pess_nao_enviados.values_list('pit_id', flat=True)
        pits_sem_pes_enviado = pits_enviar.filter(id__in=ids_pits_com_pess_nao_enviados)
        return ids_pits_com_pess_nao_enviados, pits_sem_pes_enviado

    # Participantes
    # ===================================
    def get_manualmente_participante(self, adesao):
        # UTILIZADO APENAS PARA TESTES

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))

        ultimo_pit = PlanoIndividualTrabalho.get_ultimo_pit_homologado_adesao(adesao)
        cod_unidade_lotacao = self.get_cod_unidade_lotacao_parcipante(ultimo_pit)

        matricula_siape = adesao.servidor.matricula.zfill(7)

        url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}'

        return requests.get(url=url, headers=self.header, timeout=self.get_timeout())

    def get_dados_parcipante(self, participante):
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

    def preparar_participantes(self):
        servidor_atual = None

        try:
            servidores_adesao_atual = SolicitacaoAdesaoServidor.get_adesao_atual_dos_servidores_com_adesao_deferida()

            lista_participantes_criar, lista_participantes_atualizar = [], []

            for servidor in tqdm.tqdm(servidores_adesao_atual):
                servidor_atual = servidor
                if not (servidor.ultima_adesao and servidor.ultima_adesao[0]):
                    raise Exception('Não foi possível obter a última adesão do servidor')

                ultima_adesao = servidor.ultima_adesao[0]
                ultimo_pit_homologado_na_ultima_adesao = PlanoIndividualTrabalho.get_ultimo_pit_homologado_adesao(ultima_adesao)

                # ParticipantePgd: cod_unidade_lotacao, modalidade_execucao e situacao (0 - Inativo; 1 - Ativo)
                # - Trata também os casos de que a ultima adesão está desligada e/ou sem pit homologado e/ou sem pit algum
                #   - Assim, não tem ultimo pit
                cod_unidade_lotacao = None
                modalidade_execucao = None
                situacao = None
                data_assinatura_tcr = None
                if ultimo_pit_homologado_na_ultima_adesao:
                    cod_unidade_lotacao = self.get_cod_unidade_lotacao_parcipante(ultimo_pit_homologado_na_ultima_adesao)
                    modalidade_execucao = ultimo_pit_homologado_na_ultima_adesao.get_modalidade_execucao_para_api()
                    situacao = 0 if ultima_adesao.estah_desligado else 1
                    data_assinatura_tcr = str(ultimo_pit_homologado_na_ultima_adesao.get_data_assinatura_tcr_para_api())
                else:
                    ultimo_pit_homologado_do_servidor = PlanoIndividualTrabalho.get_ultimo_pit_homologado_do_servidor(servidor)
                    if ultimo_pit_homologado_do_servidor:
                        cod_unidade_lotacao = int(servidor.setor_lotacao.codigo)
                        modalidade_execucao = ultimo_pit_homologado_do_servidor.get_modalidade_execucao_para_api()
                        situacao = 0
                        data_assinatura_tcr = str(ultimo_pit_homologado_do_servidor.get_data_assinatura_tcr_para_api())

                if cod_unidade_lotacao and modalidade_execucao and situacao is not None and data_assinatura_tcr:
                    participante = ParticipantePgd.objects.filter(servidor=servidor).first()

                    if not participante:
                        participante_novo = ParticipantePgd()
                        participante_novo.servidor = servidor
                        participante_novo.cod_unidade_lotacao = cod_unidade_lotacao
                        participante_novo.modalidade_execucao = modalidade_execucao
                        participante_novo.situacao = situacao
                        participante_novo.data_assinatura_tcr = data_assinatura_tcr
                        participante_novo.deve_enviar_pela_api = True
                        participante_novo.data_hora_envio_api = None
                        lista_participantes_criar.append(participante_novo)
                    else:
                        existe_diferenca = (
                            participante.cod_unidade_lotacao != cod_unidade_lotacao
                            or participante.modalidade_execucao != modalidade_execucao
                            or participante.situacao != situacao
                        )
                        if existe_diferenca:
                            participante.cod_unidade_lotacao = cod_unidade_lotacao
                            participante.modalidade_execucao = modalidade_execucao
                            participante.situacao = situacao
                            participante.data_assinatura_tcr = data_assinatura_tcr
                            participante.deve_enviar_pela_api = True
                            participante.data_hora_envio_api = None
                            lista_participantes_atualizar.append(participante)
                else:
                    if SolicitacaoAdesaoServidor.tem_adesao_vigente(servidor.get_user()):
                        erro = f'Não foi possível preparar o participante {servidor_atual}: aparentemente ele possui adesão DEFERIDA mas talvez não possua plano de trabalho atual ou anterior que estejam homologados. A outra possibilidade é que não foi possível obter alguma dado específico do participante'
                        LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)

            if lista_participantes_criar:
                ParticipantePgd.objects.bulk_create(lista_participantes_criar)
            if lista_participantes_atualizar:
                lista_campos = [
                    'cod_unidade_lotacao',
                    'modalidade_execucao',
                    'situacao',
                    'data_assinatura_tcr',
                    'deve_enviar_pela_api',
                    'data_hora_envio_api',
                ]
                ParticipantePgd.objects.bulk_update(lista_participantes_atualizar, lista_campos)

        except Exception as e:
            erro = f'Erro ao preparar dados do Participante:\n{e}\n{servidor_atual}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def gerar_payload_participantes(self):
        try:
            payload = []
            for participante in tqdm.tqdm(ParticipantePgd.objects.filter(deve_enviar_pela_api=True)):
                payload.append(
                    LogApiParticipanteEnvio(log=self.log_api, participante=participante, dados_envio=self.get_dados_parcipante(participante))
                )
            LogApiParticipanteEnvio.objects.bulk_create(payload)
        except Exception as e:
            erro = f'Erro ao gerar payload dos participantes:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    # PES
    # ===================================

    def get_manualmente_pes(self, pes, verbosity=False):
        # UTILIZADO APENAS PARA TESTES

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
        id_plano_entregas = str(pes.identificador_externo)

        url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_entregas/{id_plano_entregas}'

        return requests.get(url=url, headers=self.header, timeout=self.get_timeout(), verbosity=verbosity, API=self.api_externa.nome)

    def get_setor_siape_do_setor_suap(self, _sigla_setor, _uo_sigla_setor):
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

    def get_codigo_siape_setor_metodo1(self, setor):
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
        codigo_siape = self.get_setor_siape_do_setor_suap(setor.sigla, setor.uo.sigla)
        if codigo_siape:
            return codigo_siape

        # Se não tiver busca nos superiores
        setor = setor.superior
        while setor is not None:
            codigo_siape = self.get_setor_siape_do_setor_suap(setor.sigla, setor.uo.sigla)
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

    def get_codigo_siape_setor_metodo2(self, setor):
        """
        Obter código SIAPE direto do setor SIAPE (caso utilize árvore SIAPE)
        """
        return setor.codigo

    def get_codigo_siape_setor_metodo3(self, setor):
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

    def get_codigo_siape_setor(self, setor):
        metodo = get_metodo_obter_codigo_siape_setor()
        if metodo == 1:
            return self.get_codigo_siape_setor_metodo1(setor)
        if metodo == 2:
            return self.get_codigo_siape_setor_metodo2(setor)
        return self.get_codigo_siape_setor_metodo3(setor)

    def get_dados_api_grupo_pes(self, pes):
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

    def preparar_pess(self):
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
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def preparar_pess_identificadores(self):
        try:
            # ==========================================
            # Sabendo os setores que tem PES e para cada um deles saber o seu SIAPE
            # - Apenas para quem ainda nao tem identificador
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
                    cs = self.get_codigo_siape_setor(setor_pgd)
                    if cs:
                        lista_setores_pes_siape.append((setor_pgd.id, cs))
                    else:
                        erro = f'Erro ao gerar/atualizar identificadores dos PES relacionados a {setor_pgd}: não foi possível obter código SIAPE do setor'
                        LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)

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
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def gerar_payload_pes(self):
        try:
            # Apenas os que devem ser enviados
            pess_enviar = PlanoEntregasSetorial.get_pess_aprovados().filter(identificador_externo__isnull=False)
            pess_enviar = pess_enviar.filter(
                Q(data_hora_ultimo_envio_api__isnull=True)
                | (Q(data_hora_ultimo_envio_api__isnull=False) & Q(data_hora_ultima_alteracao_apos_aprovacao__gt=F('data_hora_ultimo_envio_api')))
            )

            pess_enviar = pess_enviar.order_by('identificador_externo').distinct('identificador_externo')

            payload = []
            for dado in tqdm.tqdm(pess_enviar):
                payload.append(LogApiPesEnvio(log=self.log_api, pes=dado, dados_envio=self.get_dados_api_grupo_pes(dado)))
            LogApiPesEnvio.objects.bulk_create(payload)

        except Exception as e:
            erro = f'Erro ao gerar paylod dos PESs: {e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    # PIT
    # ===================================

    def get_manualmente_pit(self, pit):
        # UTILIZADO APENAS PARA TESTES

        origem_unidade = 'SIAPE'
        cod_unidade_autorizadora = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
        id_plano_trabalho = pit.id

        url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'

        return requests.get(url=url, headers=self.header, timeout=self.get_timeout())

    def get_dados_api_pit(self, pit, com_entregas_e_avaliacao=True):
        dados = {}
        dados['origem_unidade'] = 'SIAPE'
        dados['cod_unidade_autorizadora'] = int(Configuracao.get_valor_por_chave('comum', 'instituicao_identificador'))
        dados['id_plano_trabalho'] = str(pit.id)
        dados['status'] = pit.get_situacao_api()
        dados['cod_unidade_executora'] = int(pit.get_cod_unidade_executora_para_api())
        dados['cpf_participante'] = pit.adesao.servidor.pessoa_fisica.cpf.replace('.', '').replace('-', '')
        dados['matricula_siape'] = pit.adesao.servidor.matricula.zfill(7)
        dados['cod_unidade_lotacao_participante'] = self.get_cod_unidade_lotacao_parcipante(pit)
        dados['data_inicio'] = str(pit.data_inicio)
        dados['data_termino'] = str(pit.data_fim)
        dados['carga_horaria_disponivel'] = int(pit.tempo_planejado_total)

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

            # Dados da avaliação do RIT
            # - O RIT é avaliado como um todo e não por cada entrega
            # - Por isso a avalia
            avaliacoes = []
            if pit.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT:
                dados_avaliacao = {}
                # Id do PitSolicitacaoAnaliseSetor relacionado a avaliação
                # - Se RIT foi reaberto (avaliados mais de uma vez) esse ID é o da solicitação
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

    def preparar_pits(self):
        try:
            self.pits_para_enviar = []

            # Nao envia nada dos PITs se teve algum erro no envio dos PESs
            # Interrompe envio
            if self.log_api.logapipesenvio_set.filter(status__in=[LogApiPesEnvio.STATUS_ERRO_ENVIO, LogApiPesEnvio.STATUS_PENDENTE_ENVIO]).exists():
                LogApiDetalhe.registrar(
                    log=self.log_api, url=self.get_url_api(), erro_envio='Não foi possível enviar os PITs por erros no envio dos PESs'
                )
                return False

            # PITs que deveriam ser enviados
            # - Em tese não é pra exsistir deve_enviar_pela_api=True que já não tenha sido homologado
            #   - Usamos PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez apenas para garantir isso
            pits_enviar = PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().filter(deve_enviar_pela_api=True)
            pits_enviar = pits_enviar.filter(situacao__in=[PlanoIndividualTrabalho.HOMOLOGADO, PlanoIndividualTrabalho.CANCELADO])

            # Obtem os participantes (servidores) que existem em ParticipantePgd e foram enviados (possui algum registro de envio)
            # Da lista de participantes obtem a lista de PITs que não serão enviados por nao terem participante enviado
            # Gera log com os PITs que não serão enviados por não terem participantye enviado
            ids_participantes_servidores_enviados = ParticipantePgd.objects.filter(data_hora_envio_api__isnull=False).values_list(
                'servidor_id', flat=True
            )
            pits_sem_participante = pits_enviar.exclude(adesao__servidor__id__in=ids_participantes_servidores_enviados)
            for pit_nao_enviar in tqdm.tqdm(pits_sem_participante):
                erro = f'Não foi possível enviar {pit_nao_enviar}: participante não foi enviado'
                LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            pits_sem_participante = pits_sem_participante.values_list('id', flat=True)

            # Obtem os PITs que nao tem setor ou pes que pode homologar
            pits_sem_pes_ou_setor_pode_homologar = self.get_pits_sem_pes_ou_setor_pode_homologar(pits_enviar)
            if pits_sem_pes_ou_setor_pode_homologar:
                for pne in pits_sem_pes_ou_setor_pode_homologar:
                    pne.pit.calcular_pit_setores_envolvidos()
                pits_sem_pes_ou_setor_pode_homologar = self.get_pits_sem_pes_ou_setor_pode_homologar(pits_enviar)
            for pit_nao_enviar in tqdm.tqdm(pits_sem_pes_ou_setor_pode_homologar):
                erro = f'Não foi possível enviar {pit_nao_enviar.pit}: não possui Setor para homologar ou não possui PES principal'
                LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            pits_sem_pes_ou_setor_pode_homologar = pits_sem_pes_ou_setor_pode_homologar.values_list('pit_id', flat=True)

            # Obtem os PITs que possui algum PES relacionado que ainda não foi enviado
            ids_pits_com_pess_nao_enviados, pits_sem_pes_enviado = self.get_pits_com_pess_nao_enviados(pits_enviar)
            if pits_sem_pes_enviado:
                for pspe in pits_sem_pes_enviado:
                    pspe.pit.calcular_pit_setores_envolvidos()
                ids_pits_com_pess_nao_enviados, pits_sem_pes_enviado = self.get_pits_com_pess_nao_enviados(pits_enviar)
            for pit_sem_pes_enviado in tqdm.tqdm(pits_sem_pes_enviado):
                erro = f'Não foi possível enviar {pit_sem_pes_enviado}: não possui PES relacionado enviado'
                LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)

            # Filtra os PITs que serão enviados
            ids_pits_nao_enviar = list(pits_sem_participante) + list(pits_sem_pes_ou_setor_pode_homologar) + list(ids_pits_com_pess_nao_enviados)
            pits_enviar = pits_enviar.exclude(id__in=ids_pits_nao_enviar)

            self.pits_para_enviar = pits_enviar

        except Exception as e:
            erro = f'Erro ao preparar os PITs que devem ser enviados:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def gerar_payload_pits(self):
        pit_atual = None

        try:
            pits = self.pits_para_enviar
            pits = pits.select_related('adesao', 'adesao__servidor', 'adesao__servidor__pessoa_fisica')
            pits = pits.order_by('adesao__servidor', 'data_inicio', 'id')

            payload = []
            if pits:
                for dado in tqdm.tqdm(pits):
                    pit_atual = dado
                    dados_envio = None

                    try:
                        dados_envio = self.get_dados_api_pit(dado)
                    except Exception as e:
                        erro = f'Erro ao gerar payload do PIT {pit_atual} #{pit_atual.id} Situação {pit_atual.get_situacao_display()}:\n{e}'
                        LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)

                    if dados_envio:
                        payload.append(LogApiPitEnvio(log=self.log_api, pit=dado, dados_envio=dados_envio))

                LogApiPitEnvio.objects.bulk_create(payload)
        except Exception as e:
            if pit_atual:
                erro = f'Erro ao gerar payload (interrompido) do PIT {pit_atual} #{pit_atual.id} Situação {pit_atual.get_situacao_display()}:\n{e}'
            else:
                erro = f'Erro ao gerar payload (interrompido) dos PITs:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    # ===================================
    # Envio dos dados
    # ===================================

    def enviar_pess(self):
        def enviar_dados(dados_enviar):
            origem_unidade = dados_enviar.get('origem_unidade')
            cod_unidade_autorizadora = dados_enviar.get('cod_unidade_autorizadora')
            id_plano_entregas = dados_enviar.get('id_plano_entregas')

            try:
                url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_entregas/{id_plano_entregas}'

                response = self.session.put(url=url, data=json.dumps(dados_enviar), headers=self.header, timeout=self.get_timeout())
                response.raise_for_status()

                return True, id_plano_entregas, None, None

            except HTTPError as e:
                erro = f'Erro ao enviar dados do PES {id_plano_entregas}: {e.response.status_code} - {e.response.text}'
                return False, id_plano_entregas, erro, dados_enviar
            except RequestException as e:
                erro = f'Erro ao enviar dados do PES {id_plano_entregas}: {e!s}'
                return False, id_plano_entregas, erro, dados_enviar
            except Exception as e:
                erro = f'Erro ao enviar dados do PES {id_plano_entregas}: {e!s}'
                return False, id_plano_entregas, erro, dados_enviar

        try:
            self.session = Session()

            self.session.headers.update(self.header)

            payload_pess = LogApiPesEnvio.objects.filter(log=self.log_api)
            self.log_api.qtd_envios_pes = payload_pess.count()
            self.log_api.save()

            if payload_pess:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_payload = {}

                    for payload in tqdm.tqdm(payload_pess.iterator(chunk_size=1000)):
                        future = executor.submit(enviar_dados, payload.dados_envio)
                        future_to_payload[future] = payload

                    for future in concurrent.futures.as_completed(future_to_payload):
                        retorno = future.result()
                        if retorno[0]:
                            PlanoEntregasSetorial.objects.filter(identificador_externo=retorno[1]).update(
                                data_hora_ultimo_envio_api=get_datetime_now()
                            )
                            LogApiPesEnvio.registrar_envio(log=self.log_api, identificador_externo=retorno[1])
                        else:
                            LogApiPesEnvio.registrar_envio(log=self.log_api, identificador_externo=retorno[1], erro_envio=retorno[2])

        except Exception as e:
            erro = f'Erro ao enviar dados dos PESs:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def enviar_participantes(self):
        def enviar_dados(dados_enviar):
            origem_unidade = dados_enviar.get('origem_unidade')
            cod_unidade_autorizadora = dados_enviar.get('cod_unidade_autorizadora')
            cod_unidade_lotacao = dados_enviar.get('cod_unidade_lotacao')
            matricula_siape = dados_enviar.get('matricula_siape')

            try:
                url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/{cod_unidade_lotacao}/participante/{matricula_siape}'

                response = self.session.put(url=url, data=json.dumps(dados_enviar), headers=self.header, timeout=self.get_timeout())
                response.raise_for_status()

                return True, int(matricula_siape), None, None

            except HTTPError as e:
                erro = f'Erro ao enviar dados do participante {matricula_siape}: {e.response.status_code} - {e.response.text}'
                return False, int(matricula_siape), erro, dados_enviar
            except RequestException as e:
                erro = f'Erro ao enviar dados do participante {matricula_siape}: {e!s}'
                return False, int(matricula_siape), erro, dados_enviar
            except Exception as e:
                erro = f'Erro ao enviar dados do participante {int(matricula_siape)}: {e!s}'
                return False, int(matricula_siape), erro, dados_enviar

        try:
            self.session = Session()

            self.session.headers.update(self.header)

            payload_participantes = LogApiParticipanteEnvio.objects.filter(log=self.log_api)
            self.log_api.qtd_envios_participante = payload_participantes.count()
            self.log_api.save()

            if payload_participantes:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_payload = {}

                    for payload in tqdm.tqdm(payload_participantes.iterator(chunk_size=1000)):
                        future = executor.submit(enviar_dados, payload.dados_envio)
                        future_to_payload[future] = payload

                    for future in concurrent.futures.as_completed(future_to_payload):
                        retorno = future.result()
                        if retorno[0]:
                            ParticipantePgd.objects.filter(servidor__matricula=retorno[1]).update(
                                data_hora_envio_api=get_datetime_now(), deve_enviar_pela_api=False
                            )
                            LogApiParticipanteEnvio.registrar_envio(log=self.log_api, matricula=retorno[1])
                        else:
                            LogApiParticipanteEnvio.registrar_envio(log=self.log_api, matricula=retorno[1], erro_envio=retorno[2])

        except Exception as e:
            erro = f'Erro ao enviar dados dos participantes:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def enviar_pits(self):
        def enviar_dados(dados_enviar):
            origem_unidade = dados_enviar.get('origem_unidade')
            cod_unidade_autorizadora = dados_enviar.get('cod_unidade_autorizadora')
            id_plano_trabalho = dados_enviar.get('id_plano_trabalho')

            try:
                url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'

                response = self.session.put(url=url, data=json.dumps(dados_enviar), headers=self.header, timeout=self.get_timeout())
                response.raise_for_status()

                return True, id_plano_trabalho, None, None

            except HTTPError as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e.response.status_code} - {e.response.text}'
                return False, id_plano_trabalho, erro, dados_enviar
            except RequestException as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e!s}'
                return False, id_plano_trabalho, erro, dados_enviar
            except Exception as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e!s}'
                return False, id_plano_trabalho, erro, dados_enviar

        try:
            self.session = Session()

            self.session.headers.update(self.header)

            payload_pits = LogApiPitEnvio.objects.filter(log=self.log_api)
            self.log_api.qtd_envios_pit = payload_pits.count()
            self.log_api.save()

            if payload_pits:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_payload = {}

                    for payload in tqdm.tqdm(payload_pits.iterator(chunk_size=1000)):
                        future = executor.submit(enviar_dados, payload.dados_envio)
                        future_to_payload[future] = payload

                    for future in concurrent.futures.as_completed(future_to_payload):
                        retorno = future.result()
                        if retorno[0]:
                            pit = PlanoIndividualTrabalho.objects.get(id=retorno[1])
                            pit.marcar_como_enviado_pela_api()
                            LogApiPitEnvio.registrar_envio(log=self.log_api, pit_id=retorno[1])
                        else:
                            LogApiPitEnvio.registrar_envio(log=self.log_api, pit_id=retorno[1], erro_envio=retorno[2])

        except Exception as e:
            erro = f'Erro ao enviar dados dos PITs:\n{e}'
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio=erro)
            return False

        return True

    def enviar_manualmente_pit(self, pit):
        # UTILIZADO APENAS PARA TESTES

        def enviar_dados(dados_enviar):
            origem_unidade = dados_enviar.get('origem_unidade')
            cod_unidade_autorizadora = dados_enviar.get('cod_unidade_autorizadora')
            id_plano_trabalho = dados_enviar.get('id_plano_trabalho')

            try:
                url = f'{self.get_url_api()}/organizacao/{origem_unidade}/{cod_unidade_autorizadora}/plano_trabalho/{id_plano_trabalho}'

                response = requests.put(url=url, data=json.dumps(dados_enviar), headers=self.header, timeout=self.get_timeout())
                response.raise_for_status()

                return True, id_plano_trabalho, None, None

            except HTTPError as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e.response.status_code} - {e.response.text}'
                return False, id_plano_trabalho, erro, dados_enviar
            except RequestException as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e!s}'
                return False, id_plano_trabalho, erro, dados_enviar
            except Exception as e:
                erro = f'Erro ao enviar dados do PITs {id_plano_trabalho}: {e!s}'
                return False, id_plano_trabalho, erro, dados_enviar

        dados_envio = self.get_dados_api_pit(pit)
        return enviar_dados(dados_envio)

    def enviar_dados_api(self, forcar_envio=False, self_command=None):
        def print_msg(msg):
            if self_command:
                self_command.stdout.write(msg)

        print_msg('============================')
        print_msg(' API PGD 2')
        print_msg('============================')

        pode_seguir = forcar_envio or self.deve_enviar_hoje()
        self.max_workers = get_max_workers()

        self.log_api = LogApi()
        self.log_api.data_hora_inicio = get_datetime_now()
        self.log_api.data_proximo_envio_por_sucesso = amanha()
        self.log_api.data_proximo_envio_por_erro = amanha()
        self.log_api.url = self.get_url_api()
        self.log_api.save()
        print_msg(f'>>> LogAPI PGD 2: {self.log_api} #{self.log_api.id}')

        if pode_seguir and not self.get_config_api():
            pode_seguir = False

        try:
            self.set_token()
            self.set_header()

            if not self.token_api_pgd2:
                pode_seguir = False

            # ====================================
            # PESs
            # ====================================

            if pode_seguir:
                print_msg('>>> Preparar dados dos PESs')
                retorno = self.preparar_pess()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Preparar dados dos PESs - Identificadores')
                retorno = self.preparar_pess_identificadores()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Preparar dados dos PESs - Payload')
                retorno = self.gerar_payload_pes()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Enviando dados dos PESs')
                retorno = self.enviar_pess()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            # ====================================
            # Participantes
            # ====================================
            if pode_seguir:
                print_msg('>>> Preparar dados dos Participantes ')
                retorno = self.preparar_participantes()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Preparar dados dos Participantes - Payload')
                retorno = self.gerar_payload_participantes()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Enviando dados dos Participantes ')
                retorno = self.enviar_participantes()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False
                print_msg('>>> Fim do envio dados dos Participantes')

            # ====================================
            # PITs
            # ====================================
            if pode_seguir:
                print_msg('>>> Preparar dados dos PITs ')
                retorno = self.preparar_pits()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Preparar dados dos PITs - Payload ')
                retorno = self.gerar_payload_pits()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False

            if pode_seguir:
                print_msg('>>> Enviando dados dos PITs ')
                retorno = self.enviar_pits()
                if not retorno:
                    self.log_api.data_hora_fim = get_datetime_now()
                    self.log_api.save()
                    pode_seguir = False
                print_msg('>>> Fim do envio dados dos PITs ')
        except Exception as e:
            LogApiDetalhe.registrar(log=self.log_api, url=self.get_url_api(), erro_envio={str(e)})

        self.log_api.qtd_envios_erros_pes = self.log_api.get_qtd_erros_envio_pes()
        self.log_api.qtd_envios_erros_participante = self.log_api.get_qtd_erros_envio_participante()
        self.log_api.qtd_envios_erros_pit = self.log_api.get_qtd_erros_envio_pits()
        self.log_api.data_hora_fim = get_datetime_now()
        self.log_api.save()

        print_msg('> Fim do procedimento da API')
