import json
import logging

from django.conf import settings
from django.core import signing
from django.db.models.query import QuerySet
from sentry_sdk import capture_exception

from catalogo_provedor_servico.models import Servico, Solicitacao, SolicitacaoEtapa
from catalogo_provedor_servico.utils import reload_choices
from comum.models import APIExterna
from djtools.utils import atomic
from rh.models import UnidadeOrganizacional

from .interfaces import ServiceProvider, ServiceProviderFactory

logger = logging.getLogger(__name__)


class ValidationException(Exception):
    pass


class TreatedException(Exception):
    pass


class GovBr_User_Info:
    """
    Informações disponíveis na estrutura retornada pelo *single sign on*.
    """

    CPF = 'GOVBR_CPF'  # :
    NOME = 'GOVBR_NOME'  # :
    FONE = 'GOVBR_FONE'  # :
    EMAIL = 'GOVBR_EMAIL'  # :


class Tse_User_Info:
    """
    Informações disponíveis pelo TSE.
    """

    TITULO = 'TSE_TITULO'  # :
    CPF = 'TSE_CPF'  # :
    NOME = 'TSE_NOME'  # :
    DATA_NASCIMENTO = 'TSE_DATA_NASCIMENTO'  # :
    TIPO_DOCUMENTO = 'TSE_TIPO_DOCUMENTO'  # :
    NUM_DOCUMENTO = 'TSE_NUM_DOCUMENTO'  # :
    ORG_EXPEDIDOR = 'TSE_ORG_EXPEDIDOR'  # :
    MAE = 'TSE_MAE'  # :
    PAI = 'TSE_PAI'  # :
    ENDERECO = 'TSE_ENDERECO'  # :
    NUMERO = 'TSE_NUMERO'  # :
    CEP = 'TSE_CEP'  # :
    COMPLEMENTO = 'TSE_COMPLEMENTO'  # :
    BAIRRO = 'TSE_BAIRRO'  # :
    CIDADE = 'TSE_CIDADE'  # :
    TELEFONE = 'TSE_TELEFONE'  # :
    UF = 'TSE_UF'  # :
    SEXO = 'TSE_SEXO'  # :
    MUNIC_NASCIMENTO = 'TSE_MUNIC_NASCIMENTO'  # :
    UF_NASCIMENTO = 'TSE_UF_NASCIMENTO'  # :


class Resposta:
    """
    Classe que mapeia as mensagens de resposta entre o provedor e o balcão de serviços.
    """

    def __init__(self, resposta=None, mensagem=None, has_error=False):
        self.resposta = resposta
        self.mensagem = mensagem
        self.has_error = has_error

    @classmethod
    def create_from_exception(cls, mensagem, exception):
        """
        Método que cria uma mensagem a partir de uma exceção.

        Args:
            mensagem (string): Mensagem da resposta.
            exception (Exception): Exceção que foi capturada.

        Returns:
            Resposta contendo as informações obtidas pela mensagem e a exception
        """
        mensagem += f' Detalhes: {exception}'
        resposta = cls(resposta=None, mensagem=mensagem, has_error=True)
        return resposta

    def json(self):
        """
        Método que retorna um dicionário com informações a serem enviadas ao balcão de serviços.

        Returns:
            dict com as informações da mensagem de resposta.
        """
        return {'resposta': self.resposta, 'mensagem': self.mensagem, 'has_error': self.has_error}


class AvaliacaoDisponibilidadeServico:
    def __init__(self, servico, cpf):
        self.servico = servico
        self.cpf = cpf
        self.criterios_sucesso = []
        self.criterios_erro = []

    def add_criterio(self, condicao_sucesso, msg_sucesso, msg_erro):
        if condicao_sucesso:
            self.add_criterio_sucesso(msg_sucesso)
        else:
            self.add_criterio_erro(msg_erro)

    def add_criterio_sucesso(self, msg):
        self.criterios_sucesso.append(msg)

    def add_criterio_erro(self, msg):
        self.criterios_erro.append(msg)

    @property
    def is_ok(self):
        return not self.criterios_erro

    def __str__(self):
        if self.__dict__:
            atts = ', '.join(['='.join([key, str(val)]) for key, val in self.__dict__.items()])
            return f'{self.__class__.__name__} ({atts})'
        return ''

    def __repr__(self):
        return self.__str__()


class AbstractBaseServiceProvider(ServiceProvider):
    """
    Classe abstrata base para criação de provedores de serviço.
    """

    def __new__(cls):
        self = super().__new__(cls)

        num_etapas = 0
        for name in cls.__dict__:
            if name.startswith('_get_etapa'):
                num_etapas += 1
        self.numero_etapas = num_etapas

        return self

    def get_numero_total_etapas(self):
        """
        Implementação do método que retorna o número total de etapas do serviço.

        Ver assinatura na interface *ServiceProvider*.
        """
        return self.numero_etapas

    def _get_next_etapa(self, cpf, etapa):
        """
        Método privado que retorna a próxima etapa a ser executada.

        Args:
            cpf (String): CPF do cidadão associado a solicitação.
            etapa (Etapa): Objeto da etapa a ser executada.

        Raises:
            Exception: Cado o método da etapa solicitada não exista.

        Returns:
            Formulario da etapa com os dados prestados pelo cidadão, caso seja uma edição.
        """
        if etapa.numero < self.get_numero_total_etapas():
            return getattr(self, f'_get_etapa_{etapa.numero + 1}')(cpf=cpf)
        return None

    def _get_solicitacao_etapa(self, cpf, numero_etapa):
        try:
            servico = Servico.objects.get(id_servico_portal_govbr=self.get_id_servico_portal_govbr())
            solicitacao = Solicitacao.objects.filter(servico=servico, cpf=cpf, status__in=Solicitacao.STATUS_QUE_PERMITEM_EDICAO_DADOS).first()
            if solicitacao:
                return SolicitacaoEtapa.objects.filter(solicitacao=solicitacao, numero_etapa=numero_etapa).first()
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)
            return None

    def _get_etapa_para_edicao(self, cpf, numero_etapa):
        """
        Método que obtem uma etapa do serviço atual para um cidadão.

        Args:
            cpf (String): CPF do cidadão associado a solicitação.
            numero_etapa (int): O número da etapa a retornar.

        Raises:
            Exception:

        Returns:
             A Etapa solicitada.
        """
        try:
            solicitacao_etapa = self._get_solicitacao_etapa(cpf, numero_etapa)
            if solicitacao_etapa:
                etapa = Etapa.load_from_json(solicitacao_etapa.get_dados_as_json())
                return etapa
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)
            return None

        return None

    def get_avaliacao_disponibilidade(self, cpf, verbose=False):
        """
        Implementação do método que verifica a disponibilidade do serviço.

        Ver assinatura na interface *ServiceProvider*.

        Example:
            Código utilizado para teste do método::

                from catalogo_provedor_servico.providers.base import *
                from catalogo_provedor_servico.providers.factory import *
                from catalogo_provedor_servico.models import *

                cpfs = (
                    ('108.795.654-46', 'Caso Hugo'),
                    ('115.902.124-44', 'Incompleto'),
                    ('011.692.834-46', 'Em Analise'),
                    ('701.221.354-07', 'Aguardando Correção'),
                    ('107.354.624-10', 'Dados Corrigidos'),
                    ('708.338.824-57', 'Atendido'),
                    ('706.511.634-47', 'Não Atendido'),
                    ('070.003.044-13', 'Ausente'),
                    ('039.749.154-94', 'De Hugo'),
                )
                for cpf, tipo in cpfs:
                    print('-' * 60)
                    print(f'CPF = {cpf}; Tipo = {tipo}')
                    servicos = service_provider_factory().get_servicos_disponiveis(cpf)
                    print('*' * 60)
        """
        servico = Servico.objects.get(id_servico_portal_govbr=self.get_id_servico_portal_govbr())
        avaliacao = AvaliacaoDisponibilidadeServico(servico, cpf)
        self._do_avaliacao_disponibilidade_basica(cpf=cpf, servico=servico, avaliacao=avaliacao)
        self._do_avaliacao_disponibilidade_especifica(cpf=cpf, servico=servico, avaliacao=avaliacao)

        # TODO: Botar uma rotina de log de verdade.
        if verbose:
            logger.info('')
            logger.info('Avaliacao de disponibilidade: ')
            logger.info(f'- Servico: {servico}')
            logger.info(f'- CPF: {cpf}')
            logger.info('- Disponivel para o cidadao: {}'.format('Sim' if avaliacao.is_ok else 'Nao'))
            logger.info(f'- Detalhes: {avaliacao}')
            logger.info('')
        return avaliacao

    def _do_avaliacao_disponibilidade_basica(self, cpf, servico, avaliacao):
        """
        Método privado que realiza a avaliação básica de serviços na verificação de disponibilidade.

        Args:
            cpf (String): CPF do cidadão associado a solicitação.
            servico (): Serviço a verificar a disponibilidade
            avaliacao ():
        """
        if not servico.id_servico_portal_govbr > 0:
            avaliacao.add_criterio(
                servico.id_servico_portal_govbr > 0, 'Serviço com identificador GOV.BR cadastrado.', 'Serviço sem identificador GOV.BR cadastrado.'
            )
            return

        avaliacao.add_criterio(servico.ativo, 'Serviço ativo.', 'Serviço inativo.')
        solicitacoes_em_aberto = Solicitacao.objects.filter(cpf=cpf, servico=servico).exclude(
            status__in=Solicitacao.STATUS_QUE_PERMITEM_HABILITACAO_SERVICO
        )
        avaliacao.add_criterio(not solicitacoes_em_aberto.exists(), 'Não há solicitações em aberto.', 'Existem solicitações em aberto.')

    def _do_avaliacao_disponibilidade_especifica(self, cpf, servico, avaliacao):
        """
        Método privado que realiza as avaliações, de disponibilidade, específicas do serviço.

        Args:
            cpf (String): CPF do cidadão associado a solicitação.
            servico (): Serviço a verificar a disponibilidade
            avaliacao ():
        """

    def _validate_dados_etapa(self, request, etapa, solicitacao):
        """
        Método privado que realiza validação dos dados de uma etapa.

        Args:
            request (HttpRequest): Objeto request da sessão.
            etapa (Etapa): Etapa a ser validada.
            solicitacao (): Solicitação que contem o formulário com os dados do cidadão.
            avaliacao ():

        Returns:
            Lita com erros. Caso não haja erros, será uma lista vazia.
        """
        return []

    def _on_persist_solicitacao(self, solicitacao, is_create, is_update):
        """
        Método privado que é invocado pelo provedor no ato de persistencia de uma solicitação.

        Args:
            solicitacao (Solicitacao): Solicitacao que foi persistida.
            is_create (bool): Indica que a incocação foi proveniente da criação de uma solicitação.
            is_update (bool): Indica que a incocação foi proveniente da atualização de uma solicitação.
        """

    def _on_persist_solicitacao_etapa(self, etapa, solicitacao_etapa, is_create, is_update):
        """
        Método privado que é invocado pelo provedor no ato de persistencia de uma etapa de uma solicitação.

        Args:
            etapa (Etapa): Etapa que originou a persistência.
            solicitacao_etapa (SolicitacaoEtapa): Etapa que está sendo persistida.
            is_create (bool): Indica que a incocação foi proveniente da criação de uma etapa de solicitação.
            is_update (bool): Indica que a incocação foi proveniente da atualização de uma etapa de solicitação.
        """

    def _on_before_finish_recebimento_solicitacao(self, request, solicitacao):
        """
        Método privado que é invocado antes da solicitação ser recebida.

        Args:
            solicitacao (Solicitacao): solicitação a ser recebida.
        """

    def _on_after_finish_recebimento_solicitacao(self, request, solicitacao):
        """
        Método privado que é invocado após o recebimento da solicitação.

        Args:
            solicitacao (Solicitacao): solicitação que foi recebida.
        """

    def pode_retornar_para_analise(self, request, solicitacao):
        """
        Método privado que é invocado antes de tentar retornar uma solicitação indeferida para em análise.

        Args:
            request (HttpRequest): request para obter o usuário que solicitou.
            solicitacao (Solicitacao): solicitação que foi recebida.
        """
        if not solicitacao.has_status_permite_retornar_para_analise():
            return False, 'Status inválido.'

        if not self.is_em_periodo_avaliacao(solicitacao=solicitacao, campus=solicitacao.uo):
            return False, 'Solicitação não mais em período de avaliação.'

        campus_usuario_atende = UnidadeOrganizacional.objects.filter(
            pk__in=solicitacao.servico.servicoequipe_set.filter(vinculo=request.user.get_vinculo()).values_list('campus_id', flat=True)
        )
        campus_usuario_gerencia = UnidadeOrganizacional.objects.filter(
            pk__in=solicitacao.servico.servicogerenteequipelocal_set.filter(vinculo=request.user.get_vinculo()).values_list('campus_id', flat=True)
        )

        pf_atende_uo_da_solicitacao = solicitacao.uo in campus_usuario_atende
        pf_eh_gerente_avaliacao_da_uo = solicitacao.uo in campus_usuario_gerencia

        if not (pf_atende_uo_da_solicitacao or pf_eh_gerente_avaliacao_da_uo):
            return False, 'Você não tem permissão para isso.'
        return True, ''

    def _do_pre_avaliacao_solicitacao(self, solicitacao):
        """
        Método privado que é invocado quando uma solicitação finalizou e
        está prestes a ser avaliada.

        Esta função irá pré-avaliar todos os campos opcionais que foram preenchidos
        com vazio com o status OK.

        Args:
            solicitacao (Solicitacao): solicitação que foi finalizada.
        """

        solicitacoes_etapa = SolicitacaoEtapa.objects.filter(solicitacao=solicitacao)
        for se in solicitacoes_etapa:
            etapa = self._get_etapa_para_edicao(cpf=solicitacao.cpf, numero_etapa=se.numero_etapa)
            for campo in etapa.formulario.campos:
                if not campo['required'] and not campo['value'] and not campo.get('value_hash_sha512_link_id'):
                    etapa.formulario.set_avaliacao(name=campo['name'], status='OK')
            SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa, solicitacao=solicitacao)

    def receber_solicitacao(self, request, cpf):
        """
        Implementação do método que recebe os dados enviados pelos cidadãos.

        Ver assinatura na interface *ServiceProvider*.
        """
        if request.method == 'GET':
            etapa = self._get_etapa_1(cpf=cpf)
            resposta = Resposta(resposta=etapa.json())
            return 200, resposta.json()

        if request.method == 'POST':
            etapa_atual = Etapa.load_from_json(json=request.data)

            try:
                with atomic(f'receber_solicitacao_lock:{cpf}', timeout=60):
                    servico = Servico.objects.get(id_servico_portal_govbr=self.get_id_servico_portal_govbr())
                    retorno = {'situacao': Solicitacao.STATUS_INCOMPLETO, 'mensagem': 'Solicitação Incompleto.'}
                    solicitacao_qs = Solicitacao.objects.filter(
                        servico=servico,
                        cpf=cpf,
                        numero_total_etapas=self.get_numero_total_etapas(),
                        status__in=Solicitacao.STATUS_QUE_PERMITEM_EDICAO_DADOS,
                    ).order_by('-data_ultima_atualizacao', '-pk')
                    solicitacao = solicitacao_qs.first()
                    solicitacao_criada = False
                    if solicitacao is None:
                        solicitacao = Solicitacao.objects.create(
                            servico=servico,
                            cpf=cpf,
                            numero_total_etapas=self.get_numero_total_etapas(),
                            status=Solicitacao.STATUS_INCOMPLETO,
                            status_detalhamento='Solicitação Incompleto.',
                        )
                        solicitacao_criada = True
                    self._on_persist_solicitacao(solicitacao=solicitacao, is_create=solicitacao_criada, is_update=not solicitacao_criada)

                    # Faz o tratamento dos campos extras
                    solicitacao.atualizar_extra_campo(etapa=etapa_atual)

                    has_errors = self._validate_dados_etapa(request=request, etapa=etapa_atual, solicitacao=solicitacao)

                    if has_errors:
                        raise ValidationException(has_errors)

                    try:
                        solicitacao_etapa, solicitacao_etapa_criada = SolicitacaoEtapa.update_or_create_from_etapa(
                            etapa=etapa_atual, solicitacao=solicitacao
                        )
                        self._on_persist_solicitacao_etapa(etapa_atual, solicitacao_etapa, solicitacao_etapa_criada, not solicitacao_etapa_criada)
                    except Exception as e:
                        raise TreatedException(f'Erro ao salvar a solicitação. Detalhes: {e}')

                    if etapa_atual.numero < self.get_numero_total_etapas():
                        try:
                            etapa = self._get_next_etapa(cpf=cpf, etapa=etapa_atual)
                            resposta = Resposta(resposta=etapa.json())
                            return 201, resposta.json()
                        except ConnectionError as e:
                            raise ValidationException(f'Erro de conexão. Aguarde alguns minutos e tente novamente. Detalhes: {e}')
                        except Exception as e:
                            if settings.DEBUG:
                                raise e
                            raise ValidationException(f'Erro ao gerar a próxima etapa. Detalhes: {e}')

                    if etapa_atual.numero == self.get_numero_total_etapas():
                        # Mantenha este método aqui, pois o status da solicitação vai influenciar no método "get_etapa_para_edicao",
                        # que por sua vez é normalmente usado dentro do "on_finish_recebimento_solicitacao".
                        # Obs: Uma alternativa seria criar um método get_etapa, que retornaria a etapa mesmo a solicitação não
                        # estando com um status "STATUS_QUE_PERMITEM_EDICAO_DADOS". Mas isso é bom ser feito com calma!
                        try:
                            self._on_before_finish_recebimento_solicitacao(request, solicitacao)
                        except ValidationException as e:
                            raise ValidationException(f'Erro ao finalizar a solicitação. Detalhes: {e}')
                        except Exception as e:
                            raise TreatedException(f'Erro ao finalizar a solicitação. Detalhes: {e}')

                        self._do_pre_avaliacao_solicitacao(solicitacao)

                        if solicitacao.status == Solicitacao.STATUS_AGUARDANDO_CORRECAO_DE_DADOS:
                            solicitacao.status = Solicitacao.STATUS_DADOS_CORRIGIDOS
                            solicitacao.status_detalhamento = 'Os dados foram corrigidos com sucesso. Uma nova análise será realizada.'
                        else:
                            solicitacao.status = Solicitacao.STATUS_EM_ANALISE
                            solicitacao.status_detalhamento = 'Dados enviados com sucesso. A sua solicitação está aguardando análise.'
                        solicitacao.save()
                        self._on_after_finish_recebimento_solicitacao(request, solicitacao)
                        self.registrar_acompanhamento(solicitacao)
                        retorno = {'situacao': solicitacao.status, 'mensagem': solicitacao.status_detalhamento}

                    if solicitacao.status == Solicitacao.STATUS_ATENDIDO:
                        self.registrar_conclusao(solicitacao)

                    resposta = Resposta(resposta=retorno)
                    return 201, resposta.json()
            except ValidationException as e:
                errors = {'errors': e.args}
                resposta = Resposta(resposta=errors)
                return 400, resposta.json()
            except TreatedException as e:
                errors = {'errors': [str(e)]}
                resposta = Resposta(resposta=errors)
                capture_exception(e)
                if settings.DEBUG:
                    raise e
                return 400, resposta.json()
            except Exception as e:
                errors = {'errors': [f'Erro ao salvar a solicitação. Detalhes: {e}']}
                resposta = Resposta(resposta=errors)
                capture_exception(e)
                if settings.DEBUG:
                    raise e
                return 400, resposta.json()

        raise Exception('Erro inesperado.')

    def registrar_acompanhamento(self, solicitacao=None, registro=None):
        """
        Implementação do método que registra um acompanhamento a uma solicitação.

        Ver assinatura na interface *ServiceProvider*.
        """
        api = APIExterna.ACOMPANHAMENTO_GOVBR
        if not api.ativo:
            return
        api.get_service().registrar_acompanhamento_servico(solicitacao=solicitacao, registro=registro)

    def registrar_conclusao(self, solicitacao=None, registro=None):
        """
        Implementação do método que registra a conclusão de uma solicitação.

        Ver assinatura na interface *ServiceProvider*.
        """
        api = APIExterna.ACOMPANHAMENTO_GOVBR
        if not api.ativo:
            return
        api.get_service().registrar_conclusao_servico(solicitacao=solicitacao, registro=registro)

    def registrar_reabertura(self, solicitacao=None, registro=None):
        """
        Implementação do método que registra a reabertura de uma solicitação.

        Ver assinatura na interface *ServiceProvider*.
        """
        api = APIExterna.ACOMPANHAMENTO_GOVBR
        if not api.ativo:
            return
        api.get_service().registrar_reabertura_servico(solicitacao=solicitacao, registro=registro)

    def obter_formulario_avaliacao(self, solicitacao):
        """
        Implementação do método que obtem o formulário de avaliação junto ao *gov.br*.

        Ver assinatura na interface *ServiceProvider*.
        """
        api = APIExterna.AVALIACAO_GOVBR
        if not api.ativo:
            return
        api.get_service().obter_link_formulario_avaliacao(solicitacao=solicitacao)


class AbstractBaseServiceProviderFactory(ServiceProviderFactory):
    """
    Classe abstrata base para criação de fábricas de provedores de serviços. As fábricas concretas seguirão essa
    implementação.
    """

    def get_avaliacoes_disponibilidade_servicos(self, cpf, id_servico_portal_govbr=None, avaliar_somente_servicos_ativos=False):
        """
        Implementação do método que avalia a disponibilidade de serviços.

        Ver assinatura na interface *ServiceProviderFactory*.
        """
        avaliacoes_disponibilidade_servicos = []

        servicos = Servico.objects.all()
        if avaliar_somente_servicos_ativos:
            servicos = servicos.filter(ativo=True)
        if id_servico_portal_govbr:
            servicos = servicos.filter(id_servico_portal_govbr=id_servico_portal_govbr)
        for servico in servicos:
            service_provider = self.get_service_provider(servico.id_servico_portal_govbr)
            if service_provider:
                avaliacoes_disponibilidade_servicos.append(service_provider.get_avaliacao_disponibilidade(cpf))
            else:
                avaliacao = AvaliacaoDisponibilidadeServico(servico, cpf)
                avaliacao.add_criterio(servico.ativo, 'Serviço ativo.', 'Serviço inativo.')
                avaliacoes_disponibilidade_servicos.append(avaliacao)

        return avaliacoes_disponibilidade_servicos

    def get_servicos_disponiveis(self, cpf, id_servico_portal_govbr=None):
        """
        Implementação do método que verifica se um serviço está disponível.

        Ver assinatura na interface *ServiceProviderFactory*.
        """
        avaliacoes_disponibilidade_servicos = self.get_avaliacoes_disponibilidade_servicos(
            cpf=cpf, id_servico_portal_govbr=id_servico_portal_govbr, avaliar_somente_servicos_ativos=True
        )
        servicos_disponiveis = []
        for avaliacao_disponibilidade_servico in avaliacoes_disponibilidade_servicos:
            if avaliacao_disponibilidade_servico.is_ok:
                servicos_disponiveis.append(avaliacao_disponibilidade_servico.servico)
        return servicos_disponiveis

    def get_servicos_ativos(self, id_servico_portal_govbr=None):
        """
        Implementação do método que retorna os serviços ativos.

        Ver assinatura na interface *ServiceProviderFactory*.
        """
        servicos = Servico.objects.filter(ativo=True)
        if id_servico_portal_govbr:
            servicos = servicos.filter(id_servico_portal_govbr=id_servico_portal_govbr)
        return list(servicos)


class Fieldset:
    def __init__(self):
        self.agrupamentos = []

    def add(self, name, fields):
        self.agrupamentos.append({'name': name, 'fields': fields})
        return self


class Formulario:
    def __init__(self):
        # List of dicts
        self.campos = []

    def _new_basic_campo(self, type, label, name, value, required=True, read_only=False, help_text=None):
        result = {'type': type, 'label': label, 'name': name, 'value': value, 'required': required}
        # Acrescentando o atributo read_only somente se necessário.
        if read_only:
            result['read_only'] = read_only
        # Acrescentando o atributo help_text somente se necessário.
        if help_text:
            result['help_text'] = help_text
        return result

    def _add_campo(self, campo):
        self.campos.append(campo)
        campo['avaliacao_status'] = None
        campo['avaliacao_status_msg'] = None
        return self

    def set_avaliacao(self, name, status, status_msg=None):
        for i, campo in enumerate(self.campos):
            if campo['name'] == name:
                self.campos[i]['avaliacao_status'] = status
                self.campos[i]['avaliacao_status_msg'] = status_msg

    def add_date(self, label, name, value, required=True, read_only=False, mask=None, help_text=None):
        campo = self._new_basic_campo('date', label, name, value, required, read_only, help_text)
        campo['mask'] = mask
        return self._add_campo(campo)

    def add_boolean(self, label, name, value, required=True, read_only=False, help_text=None):
        campo = self._new_basic_campo('boolean', label, name, value, required, read_only, help_text)
        return self._add_campo(campo)

    def add_string(
        self,
        label,
        name,
        value,
        balcaodigital_user_info=None,
        required=True,
        read_only=False,
        mask=None,
        mask_parameters=None,
        max_length=255,
        min_length=0,
        widget='textinput',
        help_text=None,
    ):
        if value and not isinstance(value, str):
            raise Exception('Campos do tipo string exigem um texto simples. Campo "{name}"')
        campo = self._new_basic_campo('string', label, name, value, required, read_only, help_text)
        campo['max_length'] = max_length
        campo['min_length'] = min_length
        campo['mask'] = mask
        campo['mask_parameters'] = mask_parameters
        campo['balcaodigital_user_info'] = balcaodigital_user_info
        campo['widget'] = widget
        return self._add_campo(campo)

    def add_integer(self, label, name, value, required=True, read_only=False, min_value=None, max_value=None, help_text=None):
        if value and not isinstance(value, str) and not int(value):
            raise Exception('Campos do tipo integer exigem um número simples. Campo "{name}"')
        campo = self._new_basic_campo('integer', label, name, value, required, read_only, help_text)
        campo['min_value'] = min_value
        campo['max_value'] = max_value
        return self._add_campo(campo)

    def add_choices(self, label, name, value, choices, required=True, read_only=False, filters=None, help_text=None):
        if filters is None:
            result = choices()
        else:
            result = choices(filters)
        if result and not (isinstance(result, dict | QuerySet)):
            raise Exception(f'Campos do tipo choices exigem um dicionário ou um QuerySet. Campo "{name}"')

        campo = self._new_basic_campo('choices', label, name, value, required, read_only, help_text)
        campo['choices_resource_id'] = signing.dumps(choices.__qualname__)
        campo['filters'] = json.dumps(filters)
        if isinstance(result, QuerySet):
            campo['lazy'] = True
        return self._add_campo(campo)

    def add_file(
        self,
        label,
        name,
        value,
        label_to_file,
        limit_size_in_bytes=2 * settings.BYTES_SIZE_1MB,
        allowed_extensions=settings.DEFAULT_UPLOAD_ALLOWED_DOCUMENT_EXTENSIONS + settings.DEFAULT_UPLOAD_ALLOWED_IMAGE_EXTENSIONS,
        value_hash_sha512_link_id=None,
        value_hash_sha512=None,
        value_content_type=None,
        value_original_name=None,
        value_size_in_bytes=None,
        value_charset=None,
        value_md5_hash=None,
        required=True,
        read_only=False,
        help_text=None,
    ):
        campo = self._new_basic_campo('file', label, name, value, required, read_only, help_text)
        campo['label_to_file'] = label_to_file
        campo['limit_size_in_bytes'] = limit_size_in_bytes
        campo['allowed_extensions'] = allowed_extensions
        campo['value_hash_sha512_link_id'] = value_hash_sha512_link_id
        campo['value_hash_sha512'] = value_hash_sha512
        campo['value_content_type'] = value_content_type
        campo['value_original_name'] = value_original_name
        campo['value_size_in_bytes'] = value_size_in_bytes
        campo['value_md5_hash'] = value_md5_hash
        campo['value_charset'] = value_charset
        return self._add_campo(campo)

    def set_required(self, name, required):
        for c in self.campos:
            if c.get('name', '') == name:
                c['required'] = required

    def set_value(self, name, value):
        for c in self.campos:
            if c.get('name', '') == name:
                c['value'] = value

    def get_value(self, name):
        for c in self.campos:
            if c.get('name', '') == name:
                return c.get('value')

    def get_display_value(self, name):
        for c in self.campos:
            if c.get('name', '') == name:
                return c.get('display_value') or c.get('value')

    def get_label(self, name):
        for c in self.campos:
            if c.get('name', '') == name:
                return c.get('label')

    def get_field(self, name):
        for c in self.campos:
            if c.get('name', '') == name:
                return c

    def get_campos_by_type(self, type, has_value=None):
        result = []
        for c in self.campos:
            if c.get('type') == type:
                value = c.get('value')
                if has_value is None or (has_value and value) or (not has_value and not value):
                    result.append(c)
        return result

    def get_campos_file(self, has_value=None):
        return self.get_campos_by_type('file', has_value)

    def get_campos_by_status(self, status):
        result = []
        for c in self.campos:
            if c.get('avaliacao_status') == status:
                result.append(c)
        return result


class Etapa:
    """
    Classe que representa uma etapa da solicitação realizada pelo cidadão.

    """

    def __init__(self, numero, total_etapas, nome):
        self.numero = numero
        self.total_etapas = total_etapas
        self.nome = nome
        self.formulario = Formulario()
        self.fieldsets = Fieldset()

    @classmethod
    def load_from_json(cls, json):
        """
        Método de classe que monta uma etapa a partir de um **JSON**.

        Args:
            json (string): string contendo as informações da etapa codificadas no formato **JSON**.

        Returns:
            Etapa com os dados contidos no **JSON**.
        """
        new_instance = Etapa(numero=json['etapa_atual'], total_etapas=json['total_etapas'], nome=json['nome'])
        new_instance.formulario.campos = json['formulario']
        new_instance.fieldsets.agrupamentos = json['fieldsets']
        new_instance.formulario.campos = reload_choices(new_instance.formulario.campos)
        return new_instance

    def json(self):
        """
        Método que retorna os dados a serem codificados no formato JSON.

        Returns:
            dict contendo as informações a serem codificadas.
        """
        etapa = {
            'etapa_atual': self.numero,
            'total_etapas': self.total_etapas,
            'nome': self.nome,
            'formulario': reload_choices(self.formulario.campos),
            'fieldsets': self.fieldsets.agrupamentos,
        }
        return etapa

    def json_dumps(self, indent=None):
        """
        Método que utiliza o método *self.json* e codifica no formato **JSON**.

        Args:
            indent (int): quantidade espaços em branco utilizados na identação do **JSON**.

        Returns:
            String codificada no padrão **JSON**.
        """
        return json.dumps(self.json(), indent=indent)


class Mask:
    """
    Contém máscaras de dados do plugin *https://igorescobar.github.io/jQuery-Mask-Plugin/docs.html* utilizado pelo catálogo digital"
    """

    NUMBER = '0#'
    DATE = '00/00/0000'  # :
    TIME = '00:00:00'  # :
    DATETIME = '00/00/0000 00:00:00'  # :
    CEP = '00000-000'  # :
    TELEFONE = '00telefone00'  # :
    CPF = '000.000.000-00'  # :
    CNPJ = '00.000.000/0000-00'  # :
    MONEY = '00money00'  # :
    MONEY2 = '00money200'  # :
    IP_ADDRESS = '099.099.099.099'  # :
    PERCENT = '00percent00'  # :
