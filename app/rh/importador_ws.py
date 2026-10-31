"""
__author__ = "Fernando Lopes"
__institute__ = "IFRN"
__version__ = "0.0.1"
"""

import logging
import re
import ssl
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from urllib.error import URLError

from django.apps.registry import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from suds import WebFault
from suds.client import Client
from suds.transport import TransportError

from comum.services import APIExternaService
from djtools.utils import format_telefone, mask_cpf, normalizar_nome_proprio, requests
from rh.deduplicacao.documentos import cpf_valido
from rh.deduplicacao.entrada import Politica
from rh.utils import base_matricula, extrai_matricula

logger = logging.getLogger(__name__)

Ferias = apps.get_model('ferias', 'Ferias') if 'ferias' in settings.INSTALLED_APPS else None
ParcelaFerias = apps.get_model('ferias', 'ParcelaFerias') if 'ferias' in settings.INSTALLED_APPS else None
Situacao = apps.get_model('rh', 'Situacao')
RegimeJuridico = apps.get_model('rh', 'RegimeJuridico')
Banco = apps.get_model('rh', 'Banco')
Servidor = apps.get_model('rh', 'Servidor')
Atividade = apps.get_model('rh', 'Atividade')
CargoClasse = apps.get_model('rh', 'CargoClasse')
Funcao = apps.get_model('rh', 'Funcao')
Deficiencia = apps.get_model('rh', 'Deficiencia')
Setor = apps.get_model('rh', 'Setor')
JornadaTrabalho = apps.get_model('rh', 'JornadaTrabalho')
Ocorrencia = apps.get_model('rh', 'Ocorrencia')
SubgrupoOcorrencia = apps.get_model('rh', 'SubgrupoOcorrencia')
ServidorOcorrencia = apps.get_model('rh', 'ServidorOcorrencia')
CargoEmprego = apps.get_model('rh', 'CargoEmprego')
NivelEscolaridade = apps.get_model('rh', 'NivelEscolaridade')
Titulacao = apps.get_model('rh', 'Titulacao')
ServidorFuncaoHistorico = apps.get_model('rh', 'ServidorFuncaoHistorico')
AfastamentoSiape = apps.get_model('rh', 'AfastamentoSiape')
ServidorAfastamento = apps.get_model('rh', 'ServidorAfastamento')
ServidorSetorHistorico = apps.get_model('rh', 'ServidorSetorHistorico')
EstadoCivil = apps.get_model('comum', 'EstadoCivil')
Municipio = apps.get_model('comum', 'Municipio')
Raca = apps.get_model('comum', 'Raca')
Pais = apps.get_model('comum', 'Pais')
Ano = apps.get_model('comum', 'Ano')
PessoaEndereco = apps.get_model('comum', 'PessoaEndereco')
PessoaTelefone = apps.get_model('comum', 'PessoaTelefone')
ExcecaoDado = apps.get_model('rh', 'ExcecaoDado')
Vinculo = apps.get_model('comum', 'Vinculo')
APIExterna = apps.get_model('comum', 'APIExterna')
ModalidadePGD = apps.get_model('rh', 'ModalidadePGD')
GrauParentesco = apps.get_model('comum', 'GrauParentesco')
Beneficio = apps.get_model('comum', 'Beneficio')
BeneficioDependente = apps.get_model('comum', 'BeneficioDependente')
Dependente = apps.get_model('comum', 'Dependente')
PrestadorServico = apps.get_model('comum', 'PrestadorServico')
PessoaFisica = apps.get_model('rh', 'PessoaFisica')

TipoExtracao = __import__('rh.enums', fromlist=['TipoExtracao']).TipoExtracao

"""
De modo geral, toda operação é composta pelos seguintes parâmetros de entrada:

    siglaSistema: É a sigla do sistema informada durante seu cadastramento. (estático)
    nomeSistema: É o nome do sistema informado durante seu cadastramento. (estático)
    senha: É a senha de acesso gerada após o cadastramento e enviada ao endereço eletrônico (e-mail) do responsável pelo sistema. (estático)
    cpf: O conteúdo deste parâmetro refere-se ao CPF do qual deseja-se obter as informações da consulta codOrgao: Este parâmetro é opcional. Recebe o código do órgão referente ao vínculo de onde deseja-se consultar as informações, para o CPF informado
    parmExistPag: Recebe os valores “a” ou “b”, conforme permissões. concedidas durante o cadastramento.
        a - Somente os vínculos ativos para pagamento na data atual (sem ocorrência de exclusão);
        b - Todos os vínculos existentes no sistema para o CPF, independentes de estarem recebendo pagamento (com ou sem ocorrência de exclusão)

    ParmTipoVinculo: Recebe os valores “a”, “b” ou “c”, conforme permissões concedidas durante o cadastramento.
        a - Somente os vínculos de servidores em exercício (servidores com PCA-exercício interno ou PFU vigentes ou com vínculos sem cargo e sem função). Não entram nestes casos aposentados, pensionistas, cedidos ou em exercício externo ao órgão de lotação.
        b - Somente os vínculos que se referem diretamente ao servidor (todos os vínculos do item a + aposentadorias + cedidos ou em exercício externo ao órgão de lotação)
        c - Todos os vínculos de recebimento do servidor (todos os vínculos do item b + pensões recebidas).
"""

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context


def get_siape_wsdl():
    return {
        'consultaDadosFinanceiros': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosSICAJ': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'getPensionista': [
            'cpfPensionista',
            'cpf',
            'siglaSistema',
            'nomeSistema',
            'senha',
        ],
        'consultaDadosEnderecoResidencial': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosAfastamento': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosCurriculo': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'listaContribuicoesPSS': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'codOrgao',
            'matricula',
            'codOrgaoTCU',
            'cpf',
            'anoInicial',
            'anoFinal',
        ],
        'consultaTotalizadorVagasOrgao': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
        ],
        'listaUpags': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'codUpag',
        ],
        'dadosUorg': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'codUorg',
        ],
        'consultaDadosPessoais': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosFinanceirosHistorico': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
            'anoInicial',
            'anoFinal',
        ],
        'consultaDadosDDP': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'anoMes',
            'codOrgao',
            'nivelSituacaoFuncional',
            'codigoFolhaDDP',
            'tipoConsulta',
            'classificacaoContabil',
        ],
        'consultaDadosDocumentacao': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'listaServidores': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'codUorg',
        ],
        'consultaDadosFuncionais': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'listaInformacoesAposentadoria': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'orgao',
            'matricula',
        ],
        'consultaDadosEscolares': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosBancarios': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosRepresentanteLegal': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'listaServidoresAutorizacaoIRPF': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'data',
        ],
        'consultaDadosUorg': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'verificaVinculo': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosDependentes': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaDadosPA': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'listaUorgs': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'codUorg',
        ],
        'consultaDadosAfastamentoHistorico': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
            'anoInicial',
            'mesInicial',
            'anoFinal',
            'mesFinal',
        ],
        'verificaVinculoEmpresas': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'consultaPensaoRecebida': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
        'obterVersao': [
            'siglaSistema',
        ],
        'consultaHistoricoPCA': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codigoOrgao',
        ],
        'consultaPensoesInstituidas': [
            'siglaSistema',
            'nomeSistema',
            'senha',
            'cpf',
            'codOrgao',
            'parmExistPag',
            'parmTipoVinculo',
        ],
    }


def aplicar_codigo_orgao(params: dict, nome_parametros: Iterable[str], codigo_orgao: str) -> None:
    """Preenche o parâmetro de órgão com o nome que a operação espera.

    `consultaHistoricoPCA` é a única operação do WSDL que chama esse parâmetro de
    `codigoOrgao`; todas as demais usam `codOrgao`. Decidir pelo WSDL — e não pelo
    que por acaso veio em `params` — conserta dois defeitos: a tela de consulta
    manual mandava `codOrgao` para o PCA e estourava `KeyError: 'codigoOrgao'`, e um
    órgão informado pelo chamador era sobrescrito pelo do cadastro.

    O valor do chamador tem precedência: é assim que se consulta o PCA no órgão de
    origem de um servidor cedido, cujo cargo não pertence à instituição.

    Args:
        params: Parâmetros da chamada; alterado no lugar.
        nome_parametros: Nomes que a operação declara, na ordem do WSDL.
        codigo_orgao: Órgão do cadastro da API externa, usado como padrão.
    """
    chave = 'codigoOrgao' if 'codigoOrgao' in (nome_parametros or ()) else 'codOrgao'
    if not params.get(chave):
        params[chave] = codigo_orgao


class ImportadorSIAPENetService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.SIAPE_NET)

        try:
            cliente = Client(self.api_externa.url_base, timeout=10)
            cliente.set_options(retxml=True)
            cliente.options.location = self.api_externa.url_base.split('?')[0]
            self.client = cliente
        except (URLError, TransportError, OSError) as e:
            logger.warning(f'[ImportadorWs] Falha ao conectar no webservice SIAPE: {e}', exc_info=True)
            raise ValidationError('Erro ao conectar com o webservice do SIAPE. Por favor, tente novamente mais tarde.')
        except Exception as e:
            logger.warning(f'[ImportadorWs] Erro inesperado: {e}', exc_info=True)
            raise ValidationError('Erro inesperado ao configurar o webservice. Contate o suporte técnico.')

    def estah_acessivel(self, verbosity=False):
        try:
            headers = self.get_headers()
            params = {
                'consulta': 'consultaDadosFuncionais',
                'cpf': self.api_externa.cpf_operador,
                'parmExistPag': 'a',
                'parmTipoVinculo': 'b',
            }
            if verbosity:
                logger.info(f'API SIAPENET Call: Headers: {headers}\nParams: {params}')
            start = time.perf_counter()
            obter_versao = self._call_service_siape(params)
            stop = time.perf_counter()
            if verbosity:
                logger.info(f'API SIAPENET Response: {obter_versao}\nDuration: {stop - start:.2f} seconds')
            return '</ns1:consultaDadosFuncionaisResponse>' in str(obter_versao)
        except Exception as e:
            if verbosity:
                logger.warning(f'Erro ao acessar o serviço SIAPENET. Exception {e}')
            return False

    def __get_params_service(self, method):
        params = ', '.join(f'{part.name}' for part in method.soap.input.body.parts)
        return params

    def _get_service_and_params(self):
        data = {}
        for method in list(self.client.wsdl.services[0].ports[0].methods.values()):
            params = self.__get_params_service(method)
            data[method.name] = params
        return data

    def _call_service_siape(self, params):
        headers = self.get_headers()
        metodo = params.pop('consulta')
        params['siglaSistema'] = headers['siglaSistema']
        params['nomeSistema'] = headers['nomeSistema']
        params['senha'] = headers['senha']
        assinatura = self._get_service_and_params().get(metodo)
        if not assinatura:
            raise Exception(f'Operação {metodo} não existe no WSDL do SIAPE.')
        nome_parametros = assinatura.replace(' ', '').split(',')
        aplicar_codigo_orgao(params, nome_parametros, str(headers.get('codigoOrgao') or ''))
        try:
            result = getattr(self.client.service, metodo)(*[params[parametro] for parametro in nome_parametros])
        except WebFault as webfault_ex:
            # os códigos 0030 e 0002 significam "Não existem dados para consulta"
            # por algum motivo o suds gera uma exceção ao invés de retorna vazio sendo necessário tratar
            if webfault_ex.fault.faultcode in ('0030', '0002'):
                return b'<empty></empty>'  # tratar mais a frente
            raise Exception(f'Erro no {metodo} -> code: {webfault_ex.fault.faultcode} | message: {webfault_ex.fault.faultstring}')
        except Exception as e:
            if settings.DEBUG:
                raise e
            raise Exception(f'Erro ao executar o método {metodo}. Detalhe {e}')
        return result


class ImportadorSIAPEConectaService(APIExternaService):
    def __init__(self):
        super().__init__(APIExterna.SIAPE_CONECTA)

    def estah_acessivel(self, verbosity=False):
        try:
            params = {
                'consulta': 'consultaDadosFuncionais',
                'cpf': self.api_externa.cpf_operador,
                'parmExistPag': 'a',
                'parmTipoVinculo': 'b',
            }
            obter_versao = self._call_service_siape(params, verbosity=verbosity)
            return '</ns1:consultaDadosFuncionaisResponse>' in str(obter_versao)
        except Exception as e:
            if verbosity:
                logger.warning(f'Erro ao acessar o serviço SIAPECONECTA. Exception {e}')
            return False

    def get_soap_params(self, params):
        # gerando os parâmetros no formato soap para requisição
        retorno = ''
        for k, v in params.items():
            retorno += f'<{k}>'
            retorno += str(v)
            retorno += f'</{k}>\n'
        return retorno

    def _monta_consulta(self, nome_parametros, metodo, params):
        # Organizando parâmetros. Para a api, os parâmetros devem seguir a ordem exata descrita no wsdl :/
        _nome_params = {parametro: params[parametro] for parametro in nome_parametros}
        data = f"""
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://servico.wssiapenet">
            <soapenv:Header/>
            <soapenv:Body>
                <ser:{metodo}>
                    {self.get_soap_params(_nome_params)}
                </ser:{metodo}>
            </soapenv:Body>
        </soapenv:Envelope>
        """
        return data

    def _get_service_and_params(self):
        return get_siape_wsdl()

    def _call_service_siape(self, params, verbosity=False):
        metodo = params.pop('consulta')
        try:
            #
            headers = self.get_headers(verbosity=verbosity)
            params['siglaSistema'] = headers['siglaSistema']
            params['nomeSistema'] = headers['nomeSistema']
            params['senha'] = headers['senha']
            nome_parametros = self._get_service_and_params().get(metodo)
            if not nome_parametros:
                raise Exception(f'Operação {metodo} não existe no WSDL do SIAPE.')
            aplicar_codigo_orgao(params, nome_parametros, str(headers.get('codigoOrgao') or ''))
            # gerando a consulta
            data = self._monta_consulta(nome_parametros, metodo, params)
            headers.update(
                {
                    'Content-Type': 'application/xml',
                }
            )
            response = requests.post(
                f'{self.api_externa.url_base}{self.api_externa.endpoint}', headers=headers, data=data, verbosity=verbosity, API=self.api_externa.nome
            )

            result = response.content
        except Exception as e:
            if settings.DEBUG:
                raise e
            raise Exception(f'Erro ao executar o método {metodo}. Detalhe {e}')
        return result


class ImportadorWs:
    lista_uorgs = None
    client = None
    token = None

    # Memória de UMA entrada por consulta, não um cache geral: a tela de importação
    # chama `importacao_servidor` e, logo depois, `get_historico_pca` para o MESMO
    # CPF, o que dobrava as idas ao SIAPE — e são várias, uma por órgão. Guardar só a
    # última resposta cobre esse par sem fazer a importação em massa (milhares de
    # CPFs, a mesma instância) crescer em memória.
    _ultimos_funcionais = None
    _ultimo_pca = None

    def __init__(self, api_externa=None):
        from comum.models import APIExterna

        if not api_externa:
            if APIExterna.SIAPE_CONECTA.ativo:
                self.client = ImportadorSIAPEConectaService()
            elif APIExterna.SIAPE_NET.ativo:
                self.client = ImportadorSIAPENetService()
            else:
                raise ValidationError('Nenhum serviço do SIAPE está ativo no sistema.')
        else:
            self.client = api_externa.get_service()

    @property
    def eh_conectagov(self) -> bool:
        return isinstance(self.client, ImportadorSIAPEConectaService)

    def _str_to_date(self, string_date):
        try:
            if string_date:
                return datetime.strptime(string_date, '%d%m%Y').date()
            return None
        except Exception:
            return None

    def parse_soap_response(self, soap_xml):
        root = ET.fromstring(soap_xml)
        # procurando por todos os nós a partir do <out>
        out_nodes = root.findall('.//out')
        result = [self.etree_to_dict(out_node) for out_node in out_nodes]
        return result

    def etree_to_dict(self, node):
        # convertendo a extrutura xml para um dicionário
        result = defaultdict(list)
        for child in node:
            if len(child) > 0:
                value = self.etree_to_dict(child)
            else:
                value = child.text
            tag = child.tag.split('}', 1)[-1]
            if isinstance(result[tag], list):
                result[tag].append(value)
            else:
                result[tag] = value
        return {key: value if len(value) > 1 else value[0] for key, value in result.items()}

    def _get_services_siape(self):
        list_options = []
        for k, v in list(self._get_service_and_params().items()):
            list_options.append([f'{k}', f'{k}({v})'])
        return list_options

    def _get_service_and_params(self):
        return self.client._get_service_and_params()

    def _call_service_siape(self, params):
        _result = self.client._call_service_siape(params)
        return self.parse_soap_response(_result)

    """ Consulta as uorgs do instituto e seta atributo para manter os valores."""

    def get_lista_uorgs(self, cod_uorg=1):
        #
        # não entendi pq essa consulta precisa de cpf :/
        params = {'consulta': 'listaUorgs', 'codUorg': str(cod_uorg), 'cpf': '11111111111'}
        self.lista_uorgs = self._call_service_siape(params)
        return self.lista_uorgs

    """ Consulta servidores de uma uorg. Se a uorg não for passada, consulta de todas as uorgs do instituto."""

    def get_lista_servidores(self, uo=None):
        s = {}
        uorgs = None
        if uo:
            uorgs = [uo]
        else:
            uorgs = self.lista_uorgs[0]

        for uorg in uorgs:
            try:
                s[uorg.codigo] = {'codigo': uorg.codigo, 'nome': f'{uorg.nome}'}
                #
                # não entendi pq essa consulta precisa de cpf :/
                params = {'consulta': 'listaServidores', 'cpf': 11111111111, 'codUorg': uorg.codigo}
                s[uorg.codigo]['servidores'] = self._call_service_siape(params)
            except Exception:
                continue
        return s

    """
    Consulta dados funcionais de um servidor
        :param cpf - apenas números
        :param todos_os_vinculos - Se True, mostra vínculos com ocorrência de exclusão, caso existam.
    """

    def get_dados_funcionais(self, cpf, todos_os_vinculos=False, ver_apenas_servidores_em_exercicio=False):
        tipo_vinculo = 'a' if ver_apenas_servidores_em_exercicio else 'b'
        params = {
            'consulta': 'consultaDadosFuncionais',
            'cpf': cpf,
            'parmExistPag': 'a',
            'parmTipoVinculo': tipo_vinculo,
        }
        if todos_os_vinculos:
            params.update({'parmExistPag': 'b', 'parmTipoVinculo': 'c'})

        dados_servidor = self._call_service_siape(params)

        return dados_servidor[0].get('dadosFuncionais').get('DadosFuncionais')

    """
    Consulta dados pessoais de um servidor
        :param cpf - apenas números
    """

    def get_dados_pessoais(self, cpf):
        params = {'consulta': 'consultaDadosPessoais', 'cpf': cpf, 'parmExistPag': 'b', 'parmTipoVinculo': 'c'}
        dados_pessoais = self._call_service_siape(params)
        return dados_pessoais

    """
    Consulta afastamentos no momento.
        :param cpf - apenas números
    TODO: Este método não está no padrã o correto. Corrigir!
    """

    def get_afastamento(self, cpf):
        try:
            params = {'consulta': 'consultaDadosAfastamento', 'cpf': cpf, 'parmExistPag': 'a', 'parmTipoVinculo': 'b'}
            afastamentos = self._call_service_siape(params)

            ocorrencias = None
            ferias = None

            # verificando afastamentos por matrícula
            if hasattr(ocorrencias, 'ArrayDadosAfastamento'):
                ferias_por_matr = {}
                ocorrencia_por_matr = {}

                afastamentos_matricula = afastamentos.dadosAfastamentoPorMatricula.DadosAfastamentoPorMatricula
                for a in afastamentos_matricula:
                    if a.ferias:
                        ferias_por_matr['dataIni'] = a.ferias.DadosFerias[0].dataIni
                        ferias_por_matr['dataFim'] = a.ferias.DadosFerias[0].dataFim

                        f = {}
                        f['ferias'] = ferias_por_matr
                        ferias = f

                    if a.ocorrencias:
                        ocorrencia_por_matr['codOcorrencia'] = a.ocorrencias.DadosOcorrencias[0].codOcorrencia
                        ocorrencia_por_matr['descOcorrencia'] = a.ocorrencias.DadosOcorrencias[0].descOcorrencia
                        ocorrencia_por_matr['dataIni'] = a.ocorrencias.DadosOcorrencias[0].dataIni
                        ocorrencia_por_matr['dataFim'] = a.ocorrencias.DadosOcorrencias[0].dataFim

                        o = {}
                        o['ocorrencia'] = ocorrencia_por_matr
                        ocorrencias = o

            return ferias, ocorrencias
        except WebFault as e:
            return e

    def get_afastamento_historico(self, cpf, mes_inicio=1, ano_inicio=None, mes_fim=12, ano_fim=None):
        if not ano_inicio:
            ano_inicio = date.today().year
        if not ano_fim:
            ano_fim = date.today().year + 1
        cpf = cpf.replace('.', '').replace('-', '')
        param_1 = 'a'
        # Servidores que tem 2 vinculos ativos ao mesmo tempo
        if Servidor.objects.ativos().filter(pessoa_fisica__cpf=cpf).count() >= 2:
            param_1 = 'b'
        params = {
            'consulta': 'consultaDadosAfastamentoHistorico',
            'cpf': str(cpf),
            'mesInicial': str(mes_inicio),
            'anoInicial': str(ano_inicio),
            'mesFinal': str(mes_fim),
            'anoFinal': str(ano_fim),
            'parmExistPag': str(param_1),
            'parmTipoVinculo': 'c',
        }
        ocorrencias = self._call_service_siape(params)
        afastamentos_servidor = []
        ferias_servidor = []
        if ocorrencias:
            ocorrencias = ocorrencias[0]
            ArrayDadosAfastamento = ocorrencias.get('ArrayDadosAfastamento')
            if type(ArrayDadosAfastamento) is not list:
                ArrayDadosAfastamento = [ArrayDadosAfastamento]
            if ArrayDadosAfastamento:
                for ocorrencia in ArrayDadosAfastamento:
                    dados_por_matricula = ocorrencia.get('dadosAfastamentoPorMatricula').get('DadosAfastamentoPorMatricula')
                    if type(dados_por_matricula) is not list:
                        dados_por_matricula = [dados_por_matricula]
                    for dado in dados_por_matricula:
                        matricula = extrai_matricula(dado.get('grMatricula'))
                        servidor = Servidor.objects.filter(matricula=matricula).first()
                        if servidor and dado.get('ferias') and Ferias:
                            anos_parcelas = []
                            list_of_ferias = dado.get('ferias').get('DadosFerias')
                            if type(list_of_ferias) is not list:
                                list_of_ferias = [list_of_ferias]
                            for dados_ferias in list_of_ferias:
                                ano_exercicio = Ano.objects.get_or_create(ano=int(dados_ferias.get('anoExercicio')))[0]
                                ferias = Ferias(ano=ano_exercicio, servidor=servidor)
                                numero_parcela = dados_ferias.get('numeroDaParcela')
                                ano_parcela = f'{ano_exercicio.ano}{numero_parcela}'
                                if ano_parcela not in anos_parcelas:
                                    kwargs = {
                                        'ferias': ferias,
                                        'numero_parcela': numero_parcela,
                                        'continuacao_interrupcao': dados_ferias.get('parcelaContinuacaoInterrupcao') == 'S',
                                        'parcela_interrompida': dados_ferias.get('parcelaInterrompida') == 'S',
                                        'data_inicio': self._str_to_date(dados_ferias.get('dataIni')),
                                        'data_fim': self._str_to_date(dados_ferias.get('dataFim')),
                                        'adiantamento_gratificacao_natalina': dados_ferias.get('gratificacaoNatalina') == 'S',
                                        'setenta_porcento': dados_ferias.get('adiantamentoSalarioFerias') == 'S',
                                    }
                                    ferias_servidor.append(kwargs)
                                    anos_parcelas.append(ano_parcela)

                        if servidor and dado.get('ocorrencias'):
                            list_of_afastamentos = dado.get('ocorrencias').get('DadosOcorrencias')
                            if type(list_of_afastamentos) is not list:
                                list_of_afastamentos = [list_of_afastamentos]
                            for dados_afastamento in list_of_afastamentos:
                                afastamento = AfastamentoSiape.objects.filter(codigo=dados_afastamento.get('codOcorrencia')).first()
                                if afastamento:
                                    kwargs = {
                                        'afastamento': afastamento,
                                        'servidor': servidor,
                                        'data_inicio': self._str_to_date(dados_afastamento.get('dataIni')),
                                        'data_termino': self._str_to_date(dados_afastamento.get('dataFim')),
                                    }
                                    afastamentos_servidor.append(kwargs)

        return {'ferias': ferias_servidor, 'afastamentos': afastamentos_servidor}

    """
    Consulta dados bancários de um servidor
        :param cpf - apenas números
    """

    def get_dados_bancarios(self, cpf):
        try:
            params = {'consulta': 'consultaDadosBancarios', 'cpf': cpf, 'parmExistPag': 'b', 'parmTipoVinculo': 'c'}
            dados_bancarios = self._call_service_siape(params)
            return dados_bancarios[0].get('dadosBancarios').get('DadosBancarios')
        except WebFault as e:
            return e

    """
    Consulta dependentes
        :param cpf - apenas números
    """

    def get_dependentes(self, cpf):
        try:
            params = {'consulta': 'consultaDadosDependentes', 'cpf': cpf, 'parmExistPag': 'a', 'parmTipoVinculo': 'b'}
            dependentes = self._call_service_siape(params)
            return dependentes
        except WebFault as e:
            return e

    """
    Consulta dados de documentação
        :param cpf - apenas números
    """

    def get_dados_documentacao(self, cpf):
        try:
            params = {'consulta': 'consultaDadosDocumentacao', 'cpf': cpf, 'parmExistPag': 'b', 'parmTipoVinculo': 'c'}
            documentacao = self._call_service_siape(params)
            return documentacao
        except WebFault as e:
            return e

    """
    Consulta dados de endereço residencial
        :param cpf - apenas números
    """

    def get_dados_endereco_residencial(self, cpf):
        try:
            params = {
                'consulta': 'consultaDadosEnderecoResidencial',
                'cpf': cpf,
                'parmExistPag': 'b',
                'parmTipoVinculo': 'c',
            }
            endereco = self._call_service_siape(params)
            return endereco
        except WebFault as e:
            return e

    """
    Consulta dados escolares (inclui as titulações)
        :param cpf - apenas números
    """

    def get_dados_escolares(self, cpf):
        try:
            params = {'consulta': 'consultaDadosEscolares', 'cpf': cpf, 'parmExistPag': 'b', 'parmTipoVinculo': 'c'}
            dados_escolares = self._call_service_siape(params)

            d_titutlacao = None
            d_escolar = None
            if dados_escolares:
                d_escolar = [
                    {
                        'codEscolaridade': dados_escolares[0].get('codEscolaridade'),
                        'nomeEscolaridade': dados_escolares[0].get('nomeEscolaridade'),
                    }
                ]

                if dados_escolares[0].get('arrayTitulacao'):
                    d_titutlacao = dados_escolares[0].get('arrayTitulacao').get('DadosTitulacao')
                    # IFF: Quando servidor tem apenas 1 titulação, o conteúdo da variável d_titutlacao é um dict
                    # Porém o espearado é que seja uma lista de dicts
                    if isinstance(d_titutlacao, dict):
                        d_titutlacao = [d_titutlacao]
                    # ENDIFF

            return {'escolar': d_escolar, 'titulacoes': d_titutlacao}
        except WebFault as e:
            return e

    """
    Consulta dados ficanceiros
        :param cpf - apenas números

        @TODO método fora do padrão. Corrigir.
    """

    def get_dados_financeiros(self, cpf):
        try:
            params = {'consulta': 'consultaDadosFinanceiros', 'cpf': cpf, 'parmExistPag': 'a', 'parmTipoVinculo': 'b'}
            dados_financeiros = self._call_service_siape(params)

            return dados_financeiros.dadosFinanceiros.DadosFinanceiros
        except WebFault as e:
            return e

    """
    Consulta dados uorg de um servidor
        :param cpf - apenas números
    """

    def get_dados_uorg(self, cpf):
        try:
            params = {'consulta': 'consultaDadosUorg', 'cpf': cpf, 'parmExistPag': 'a', 'parmTipoVinculo': 'b'}
            dados_uorg = self._call_service_siape(params)
            return dados_uorg
        except WebFault as e:
            return e

    """
    Consulta dados do contracheques
        :param cpf - apenas números
        :param anoInicial - apenas números
        :param anoFinal - apenas números
    """

    def get_dados_contracheques(self, cpf, ano_inicial=None, ano_fim=None, ultimo_cc_apenas=False):
        try:
            ano_atual = date.today().year
            params = {
                'consulta': 'consultaDadosFinanceirosHistorico',
                'cpf': cpf,
                'parmExistPag': 'b',
                'parmTipoVinculo': 'c',
                'anoInicial': str(ano_atual),
                'anoFinal': str(ano_atual),
            }
            if ano_inicial:
                params = params.update({'anoInicial': ano_inicial})
            if ano_fim:
                params = params.update({'anoFinal': ano_fim})

            _dados = self._call_service_siape(params)
            dados = _dados[0]
            if ultimo_cc_apenas and dados.get('ArrayDadosFinanceiros'):
                ultimo_ano_mes_cc = dados.get('ArrayDadosFinanceiros')[-1].get('mesAnoPagamento')
                cc_ultimo_mes_list = []
                for x in dados.get('ArrayDadosFinanceiros'):
                    if x.get('mesAnoPagamento') == ultimo_ano_mes_cc:
                        cc_ultimo_mes_list.append(x)
                dados['ArrayDadosFinanceiros'] = cc_ultimo_mes_list
            return dados
        except WebFault as e:
            return e

    """
    Consulta dados do PCA de um servidor
        :param cpf - apenas números
    """

    def get_dados_pca(self, cpf, codigo_orgao=None):
        """Histórico de PCA do CPF em um órgão.

        O PCA é atributo do cargo, não do exercício: consultado no órgão errado o
        SIAPE devolve `<out/>` vazio, com HTTP 200. Sem `codigo_orgao` vale o do
        cadastro da API externa.
        """
        codigo_orgao = codigo_orgao or self.client.get_headers().get('codigoOrgao')
        params = {'consulta': 'consultaHistoricoPCA', 'cpf': cpf, 'codigoOrgao': codigo_orgao}
        return self._call_service_siape(params)

    ORGAOS_SEM_ORIGEM = frozenset({'00000'})

    def orgaos_do_cargo(self, servidores: list[dict]) -> list[str]:
        """Órgãos em que pode existir PCA para os vínculos informados.

        Começa pela instituição e acrescenta cada `codigoOrgaoOrigem` distinto que
        os dados funcionais trouxerem — é o que recupera o histórico de cedidos,
        requisitados, redistribuídos e em exercício provisório, cujo cargo pertence
        ao órgão de origem. `00000` significa "sem origem externa".
        """
        nosso_orgao = self.client.get_headers().get('codigoOrgao')
        orgaos = [nosso_orgao]
        for vinculo in servidores:
            origem = (vinculo.get('codigoOrgaoOrigem') or '').strip()
            if origem and origem not in self.ORGAOS_SEM_ORIGEM and origem not in orgaos:
                orgaos.append(origem)
        return orgaos

    @staticmethod
    def cargos_pca(dados) -> list[dict]:
        """Normaliza a resposta de `consultaHistoricoPCA` numa lista de `CargoPca`."""
        if not dados:
            return []
        if not isinstance(dados, list):
            dados = [dados]
        infos = dados[0].get('CargoPca')
        if not infos:
            return []
        return [infos] if isinstance(infos, dict) else list(infos)

    @staticmethod
    def pca_do_cargo_atual(registros: list[dict]) -> dict:
        """Provimento que descreve o cargo ocupado hoje.

        Prefere o `VIGENTE`; não havendo (aposentado, substituto com contrato findo,
        cedido cujo provimento já encerrou), cai no de início mais recente. As datas
        vêm em ISO, então a ordem lexicográfica é a cronológica.
        """
        vigentes = [registro for registro in registros if registro.get('situacaoPca') == 'VIGENTE']
        return max(vigentes or registros, key=lambda registro: registro.get('dataInicio') or '')

    def coletar_pca_por_orgao(self, cpf: str, servidores: list[dict]) -> list[tuple[str, list[dict]]]:
        """Provimentos do CPF, agrupados pelo órgão que os devolveu.

        Os órgãos sem retorno continuam na lista, com a lista vazia: a tela precisa
        mostrar onde se procurou e não se achou, e o log precisa distinguir "não é
        deste órgão" de falha de comunicação — o que antes era a mesma linha.

        Reaproveita a última coleta quando o CPF e os órgãos são os mesmos: a tela de
        importação percorre este caminho duas vezes para o mesmo servidor, uma pela
        importação e outra para montar a aba.
        """
        orgaos = self.orgaos_do_cargo(servidores)
        chave = (cpf, tuple(orgaos))
        if self._ultimo_pca and self._ultimo_pca[0] == chave:
            return self._ultimo_pca[1]
        resultado = []
        for codigo_orgao in orgaos:
            dados = self._consultar_com_retentativa(lambda orgao=codigo_orgao: self.get_dados_pca(cpf, orgao))
            encontrados = self.cargos_pca(dados)
            if not encontrados:
                logger.info('Sem PCA para o CPF %s no órgão %s.', mask_cpf(cpf), codigo_orgao)
            resultado.append((codigo_orgao, encontrados))
        self._ultimo_pca = (chave, resultado)
        return resultado

    def coletar_pca(self, cpf: str, servidores: list[dict]) -> list[dict]:
        """Todos os provimentos do CPF, somando o que cada órgão envolvido devolver."""
        return [registro for _, registros in self.coletar_pca_por_orgao(cpf, servidores) for registro in registros]

    @staticmethod
    def _data_pca(valor: str | None) -> date | None:
        """Converte a data ISO do PCA; o SIAPE manda a tag vazia quando não há data."""
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except TypeError, ValueError:
            return None

    @staticmethod
    def _documento_legal(registro: dict, sufixo: str) -> str:
        """Monta 'PORTARIA 000870/2017' a partir dos campos de documento legal."""
        partes = [registro.get(f'tipoDl{sufixo}'), registro.get(f'numeroDl{sufixo}')]
        return ' '.join(parte.strip() for parte in partes if parte and parte.strip())

    def _provimento_para_exibicao(self, registro: dict, codigo_orgao: str) -> dict:
        """Achata um `CargoPca` nos campos que a aba exibe."""
        return {
            'matricula_siape': registro.get('matriculaSiape'),
            'situacao': registro.get('situacaoPca'),
            'cargo': registro.get('nomeCargo'),
            'codigo_cargo': registro.get('codigoCargo'),
            'codigo_vaga': registro.get('codigoVaga'),
            'orgao': registro.get('nomeOrgao'),
            'codigo_orgao': registro.get('codigoOrgao') or codigo_orgao,
            'data_inicio': self._data_pca(registro.get('dataInicio')),
            'data_fim': self._data_pca(registro.get('dataFim')),
            'forma_provimento': registro.get('formaProvimento'),
            'forma_vacancia': registro.get('formaVacancia'),
            'documento_provimento': self._documento_legal(registro, 'Provimento'),
            'publicacao_provimento': self._data_pca(registro.get('dataPublicacaoDlProvimento')),
            'documento_vacancia': self._documento_legal(registro, 'Vacancia'),
            'publicacao_vacancia': self._data_pca(registro.get('dataPublicacaoDlVacancia')),
        }

    def get_historico_pca(self, cpf: str, servidores: list[dict] | None = None, ver_apenas_servidores_em_exercicio: bool = False) -> dict:
        """Histórico de PCA do CPF pronto para exibição, órgão a órgão.

        Alimenta a aba "Provimentos de Cargo" da tela de importação de servidor. Sem
        `servidores`, consulta os dados funcionais para descobrir os órgãos de origem —
        e aí respeita o mesmo filtro de vínculos escolhido no formulário, senão a aba
        mostraria provimentos de vínculos que o resto da tela omitiu.

        Returns:
            `consultas` com um item por órgão consultado (e quantos provimentos vieram
            de cada um) e `provimentos` achatados, do mais recente para o mais antigo.
        """
        cpf = cpf.replace('.', '').replace('-', '')
        if servidores is None:
            servidores = self._consultar_dados_funcionais(cpf, ver_apenas_servidores_em_exercicio)
        siglas = {(vinculo.get('codigoOrgaoOrigem') or '').strip(): vinculo.get('siglaOrgaoOrigem') for vinculo in servidores}
        consultas = []
        provimentos = []
        for codigo_orgao, registros in self.coletar_pca_por_orgao(cpf, servidores):
            nome = siglas.get(codigo_orgao) or (registros[0].get('nomeOrgao') if registros else '')
            consultas.append({'codigo_orgao': codigo_orgao, 'sigla_orgao': nome, 'quantidade': len(registros)})
            provimentos.extend(self._provimento_para_exibicao(registro, codigo_orgao) for registro in registros)
        provimentos.sort(key=lambda provimento: provimento['data_inicio'] or date.min, reverse=True)
        return {'consultas': consultas, 'provimentos': provimentos}

    #########################
    # IMPORTAÇÕES           #
    #########################
    # Cada consulta ao SIAPE é tentada até este número de vezes antes de desistir.
    TENTATIVAS_POR_CONSULTA = 3

    def _consultar_com_retentativa(self, consulta, propagar_em_debug=False):
        """Chama ``consulta()`` até ``TENTATIVAS_POR_CONSULTA`` vezes; ``None`` se todas falharem.

        ``propagar_em_debug`` preserva a assimetria do código original: só a
        consulta de dados funcionais relançava a exceção sob ``DEBUG``.
        """
        for tentativa in range(1, self.TENTATIVAS_POR_CONSULTA + 1):
            try:
                return consulta()
            except Exception as e:
                if propagar_em_debug and settings.DEBUG:
                    # `raise` puro, e não `raise e`: preserva o traceback original
                    # da falha, que é o que serve ao diagnóstico.
                    raise
                if tentativa == self.TENTATIVAS_POR_CONSULTA:
                    # Sem isto a causa some: quem chama só vê `None` e emite a
                    # mensagem genérica, que foi o que dificultou o erro 10210.
                    logger.warning(
                        'Consulta ao SIAPE falhou nas %s tentativas: %s: %s',
                        self.TENTATIVAS_POR_CONSULTA,
                        type(e).__name__,
                        e,
                    )
                    return None
        return None

    def _consultar_dados_funcionais(self, cpf, ver_apenas_servidores_em_exercicio):
        chave = (cpf, ver_apenas_servidores_em_exercicio)
        if self._ultimos_funcionais and self._ultimos_funcionais[0] == chave:
            return self._ultimos_funcionais[1]
        dados = self._consultar_com_retentativa(
            lambda: self.get_dados_funcionais(cpf, True, ver_apenas_servidores_em_exercicio),
            propagar_em_debug=True,
        )
        if not dados:
            raise Exception('Não foi possível recuperar dados funcionais do servidor.')
        if type(dados) is not list:
            dados = [dados]
        servidores = list(dados)
        self._ultimos_funcionais = (chave, servidores)
        return servidores

    def _acrescentar_documentacao(self, pessoa, cpf):
        """Documentação ausente NÃO aborta a importação.

        RG, título de eleitor, CNH e CTPS são complementares, e o SIAPE
        simplesmente pode não ter o registro — foi o caso do erro 10210, em que
        os dados funcionais vinham completos e só esta consulta voltava vazia.
        A função já trata PCA, contracheques e dependentes assim.

        `numCPF` é a exceção: ele só vem daqui e é indispensável. Quando falta,
        o CPF consultado é a fonte de verdade — foi a chave usada para achar
        esta pessoa, e sem ele `mask_cpf(None)` devolveria `''`.
        """
        dados = self._consultar_com_retentativa(lambda: self.get_dados_documentacao(cpf))
        if dados:
            pessoa.update(dados[0])
        else:
            logger.warning('Não foi possível recuperar dados de documentação do servidor (CPF %s).', cpf)

        # Fora do if de propósito: a resposta pode vir NÃO vazia e ainda assim
        # sem `numCPF` — dado parcial, comum no SIAPE. Garantir só no ramo vazio
        # deixaria a mesma corrupção (`PessoaFisica` com cpf='') entrar por outro
        # caminho.
        if not pessoa.get('numCPF'):
            logger.warning('Documentação sem numCPF (CPF %s); usando o CPF consultado.', cpf)
            pessoa['numCPF'] = cpf

    def _acrescentar_dados_pessoais(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dados_pessoais(cpf))
        if not dados:
            raise Exception('Não foi possível recuperar dados pessoais do servidor.')
        pessoa.update(dados[0])

    def _acrescentar_endereco_residencial(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dados_endereco_residencial(cpf))
        if not dados:
            raise Exception('Não foi possível recuperar dados endereco residencial.')
        pessoa.update(dados[0])

    def _acrescentar_dados_bancarios(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dados_bancarios(cpf))
        if not dados:
            raise Exception('Não foi possível recuperar dados bancários do servidor.')
        pessoa['dados_bancarios'] = {}
        if type(dados) is not list:
            dados = [dados]
        for d in dados:
            if pessoa['dados_bancarios'].get(d['matricula']):
                pessoa['dados_bancarios'].get(d['matricula']).update(d)
            else:
                pessoa['dados_bancarios'].update({d['matricula']: d})

    def _acrescentar_dados_escolares(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dados_escolares(cpf))
        if not dados:
            raise Exception('Não foi possível recuperar dados escolares do servidor.')
        for chave in dados:
            valor = dados.get(chave)
            if valor:
                pessoa[chave] = valor if chave == 'titulacoes' else valor[0]

    def _acrescentar_contracheques(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dados_contracheques(cpf, ultimo_cc_apenas=True))
        if not dados:
            return
        pessoa['dados_contracheques'] = {}
        for d in dados.get('ArrayDadosFinanceiros'):
            pagamento = {d['mesAnoPagamento']: d['dadosFinanceiros']}
            if pessoa['dados_contracheques'].get(d['matricula']):
                pessoa['dados_contracheques'].get(d['matricula']).update(pagamento)
            else:
                pessoa['dados_contracheques'].update({d['matricula']: pagamento})

    def _acrescentar_pca(self, pessoa, cpf, servidores):
        """Indexa o PCA por vínculo, consultando também o órgão de origem.

        PCA ausente não é erro — estagiário e colaborador não ocupam cargo efetivo e
        simplesmente não têm provimento.

        Duas mudanças em relação ao comportamento anterior, ambas necessárias para o
        histórico aparecer: o `VIGENTE` deixou de ser filtro (era ele que apagava o
        provimento de aposentados e substitutos, em que toda situação é `ENCERRADO`)
        e a chave passou a ser a matrícula do vínculo, casada com o provimento por
        `_pca_do_vinculo` — o órgão de origem devolve a matrícula dele, não a nossa.
        """
        pessoa['dados_pca'] = {}
        registros = self.coletar_pca(cpf, servidores)
        if not registros:
            return
        por_base: dict[str, list[dict]] = defaultdict(list)
        for registro in registros:
            por_base[base_matricula(registro.get('matriculaSiape'))].append(registro)
        for vinculo in servidores:
            escolhido = self._pca_do_vinculo(vinculo, por_base)
            if escolhido:
                pessoa['dados_pca'][extrai_matricula(vinculo['matriculaSiape'])] = escolhido

    def _pca_do_vinculo(self, vinculo: dict, por_base: dict[str, list[dict]]) -> dict | None:
        """Escolhe, entre os provimentos do CPF, o que corresponde a este vínculo.

        A base de 6 dígitos identifica a PESSOA, não o vínculo: quem tem mais de uma
        matrícula cai toda na mesma base. Por isso a matrícula exata decide primeiro —
        sem ela, um servidor cedido com dois vínculos (2375512 no IFRN, encerrado, e
        1375512 na UFOB, vigente) recebia o mesmo provimento nos dois.

        A base só decide quando o provimento veio de outro órgão e por isso tem
        numeração própria; nesse caso vale o provimento do órgão de origem do vínculo.
        """
        matricula = vinculo.get('matriculaSiape')
        candidatos = por_base.get(base_matricula(matricula)) if matricula else None
        if not candidatos:
            return None
        exatos = [registro for registro in candidatos if registro.get('matriculaSiape') == matricula]
        if exatos:
            return self.pca_do_cargo_atual(exatos)
        origem = (vinculo.get('codigoOrgaoOrigem') or '').strip()
        if origem and origem not in self.ORGAOS_SEM_ORIGEM:
            candidatos = [registro for registro in candidatos if registro.get('codigoOrgao') == origem] or candidatos
        return self.pca_do_cargo_atual(candidatos)

    def _acrescentar_dependentes(self, pessoa, cpf):
        dados = self._consultar_com_retentativa(lambda: self.get_dependentes(cpf))
        if dados:
            pessoa['dados_dependentes'] = dados

    def _get_servidor_completo(self, cpf, ver_apenas_servidores_em_exercicio=False):
        """Monta ``(servidores, pessoa)`` a partir das consultas do SIAPE.

        Cada consulta era um laço de retentativa copiado, com o mesmo tratamento
        de falha; a repetição está agora em ``_consultar_com_retentativa`` e cada
        bloco virou um ``_acrescentar_*``. A decomposição foi necessária para
        caber na regra de complexidade ao tornar a documentação tolerante.

        Quais consultas são fatais é decisão de negócio, não detalhe: funcionais,
        pessoais, endereço, bancários e escolares abortam; documentação, PCA,
        contracheques e dependentes apenas avisam.
        """
        cpf = cpf.replace('.', '').replace('-', '')
        pessoa = {}

        servidores = self._consultar_dados_funcionais(cpf, ver_apenas_servidores_em_exercicio)
        self._acrescentar_documentacao(pessoa, cpf)
        self._acrescentar_dados_pessoais(pessoa, cpf)
        self._acrescentar_endereco_residencial(pessoa, cpf)
        self._acrescentar_dados_bancarios(pessoa, cpf)
        self._acrescentar_dados_escolares(pessoa, cpf)
        self._acrescentar_contracheques(pessoa, cpf)
        self._acrescentar_pca(pessoa, cpf, servidores)
        self._acrescentar_dependentes(pessoa, cpf)

        return servidores, pessoa

    def _data_ingresso_servico_publico(self, servidores: list[dict], cpf: str | None = None) -> date | None:
        """Data de ingresso no serviço público consolidada entre os vínculos do CPF.

        ``dataOcorrIngressoServPublico`` (consultaDadosFuncionais) é a data de uma
        ocorrência da MATRÍCULA, não da pessoa: o SIAPE só a preenche no vínculo em
        que o ingresso aconteceu e devolve ``<dataOcorrIngressoServPublico></...>``
        nos demais. O CPF 034.710.844-01 traz ``20082004`` na matrícula 1466156
        (inativa) e vazio na 2466156 (ativa) — o vínculo ativo ficava sem a data e a
        licença capacitação passava a calcular pelo início de exercício na
        instituição (2010) em vez de 2004.

        Ingresso no serviço público é atributo da pessoa e não retrocede, então vale
        a data mais antiga entre os vínculos devolvidos para o CPF. Devolve ``None``
        quando nenhum vínculo tem a informação.

        O que já está gravado para o CPF entra na comparação: sem isso, um ciclo em
        que o vínculo detentor do primeiro ingresso não voltasse na resposta moveria
        a data para frente — a mesma perda que este método existe para evitar, só que
        no sentido inverso. Para sobrepor a regra num caso específico, o mecanismo é
        cadastrar o campo como ``ExcecaoDado`` do tipo webservice.
        """
        datas = [d for d in (self._str_to_date(s.get('dataOcorrIngressoServPublico')) for s in servidores) if d]
        if cpf:
            gravadas = Servidor.objects.filter(pessoa_fisica__cpf=cpf).values_list('data_inicio_servico_publico', flat=True)
            datas += [d for d in gravadas if d]
        return min(datas) if datas else None

    """
    Processamento de importação de um servidor
        :param cpf - apenas números
        :param ver_apenas_servidores_em_exercicio - Se True, segue a regra do parametro ParmTipoVinculo (opção 'a') definida na documentação ConsultaSiape.
    """

    def importacao_servidor(self, cpf, ver_dados_apenas=False, ver_apenas_servidores_em_exercicio=False):
        try:
            ###############################
            # Consultando cpf no webservice
            ###############################
            servidores, pessoa = self._get_servidor_completo(cpf, ver_apenas_servidores_em_exercicio)

            ############################
            # DADOS FUNCIONAIS         #
            ############################

            # TODO: verificar quando setar o campo "data_obito"
            # TODO: é para setar o username com a matrícula do servidor/estagiário?

            #
            # Não foi possível recuperar:
            # 1. CargoEmprego, pois não é possível recuperar o grupo cargo emprego via webservice
            # 2. Não foi encontrado a data do primeiro emprego via webservice (ctps_data_prim_emprego)
            # 3. Não foi possível encontrar o código do país via webservice
            # 4. Não foi possível encontrar o grupo de deficiência via webservice

            #
            # Carregando informações sobre exceções de atualização de dados
            # - carrega campos de servidores que não terão essas informações atualizadas (os campos cadastrados como exceção de atualização)
            excecoes_atualizacao = {}
            for i in ExcecaoDado.objects.filter(tipo_extracao=TipoExtracao.TIPO_WEBSERVICE):
                if i.servidor.matricula not in excecoes_atualizacao:
                    excecoes_atualizacao[i.servidor.matricula] = list(i.campos.values_list('campo', flat=True))

            #
            # A data de ingresso no serviço público vale para a pessoa, não para o vínculo:
            # é consolidada uma vez a partir de todos os vínculos devolvidos para o CPF.
            ingresso_servico_publico = self._data_ingresso_servico_publico(servidores, mask_cpf(pessoa.get('numCPF')))

            dados_atualizar = []
            for servidor in servidores:
                matricula = extrai_matricula(servidor.get('matriculaSiape'))
                # Verificando se existe um email siape cadastrado. Caso negativo, não permite o cadastro do servidor
                email_siape = servidor.get('emailServidor')
                if not email_siape or email_siape == '':
                    raise ValidationError(
                        'Não existe um e-mail cadastrado no SIAPE para o servidor. Por favor, cadastre um e-mail e repita esta operação.'
                    )
                #
                # Verificando se o servidor participa do PGD
                participa_pgd = servidor.get('participaPGD') == 'sim'
                #
                args = {
                    'pessoa_fisica': {
                        'cpf': mask_cpf(pessoa.get('numCPF')),
                        'nome': normalizar_nome_proprio(pessoa.get('nome')),
                        'nome_registro': normalizar_nome_proprio(pessoa.get('nome')),
                        'nome_mae': normalizar_nome_proprio(pessoa.get('nomeMae')),
                        'nome_pai': normalizar_nome_proprio(pessoa.get('nomePai')),
                        'sexo': pessoa.get('codSexo'),
                        'nascimento_data': self._str_to_date(pessoa.get('dataNascimento')),
                        'raca': Raca.objects.get_or_create(codigo_siape=pessoa.get('codCor'), defaults={'descricao': pessoa.get('nomeCor')})[0],
                        'estado_civil': EstadoCivil.get_or_create(codigo_siape=pessoa.get('codEstadoCivil'))[0],
                        'nacionalidade': pessoa.get('codNacionalidade'),
                        'titulo_numero': pessoa.get('numeroTituloEleitor'),
                        'titulo_zona': pessoa.get('zonaTituloEleitor'),
                        'titulo_secao': pessoa.get('secaoTituloEleitor'),
                        'titulo_uf': pessoa.get('ufTituloEleitor'),
                        'titulo_data_emissao': self._str_to_date(pessoa.get('dataTituloEleitor')),
                        'rg': pessoa.get('numeroCarteiraIdentidade'),
                        'rg_orgao': pessoa.get('orgaoCarteiraIdentidade'),
                        'rg_data': self._str_to_date(pessoa.get('dataCarteiraIdentidade')),
                        'rg_uf': pessoa.get('ufCarteiraIdentidade'),
                        'cnh_carteira': pessoa.get('numeroCarteiraMotorista'),
                        'cnh_registro': pessoa.get('registroCarteiraMotorista'),
                        'cnh_categoria': pessoa.get('categoriaCarteiraMotorista'),
                        'cnh_emissao': self._str_to_date(pessoa.get('dataExpedicaoCarteiraMotorista')),
                        'cnh_uf': pessoa.get('ufCarteiraMotorista'),
                        'cnh_validade': self._str_to_date(pessoa.get('dataValidadeCarteiraMotorista')),
                        'ctps_numero': pessoa.get('numeroCarteiraTrabalho'),
                        'ctps_uf': pessoa.get('ufCarteiraTrabalho'),
                        'ctps_serie': pessoa.get('serieCarteiraTrabalho'),
                        'pis_pasep': pessoa.get('numPisPasep'),
                    },
                    'matricula': matricula,
                    'situacao': Situacao.objects.get_or_create(codigo=servidor.get('codSitFuncional'))[0],
                    'email_siape': email_siape.lower(),
                    'identificacao_unica_siape': servidor.get('identUnica'),
                    'data_inicio_exercicio_na_instituicao': self._str_to_date(servidor.get('dataExercicioNoOrgao')),
                    'regime_juridico': RegimeJuridico.get_or_create(sigla=servidor.get('siglaRegimeJuridico'))[0],
                    'participa_pgd': participa_pgd,
                }

                # Sem a chave, o campo fica de fora do `defaults` do update_or_create em
                # Servidor.update_or_create: não havendo data em nenhum vínculo, preserva o
                # que já está cadastrado em vez de apagar com None. Escrito como expressão
                # (e não `if`) para não somar complexidade a esta função legada (C901 57).
                args.update({'data_inicio_servico_publico': ingresso_servico_publico} if ingresso_servico_publico else {})

                # dados PCA (apenas início no cargo por enquanto)
                dados_pca = pessoa.get('dados_pca')
                if dados_pca and dados_pca.get(matricula):
                    dados = dados_pca.get(matricula)
                    #
                    data_inicio = dados.get('dataInicio')
                    if data_inicio:
                        data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                    #
                    args.update({'data_posse_no_cargo': data_inicio, 'data_inicio_exercicio_no_cargo': data_inicio})

                # modalidade do PGD (apenas se participa do PGD)
                if participa_pgd:
                    modalidade_pgd = servidor.get('modalidadePGD')
                    if modalidade_pgd and modalidade_pgd != '':
                        modalidade_pgd = ModalidadePGD.get_or_create(nome=servidor.get('modalidadePGD'))[0]
                        args.update({'modalidade_pgd': modalidade_pgd})

                nivel_padrao = servidor.get('codPadrao')
                try:
                    nivel_padrao = servidor.get('codPadrao', '').lstrip('0')
                except Exception:
                    pass
                args['nivel_padrao'] = nivel_padrao

                passaporte = pessoa.get('passaporte')
                if passaporte:
                    args['pessoa_fisica']['passaporte'] = passaporte

                if ver_dados_apenas:
                    args.update({'nome_apresentacao': normalizar_nome_proprio(pessoa.get('nome'))})

                #
                # E-mail institucional: campo próprio do SIAPE (consultaDadosFuncionais), distinto do emailServidor (pessoal).
                # Só grava quando vier preenchido, para não apagar um valor já existente em atualizações, e apenas
                # quando for de um domínio institucional: servidor cedido/redistribuído traz o e-mail do órgão de origem.
                Configuracao = apps.get_model('comum', 'configuracao')
                email_institucional = servidor.get('emailInstitucional')
                if email_institucional and Configuracao.email_institucional_permitido(email_institucional):
                    args['email_institucional'] = email_institucional.strip().lower()

                #
                # Verificando email secundario
                email_secundario = pessoa.get('email_secundario')
                if email_secundario:
                    Configuracao = apps.get_model('comum', 'configuracao')
                    if not Configuracao.get_valor_por_chave(
                        'comum', 'permite_email_institucional_email_secundario'
                    ) and not Configuracao.eh_email_institucional(email_secundario):
                        args['pessoa_fisica']['email_secundario'] = email_secundario

                #
                # tratando deficiência
                deficiencia = pessoa.get('codDefFisica')
                if deficiencia:
                    try:
                        deficiencia = Deficiencia.objects.get(codigo=pessoa.get('codDefFisica'))
                        args['pessoa_fisica']['deficiencia'] = deficiencia
                    except Exception:
                        pass

                #
                # tratando país de origem
                pais_origem = pessoa.get('pais_origem')
                if pais_origem:
                    try:
                        pais_origem = Pais.objects.get(nome=pessoa.get('pais_origem'))
                        args['pessoa_fisica']['pais_origem'] = pais_origem
                    except Exception:
                        pass
                #
                # tratando nome do município de nascimento
                municipio_nascimento = pessoa.get('nomeMunicipNasc')
                uf_nascimento = pessoa.get('ufNascimento')
                if municipio_nascimento and uf_nascimento:
                    identificacao = Municipio.get_identificacao(municipio_nascimento, uf_nascimento)
                    municipio_nascimento = Municipio.objects.get_or_create(
                        identificacao=identificacao, defaults={'uf': uf_nascimento, 'nome': municipio_nascimento}
                    )[0]
                    args['pessoa_fisica']['nascimento_municipio'] = municipio_nascimento

                #
                # tratando grupo sanguíneo
                gs = pessoa.get('grupoSanguineo')
                if gs:
                    grupo_sanguineo = re.findall('[a-zA-Z]+', gs)
                    fator_rh = re.findall('[-+]+', gs)
                    if grupo_sanguineo and fator_rh:
                        args['pessoa_fisica']['grupo_sanguineo'] = grupo_sanguineo[0]
                        args['pessoa_fisica']['fator_rh'] = fator_rh[0]

                #
                # tratando cargo emprego
                cargo_emprego = servidor.get('codCargo')
                if cargo_emprego:
                    cargo_emprego = CargoEmprego.objects.get_or_create(codigo=cargo_emprego, defaults={'nome': servidor.get('nomeCargo')})[0]
                    args.update({'cargo_emprego': cargo_emprego})

                #
                # tratando cargo classe
                cargo_classe = servidor.get('codClasse')
                if cargo_classe:
                    cargo_classe = CargoClasse.objects.get_or_create(codigo=cargo_classe, defaults={'nome': servidor.get('nomeClasse')})[0]
                    args.update({'cargo_classe': cargo_classe})

                #
                # tratando atividade da função
                funcao_atividade = servidor.get('codAtivFun')
                if funcao_atividade:
                    funcao_atividade = Atividade.objects.get_or_create(
                        codigo=servidor.get('codAtivFun'), defaults={'nome': servidor.get('nomeAtivFun')}
                    )[0]
                    args.update({'funcao_atividade': funcao_atividade})
                funcao = servidor.get('codFuncao')
                data_ini_funcao = servidor.get('dataIngressoFuncao')
                nova_funcao = servidor.get('codNovaFuncao')
                data_ini_nova_funcao = servidor.get('dataIngressoNovaFuncao')
                if nova_funcao and (not data_ini_funcao or (data_ini_funcao and data_ini_nova_funcao > data_ini_funcao)):
                    nova_funcao = Funcao.objects.get_or_create(codigo=nova_funcao[:3].strip(), defaults={'nome': servidor.get('nomeNovaFuncao')})[0]
                    args.update({'funcao': nova_funcao})
                elif funcao:
                    funcao = Funcao.objects.get_or_create(codigo=funcao[:3].strip(), defaults={'nome': servidor.get('nomeFuncao')})[0]
                    args.update({'funcao': funcao})

                jornada_trabalho = servidor.get('codJornada')
                if jornada_trabalho:
                    jornada_trabalho = JornadaTrabalho.objects.get(codigo=jornada_trabalho)
                    args.update({'jornada_trabalho': jornada_trabalho})

                #
                # tratando o setor de lotação do servidor
                setor_lotacao = servidor.get('codUorgLotacao')
                if setor_lotacao and setor_lotacao != '':
                    setor_lotacao, _created = Setor.objects.siape().get_or_create(codigo=servidor.get('codUorgLotacao'))
                    args.update({'setor_lotacao': setor_lotacao})

                #
                # tratando o setor e setor exercício do servidor
                cod_setor_exercicio = servidor.get('codUorgExercicio')
                setor = None
                if cod_setor_exercicio and cod_setor_exercicio != '':
                    Configuracao = apps.get_model('comum', 'configuracao')
                    setor_exercicio, _created = Setor.objects.siape().get_or_create(codigo=cod_setor_exercicio)

                    ajustar_setores_na_reitoria = Configuracao.get_valor_por_chave('rh', 'ajustar_setores_na_reitoria')
                    if ajustar_setores_na_reitoria:
                        sigla_re = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
                        codigo_uorg = Configuracao.get_valor_por_chave('rh', 'codigo_uorg_vinculacao') or '000000001'
                        if cod_setor_exercicio == codigo_uorg and setor_exercicio.sigla != sigla_re:
                            s = Setor.objects.siape().get(sigla=sigla_re)
                            setor_exercicio = s
                            # ajustando o vinculo de todos os setores, alterando o vinculo de 1 para o vinculo da reitoria
                            cod_setor_exercicio = s.codigo

                    args.update({'setor_exercicio': setor_exercicio})
                    configuracao_setor = settings.TIPO_ARVORE_SETORES
                    if configuracao_setor == 'SIAPE':
                        setor = setor_exercicio
                    else:
                        try:
                            setor_exercicio_split = setor_exercicio.sigla.split('/')
                            sigla_setor = setor_exercicio_split[0]
                            sigla_uo = setor_exercicio_split[1]
                            setor = (
                                Setor.objects.suap().filter(sigla=sigla_setor, uo__sigla=sigla_uo, excluido=False).first()
                                or Setor.objects.suap().filter(sigla=setor_exercicio, uo__sigla=sigla_uo, excluido=False).first()
                            )

                        except Exception:
                            pass
                    if setor:
                        args.update({'setor': setor})

                #
                # tratando dados escolares e titulações
                dados_escolares = pessoa.get('escolar')
                if dados_escolares:
                    nivel_escolar, _created = NivelEscolaridade.objects.get_or_create(
                        codigo=dados_escolares.get('codEscolaridade'),
                        defaults={'nome': dados_escolares.get('nomeEscolaridade')},
                    )
                    args.update({'nivel_escolaridade': nivel_escolar})

                dados_titulacoes = pessoa.get('titulacoes')
                if dados_titulacoes:
                    #
                    # procurando a maior titulação
                    if 'contracheques' in settings.INSTALLED_APPS:
                        from contracheques import layout

                        d_posicao = {}
                        nomes_mapeados = set()
                        for k, v in list(layout.classificacao_titulacoes.items()):
                            for t in dados_titulacoes:
                                if t.get('nomeTitulacao') in v:
                                    d_posicao[k] = [t.get('codTitulacao'), t.get('nomeTitulacao')]
                                    nomes_mapeados.add(t.get('nomeTitulacao'))
                        # Titulação fora do mapa é ignorada pelo ranking — avisa em vez de descartar em
                        # silêncio (já causou servidor sem titulação quando o SIAPE emitiu nome novo).
                        nao_mapeadas = sorted({t.get('nomeTitulacao') or '(sem nome)' for t in dados_titulacoes} - nomes_mapeados)
                        if nao_mapeadas:
                            complemento = ' NENHUMA titulação foi salva para o servidor.' if not d_posicao else ''
                            logger.warning(
                                f'[ImportadorWs] Titulação(ões) do SIAPE ausente(s) do mapa classificacao_titulacoes '
                                f'(contracheques/layout.py) para o CPF {cpf}: {nao_mapeadas}.{complemento} Atualize o mapa.'
                            )
                        if d_posicao:
                            dados = d_posicao[max(d_posicao)]
                            titulacao, _created = Titulacao.objects.get_or_create(codigo=dados[0], defaults={'nome': dados[1]})
                            args.update({'titulacao': titulacao})

                # tratando a entrada de dados de contracheque via webservices
                dados_contracheques = pessoa.get('dados_contracheques')
                if dados_contracheques and dados_contracheques.get(matricula):
                    cc_dados = {}
                    for k, v in dados_contracheques.get(matricula).items():
                        lista_rubricas = []
                        for rubrica in v.get('DadosFinanceiros'):
                            lista_rubricas.append(
                                {
                                    'valorRubrica': rubrica['valorRubrica'],
                                    'nomeRubrica': rubrica['nomeRubrica'],
                                    'indicadorRD': rubrica['indicadorRD'],
                                    'numeroSeq': rubrica['numeroSeq'],
                                    'pzRubrica': rubrica['pzRubrica'],
                                    'codRubrica': rubrica['codRubrica'],
                                }
                            )
                        if cc_dados.get(matricula):
                            cc_dados.get(matricula).update({k: lista_rubricas})
                        else:
                            cc_dados.update({matricula: {k: lista_rubricas}})
                    args.update({'dados_contracheques': cc_dados})

                # dados bancários
                dados_bancarios = pessoa.get('dados_bancarios')
                if dados_bancarios and dados_bancarios.get(matricula):
                    db = dados_bancarios.get(matricula)
                    args['pessoa_fisica']['pagto_banco'] = Banco.get_or_create(codigo=db.get('banco'))[0]
                    args['pessoa_fisica']['pagto_agencia'] = db.get('agencia')
                    args['pessoa_fisica']['pagto_ccor'] = db.get('contaCorrente')

                # excluindo do args, informações que serão ignoradas na atualização do servidor
                if matricula in excecoes_atualizacao:
                    for campo in excecoes_atualizacao[matricula]:
                        #
                        # pessoa física
                        if ver_dados_apenas:
                            args.get('pessoa_fisica').update(
                                {campo: f'{args.get("pessoa_fisica").get(campo)} <br /><strong>(Não será atualizado)</strong>'}
                            )
                        elif campo in args.get('pessoa_fisica'):
                            del args.get('pessoa_fisica')[campo]
                        #
                        # servidor
                        if ver_dados_apenas:
                            args.update({campo: f'{args.get(campo)} <br /><strong>(Não será atualizado)</strong>'})
                        elif campo in args:
                            del args[campo]

                # se o parâmetro "ver_dados_apenas" for verdadeiro, iremos retornar o dicionário com as informações
                if ver_dados_apenas:
                    dados_atualizar.append(args)
                else:
                    dados_atualizar.append(self.__efetiva_dados_sevidor(matricula, servidor, pessoa, args))

            return dados_atualizar

        except WebFault:
            raise
        except IndexError:
            raise

    def __efetiva_dados_sevidor(self, matricula, servidor, pessoa, args):
        hoje = date.today()
        configuracao_setor = settings.TIPO_ARVORE_SETORES
        setor_suap = None
        if args.get('setor') and configuracao_setor == 'SUAP':
            setor_suap = args.pop('setor')

        # se tiver contracheque, recupera o dado e joga para cc, se não, seta cc igual a none
        # é necessário remover o indice "dados_contracheques" de args para não dar problema no update_or_create de servidor
        cc = None
        if args.get('dados_contracheques'):
            cc = args.pop('dados_contracheques')

        #
        args['data_ultima_atualizacao_webservice'] = hoje
        retorno = Servidor.update_or_create(args)
        servidor_atualizado = retorno['servidor']
        criado = retorno['servidor_created']
        atualizar_setor = False
        if criado and setor_suap:
            atualizar_setor = True
        elif not criado and setor_suap:
            if servidor_atualizado.setor not in setor_suap.descendentes:
                atualizar_setor = True
        if atualizar_setor:
            servidor_atualizado.setor = setor_suap
            servidor_atualizado.save()

        if servidor.get('dataOcorrIngressoOrgao'):
            ocorrencia = Ocorrencia.objects.get(codigo=servidor.get('codOcorrIngressoOrgao'))
            subgrupo = SubgrupoOcorrencia.objects.get_or_create(descricao='INCLUSAO NO ORGAO')[0]
            ServidorOcorrencia.objects.update_or_create(
                servidor=servidor_atualizado,
                ocorrencia=ocorrencia,
                subgrupo=subgrupo,
                data=self._str_to_date(servidor.get('dataOcorrIngressoOrgao')),
            )

        if servidor.get('dataOcorrIngressoServPublico'):
            ocorrencia = Ocorrencia.objects.get(codigo=servidor.get('codOcorrIngressoServPublico'))
            subgrupo = SubgrupoOcorrencia.objects.get_or_create(descricao='INCLUSAO NO SERVICO PUBLICO')[0]
            ServidorOcorrencia.objects.update_or_create(
                servidor=servidor_atualizado,
                ocorrencia=ocorrencia,
                subgrupo=subgrupo,
                data=self._str_to_date(servidor.get('dataOcorrIngressoServPublico')),
            )

        if servidor.get('codOcorrExclusao'):
            subgrupo = SubgrupoOcorrencia.objects.get_or_create(descricao='EXCLUSAO')[0]
            ocorrencia_exclusao = Ocorrencia.objects.get(codigo=servidor.get('codOcorrExclusao'))
            data_ocorrencia_exclusao = self._str_to_date(servidor.get('dataOcorrExclusao'))
            ServidorOcorrencia.objects.get_or_create(
                servidor=servidor_atualizado,
                ocorrencia=ocorrencia_exclusao,
                data=data_ocorrencia_exclusao,
                subgrupo=subgrupo,
            )
            Servidor.objects.filter(id=servidor_atualizado.id).update(ativo=False)
            Vinculo.objects.filter(id_relacionamento=servidor_atualizado.id, tipo_relacionamento__model='servidor').update(ativo=False)

            historico_setores_servidor = ServidorSetorHistorico.objects.filter(servidor=servidor_atualizado).order_by('-data_inicio_no_setor')
            if historico_setores_servidor.exists():
                setor_mais_atual = historico_setores_servidor[0]
                if not setor_mais_atual.data_fim_no_setor:
                    setor_mais_atual.data_fim_no_setor = data_ocorrencia_exclusao
                    setor_mais_atual.save()

        data_ingresso_orgao = self._str_to_date(servidor.get('dataOcorrIngressoOrgao'))

        Servidor.objects.filter(id=servidor_atualizado.id).update(
            # data_inicio_servico_publico=data_ingresso_servico_publico,
            data_posse_na_instituicao=data_ingresso_orgao,
            data_fim_servico_na_instituicao=servidor_atualizado.calcula_fim_servico_na_instituicao,
        )
        self.atualiza_historico_funcao(servidor, servidor_atualizado, args)

        """
        Atualiza dados da pessoa Física a partir do serviço get_dados_endereço_residencial
        """
        pessoa_fisica = servidor_atualizado.pessoa_fisica
        if pessoa.get('logradouro') and pessoa.get('uf') and pessoa.get('nomeMunicipio'):
            municipio = Municipio.get_or_create(pessoa.get('nomeMunicipio'), pessoa.get('uf'))[0]
            for pe in PessoaEndereco.objects.filter(pessoa__id=pessoa_fisica.pk):
                pe.__skip_history = True
                pe.delete()
            endereco = PessoaEndereco(
                pessoa_id=pessoa_fisica.pk,
                logradouro=pessoa['logradouro'],
                numero=pessoa['numero'],
                complemento=pessoa['complemento'],
                bairro=pessoa['bairro'],
                municipio=municipio,
                cep=pessoa['cep'],
            )
            endereco.__skip_history = True
            endereco.save()
        if pessoa.get('dddTelefone') and pessoa.get('numTelefone'):
            for pt in PessoaTelefone.objects.filter(pessoa__id=pessoa_fisica.pk):
                pt.__skip_history = True
                pt.delete()
            fone_numero = pessoa.get('numTelefone')
            fone_ddd = pessoa.get('dddTelefone')
            if fone_numero and fone_ddd:
                telefone_formatado = format_telefone(fone_ddd, fone_numero)
                telefone = PessoaTelefone(pessoa=pessoa_fisica, numero=telefone_formatado)
                telefone.__skip_history = True
                telefone.save()

        # contracheque
        if cc and 'contracheques' in settings.INSTALLED_APPS:
            if cc:
                ContraCheque = apps.get_model('contracheques', 'ContraCheque')
                contra_cheque = ContraCheque()
                contra_cheque.importar_contracheque_webservice(cc)

        # dependentes
        dados_dependentes = pessoa.get('dados_dependentes')
        if dados_dependentes:
            dep_raw = dados_dependentes[0].get('dadosDependentes', {})
            if dep_raw:
                lista_dep = dep_raw.get('DadosDependentes', [])
                if isinstance(lista_dep, dict):
                    lista_dep = [lista_dep]
                self._importar_dependentes(servidor_atualizado, lista_dep)

        return servidor_atualizado, criado

    def atualiza_historico_funcao(self, servidor, servidor_atualizado, args):
        ultima_funcao_suap = (
            ServidorFuncaoHistorico.objects.filter(servidor_id=servidor_atualizado.id, funcao__funcao_siape=True)
            .order_by('data_inicio_funcao')
            .last()
        )
        setor_exercicio = Setor.objects.siape().get(codigo=servidor.get('codUorgExercicio')) if servidor.get('codUorgExercicio') else None
        data_inicio_funcao_siape = self._str_to_date(servidor.get('dataIngressoFuncao'))
        data_inicio_nova_funcao_siape = self._str_to_date(servidor.get('dataIngressoNovaFuncao'))
        servidor_atualizado_kwargs = {}
        # Verifica se não é aposentado e se tem função nova
        if data_inicio_nova_funcao_siape and (
            not ultima_funcao_suap or (ultima_funcao_suap and ultima_funcao_suap.data_inicio_funcao < data_inicio_nova_funcao_siape)
        ):
            if ultima_funcao_suap and ultima_funcao_suap.data_fim_funcao is None:
                ServidorFuncaoHistorico.objects.filter(id=ultima_funcao_suap.id).update(data_fim_funcao=data_inicio_nova_funcao_siape)
            #
            _dados = {
                'servidor_id': servidor_atualizado.id,
                'data_inicio_funcao': self._str_to_date(servidor.get('dataIngressoNovaFuncao')),
                'nivel': servidor.get('codNovaFuncao')[3:],
                'funcao_id': args.get('funcao').id,
                'setor_id': setor_exercicio.id,
            }
            #
            ServidorFuncaoHistorico.objects.create(**_dados)
            #
            servidor_atualizado_kwargs['funcao_id'] = args.get('funcao').id
            servidor_atualizado_kwargs['funcao_codigo'] = servidor.get('codNovaFuncao')[3:]

        elif data_inicio_funcao_siape and (
            not ultima_funcao_suap or (ultima_funcao_suap and ultima_funcao_suap.data_inicio_funcao < data_inicio_funcao_siape)
        ):
            if ultima_funcao_suap and ultima_funcao_suap.data_fim_funcao is None:
                ServidorFuncaoHistorico.objects.filter(id=ultima_funcao_suap.id).update(data_fim_funcao=data_inicio_funcao_siape)
            ServidorFuncaoHistorico.objects.create(
                servidor_id=servidor_atualizado.id,
                data_inicio_funcao=self._str_to_date(servidor.get('dataIngressoFuncao')),
                nivel=servidor.get('codFuncao')[3:],
                funcao_id=args.get('funcao').id,
                setor_id=setor_exercicio.id,
                atividade_id=args.get('funcao_atividade').id,
            )
            # Atualizando dados em servidor
            servidor_atualizado_kwargs['funcao_id'] = args.get('funcao').id
            servidor_atualizado_kwargs['funcao_codigo'] = servidor.get('codFuncao')[3:]
            servidor_atualizado_kwargs['funcao_atividade'] = args.get('funcao_atividade').id

        elif data_inicio_funcao_siape and ultima_funcao_suap and data_inicio_funcao_siape == ultima_funcao_suap.data_inicio_funcao:
            ServidorFuncaoHistorico.objects.filter(id=ultima_funcao_suap.id).update(
                nivel=servidor.get('codFuncao')[3:],
                funcao_id=args.get('funcao').id,
                setor_id=setor_exercicio.id,
                atividade_id=args.get('funcao_atividade').id,
            )
            servidor_atualizado_kwargs['funcao_id'] = args.get('funcao').id
            servidor_atualizado_kwargs['funcao_codigo'] = servidor.get('codFuncao')[3:]
            servidor_atualizado_kwargs['funcao_atividade'] = args.get('funcao_atividade').id
        elif not data_inicio_funcao_siape and not data_inicio_nova_funcao_siape and servidor_atualizado.funcao:
            # Zerando o registro nos atributos em servidor
            servidor_atualizado_kwargs['funcao_id'] = None
            servidor_atualizado_kwargs['funcao_codigo'] = ''
            servidor_atualizado_kwargs['funcao_atividade'] = None

        if servidor_atualizado_kwargs:
            Servidor.objects.filter(id=servidor_atualizado.id).update(**servidor_atualizado_kwargs)

    def _importar_dependentes(self, servidor: Servidor, lista_dependentes: list[dict]) -> None:
        for dep_data in lista_dependentes:
            cpf_dep = dep_data.get('cpf')
            nome_dep = dep_data.get('nome')
            if not cpf_dep or not nome_dep:
                continue
            if not cpf_valido(cpf_dep):
                # CPF inválido não identifica ninguém e não cria pessoa (a higiene o anularia): o dependente fica de fora
                logger.warning(f'Dependente {nome_dep} do servidor {servidor.matricula} não importado: CPF inválido.')
                continue

            grau = None
            cod_grau = dep_data.get('codGrauParentesco')
            if cod_grau:
                grau, _ = GrauParentesco.objects.get_or_create(
                    codigo=cod_grau,
                    defaults={'nome': normalizar_nome_proprio(dep_data.get('nomeGrauParentesco') or cod_grau)},
                )

            cpf_masked = mask_cpf(cpf_dep)
            matricula_ps = re.sub(r'\D', '', cpf_dep)
            nome_normalizado = normalizar_nome_proprio(nome_dep)

            # PrestadorServico.matricula é unique — lookup seguro. Do dependente o SIAPE só traz nome e CPF:
            # reusa a pessoa existente e só completa o que estiver vazio.
            prestador = PrestadorServico.objects.filter(matricula=matricula_ps).first()
            if not prestador:
                pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar({'cpf': cpf_masked, 'nome': nome_normalizado}, Politica.PREENCHER)
                prestador = PrestadorServico(matricula=matricula_ps, pessoa_fisica=pessoa_fisica, ativo=True)
                prestador.save()

            dependente, _ = Dependente.objects.update_or_create(
                usuario_externo=prestador,
                defaults={
                    'servidor': servidor,
                    'grau_parentesco': grau,
                    'codigo_condicao': dep_data.get('codCondicao'),
                },
            )

            beneficios_raw = dep_data.get('arrayBeneficios') or {}
            lista_ben = beneficios_raw.get('Beneficio', [])
            if isinstance(lista_ben, dict):
                lista_ben = [lista_ben]
            for ben_data in lista_ben:
                cod_ben = ben_data.get('codBeneficio')
                if not cod_ben:
                    continue
                beneficio, _ = Beneficio.objects.get_or_create(
                    codigo=cod_ben,
                    defaults={'nome': ben_data.get('nomeBeneficio', '')},
                )
                data_inicio_ben = self._str_to_date(ben_data.get('dataInicio'))
                data_fim_str = ben_data.get('dataFim', '00000000')
                data_fim_ben = self._str_to_date(data_fim_str) if data_fim_str != '00000000' else None
                if data_inicio_ben:
                    BeneficioDependente.objects.update_or_create(
                        dependente=dependente,
                        beneficio=beneficio,
                        defaults={
                            'data_inicio': data_inicio_ben,
                            'data_termino': data_fim_ben,
                        },
                    )

        qtde_ir = servidor.dependentes_ir.count()
        Servidor.objects.filter(pk=servidor.pk).update(qtde_depend_ir=qtde_ir)

    def atualizar_ferias_afastamentos(self, cpf, mes_inicio=1, mes_fim=12, ano_inicio=None, ano_fim=None):
        if not ano_inicio:
            ano_inicio = date.today().year - 1
        if not ano_fim:
            ano_fim = date.today().year + 1
        try:
            count = 1
            interar = True
            dados_afastamentos = None
            while interar:
                try:
                    dados_afastamentos = self.get_afastamento_historico(
                        cpf, mes_inicio=mes_inicio, mes_fim=mes_fim, ano_inicio=ano_inicio, ano_fim=ano_fim
                    )
                    interar = False
                except Exception:
                    if count < 3:
                        count += 1
                    else:
                        interar = False
            if dados_afastamentos and Ferias:
                lista_parcelas = dados_afastamentos.get('ferias')
                ferias_atualizadas = {}
                for parcela in lista_parcelas:
                    ferias, created = Ferias.objects.get_or_create(ano=parcela['ferias'].ano, servidor=parcela['ferias'].servidor)
                    parcela['ferias'] = ferias
                    numero_parcela = parcela['numero_parcela']
                    ParcelaFerias.objects.update_or_create(numero_parcela=numero_parcela, ferias=ferias, defaults=parcela)
                    ferias.atualiza_pelo_extrator = False
                    ferias.save()
                    if not created:
                        if ferias_atualizadas.get(ferias.pk):
                            ferias_atualizadas[ferias.pk].append(numero_parcela)
                        else:
                            ferias_atualizadas[ferias.pk] = [numero_parcela]

                for ferias_pk, parcelas in ferias_atualizadas.items():
                    ParcelaFerias.objects.filter(ferias__pk=ferias_pk).exclude(numero_parcela__in=parcelas).delete()

                lista_afastamentos = dados_afastamentos.get('afastamentos')
                for dado_afastamento in lista_afastamentos:
                    servidor = dado_afastamento['servidor']
                    afastamento = dado_afastamento['afastamento']
                    data_inicio = dado_afastamento['data_inicio']
                    ServidorAfastamento.objects.update_or_create(
                        servidor=servidor, afastamento=afastamento, data_inicio=data_inicio, defaults=dado_afastamento
                    )
        except Exception:
            raise

    # '''
    # Setando setores do servidor
    # '''
    # def _set_setores(self, servidor):
    #
    #     '''
    #     Precisamos tratar os setores:
    #      - campo setor em Funcionario
    #         pelos testes realizados, é o mesmo setor de exercício
    #
    #      - campo setor_lotacao em Funcionario
    #
    #      - campo setor_funcao em Funcionario
    #         pelos testes realizados, é o mesmo setor de exercício
    #
    #      - campo setor_exercicio em Servidor
    #
    #     Verificar os históricos:
    #      - ServidorSetorHistorico
    #      - ServidorSetorLotacaoHistorico
    #     '''
    #
    #
    #
    #     return

    def importacao_servidor_completo(self, cpf):
        try:
            self.importacao_servidor(cpf)
        except Exception:
            return False
        return True

    """ Importação completa."""

    def importacao_completa(self):
        #
        # ??? 236 = COSINF

        self.get_lista_uorgs(236)

        lista = self.get_lista_servidores(self.lista_uorgs[0][0])

        cpfs_errors = []

        for s in lista.get('236').get('servidores').Servidor:
            importou = self.importacao_servidor_completo(s.cpf)
            if not importou:
                cpfs_errors.append(s.cpf)
                continue
