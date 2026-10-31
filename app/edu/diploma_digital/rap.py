from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import jsonschema
import qrcode
from django.conf import settings
from requests.exceptions import RequestException
from requests_toolbelt import MultipartEncoder

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from djtools.storages import cache_file, get_temp_storage, upload_temporary_file
from djtools.utils import PDFResponse, XmlResponse, mask_cnpj, mask_cpf, requests
from edu.models import Modalidade
from edu.models.arquivos import AlunoArquivo
from edu.models.cadastros_gerais import Cidade, NaturezaParticipacao
from edu.models.diploma_digital import HistoricoEscolarParcial
from edu.models.diplomas import AssinaturaDigital, RegistroEmissaoDiploma, SincronizacaoAssinaturaDigital
from edu.models.regulacao import AtoRegulatorioCurso, Credenciamento, TramitacaoProcessoEMEC
from rh.models import UnidadeOrganizacional

from . import status

if TYPE_CHECKING:
    from edu.models.alunos import Aluno
    from edu.models.cursos import CursoCampus
    from edu.models.polos import Polo

ESQUEMA_DOCUMENTACAO = 'edu/diploma_digital/schemas/0.24.11/DocumentacaoAcademica.json'
ESQUEMA_HISTORICO_FINAL = 'edu/diploma_digital/schemas/0.24.11/HistoricoEscolarFinal.json'
ESQUEMA_HISTORICO_PARCIAL = 'edu/diploma_digital/schemas/0.24.11/HistoricoEscolarParcial.json'
ESQUEMA_ARQUIVO_FISCALIZACAO_EMISSORA = 'edu/diploma_digital/schemas/0.24.11/ArquivoFiscalizacaoEmissora.json'
ESQUEMA_DIPLOMA = 'edu/diploma_digital/schemas/0.24.11/DiplomaDigital.json'
ESQUEMA_REPRESENTACAO_VISUAL = 'edu/diploma_digital/schemas/0.24.11/RepVisual.json'

"""
"TermoResponsabilidade",
"DocumentoIdentidadeDoAluno",
"ProvaConclusaoEnsinoMedio",
"HistoricoEscolar",
"ProvaColacao",
"ComprovacaoEstagioCurricular",
"CertidaoNascimento",
"CertidaoCasamento",
"TituloEleitor",
"AtoNaturalizacao",
"Outros"

https://www.jsonschemavalidator.net/
http://validadordiplomadigital.mec.gov.br/
https://avepdf.com/pt/convert-to-pdfa
https://demo.verapdf.org/

"""
ERRO_CONECTIVIDADE = 998
STATUS = {status_doc[0]: status_doc[1] for status_doc in AssinaturaDigital.SITUACAO_CHOICES}
STATUS_ERRO = {status_error[0]: status_error[1] for status_error in status.STATUS_ERRO_DOCUMENTO}
MOCK = False

logger = logging.getLogger(__name__)


def _is_valid(texto, pattern='^[!-ÿ]{1}[ -ÿ]{0,}[!-ÿ]{1}|[!-ÿ]{1}$'):
    import re

    occurrences = re.findall(pattern, texto)
    return len(occurrences) == 1


def _titulacao(titulacao):
    if titulacao:
        if titulacao.lower().startswith('gra'):
            return 'Graduação'
        elif titulacao.lower().startswith('esp'):
            return 'Especialização'
        elif titulacao.lower().startswith('mes'):
            return 'Mestrado'
        elif titulacao.lower().startswith('dou'):
            return 'Doutorado'
    return 'Graduação'


class _AtosRegulatorios(NamedTuple):
    autorizacao: AtoRegulatorioCurso | None
    reconhecimento: AtoRegulatorioCurso | None
    tramitacao_emec: TramitacaoProcessoEMEC | None
    renovacao_reconhecimento: AtoRegulatorioCurso | None
    credenciamento: Credenciamento | None
    recredenciamento: Credenciamento | None
    renovacao_recredenciamento: Credenciamento | None


def _modalidade_ead(aluno: Aluno) -> bool:
    if aluno.is_qacademico():
        return aluno.get_historico_legado(final=True)['ead']
    return aluno.matriz.natureza_participacao_id == NaturezaParticipacao.EAD


def _erros_polo_ou_curso(aluno: Aluno) -> list[str]:
    polo = aluno.polo
    if not polo:
        return [] if aluno.curso_campus.codigo_emec else ['Código e-MEC do curso']
    erros = []
    if not all((polo.cidade, polo.cep, polo.logradouro, polo.numero, polo.bairro)):
        erros.append(f'Endereço do Polo "{polo}" relacionado ao curso do aluno')
    if not polo.codigo_censup:
        erros.append(f'Código e-MEC do Polo "{polo}"')
    return erros


def _erros_colacao_e_enade(aluno: Aluno) -> list[str]:
    if not aluno.matriz_id:
        return []
    erros = []
    if not aluno.get_participacao_colacao_grau():
        erros.append('Registro da Colação de Grau')
    registro_convocacao_enade = aluno.get_convocacoes_enade(ignorar_ausencia=True).last()
    try:
        if registro_convocacao_enade is None:
            erros.append('Registro do ENADE')
        elif registro_convocacao_enade.get_situacao_para_diploma_digital() is None:
            erros.append('Situação do ENADE')
    except Exception as e:
        erros.append(str(e))
    return erros


def _erros_identificacao(aluno: Aluno) -> list[str]:
    erros = []
    if aluno.numero_rg is None:
        erros.append('Número do documento de identidade (RG)')
    if aluno.uf_emissao_rg is None:
        erros.append('UF de emissão do documento de identidade (RG)')
    if aluno.naturalidade is None and aluno.nacionalidade == 'Brasileira':
        erros.append('Naturalidade do aluno')
    return erros


def _erros_enderecos_e_atos(aluno: Aluno, reitoria: UnidadeOrganizacional, atos: _AtosRegulatorios) -> list[str]:
    erros = []
    if aluno.curso_campus.diretoria.setor.uo.numero is None:
        erros.append(f'Número do endereço do campus {aluno.curso_campus.diretoria.setor.uo}.')
    if reitoria.numero is None:
        erros.append('Número do endereço da reitoria.')
    if atos.autorizacao is None:
        erros.append('Cadastro da autorização do curso')
    if atos.reconhecimento is None and atos.tramitacao_emec is None:
        erros.append('Cadastro do reconhecimento do curso')
    if atos.credenciamento is None:
        erros.append('Cadastro do credenciamento da instituição')
    renovacao = atos.renovacao_reconhecimento
    if renovacao and renovacao.veiculo_publicacao and not renovacao.data_publicacao:
        erros.append('A data de publicação da renovação do reconhecimento deve ser informada quando o meio de publicação for informado.')
    return erros


def _erros_pasta_documental(aluno: Aluno) -> list[str]:
    if not aluno.curso_campus.modalidade.grupoarquivoobrigatorio_set.all().exists():
        return []
    if not aluno.alunoarquivo_set.all().exists():
        return ['Pasta documental vazia']
    if not aluno.possui_todos_documentos_obrigatorios():
        return ['Documentos obrigatórios na pasta documental']
    return []


def _pdfa_em_base64(aluno_arquivo: AlunoArquivo) -> str:
    """Conteúdo do arquivo convertido para PDF/A, em base64; o PDF/A temporário é removido logo após a leitura (#17602)."""
    caminho_pdfa = aluno_arquivo.to_pdfa()
    try:
        with open(caminho_pdfa, 'rb') as arquivo:
            return base64.b64encode(arquivo.read()).decode()
    finally:
        Path(caminho_pdfa).unlink(missing_ok=True)


def _documentos_comprobatorios(aluno: Aluno, erros: list[str]) -> tuple[list[dict], list[int]]:
    """Documentos obrigatórios da pasta documental no formato do RAP; o que não puder ser convertido vira erro em ``erros``."""
    documentos_aluno = []
    ids_documentos_alunos = []
    for aluno_arquivo in aluno.get_documentos_obrigatorios():
        ids_documentos_alunos.append(aluno_arquivo.id)
        try:
            documento = {
                'Documento': {
                    'Tipo': aluno_arquivo.get_tipo_diploma_exibicao(),
                    'Observacoes': aluno_arquivo.tipo.nome,
                    'Arquivo': _pdfa_em_base64(aluno_arquivo),
                }
            }
            documentos_aluno.append(documento)
        except Exception as e:
            erros.append(f'O arquivo {aluno_arquivo.tipo} contido na pasta documental não pôde ser utilizado. Motivo: {e}')
    return documentos_aluno, ids_documentos_alunos


def _erros_coordenacao_e_aacc(aluno: Aluno) -> list[str]:
    erros = []
    if aluno.curso_campus.coordenador is None:
        erros.append('Coordenador do curso não informado.')
    if aluno.curso_campus.get_titulacao_coordenador() is None:
        erros.append('Titulação do coordenador do curso não informada.')
    for aacc in aluno.atividadecomplementar_set.filter(deferida=True):
        if not _is_valid(aacc.descricao):
            erros.append(f'Descrição da Atividade Complementar "{aacc.descricao}" contém caracteres inválidos.')
    return erros


def _grau_conferido(curso_campus: CursoCampus) -> str:
    if curso_campus.is_licenciatura():
        return 'Licenciatura'
    if curso_campus.modalidade_id in [Modalidade.ENGENHARIA, Modalidade.BACHARELADO]:
        return 'Bacharelado'
    return 'Tecnólogo'


def _naturalidade(aluno: Aluno) -> dict | str:
    if not aluno.naturalidade_id:
        return 'Naturalidade_Indisponivel'
    if aluno.naturalidade.estado_id:
        return {
            'CodigoMunicipio': f'{aluno.naturalidade.codigo}',
            'NomeMunicipio': aluno.naturalidade.nome,
            'UF': aluno.naturalidade.estado.get_sigla(),
        }
    return {'NomeMunicipioEstrangeiro': aluno.naturalidade.nome}


def _diplomado(aluno: Aluno) -> dict:
    return {
        'ID': str(aluno.pk),
        'Nome': aluno.pessoa_fisica.nome,
        'Sexo': aluno.pessoa_fisica.sexo,
        'Nacionalidade': aluno.nacionalidade,
        'Naturalidade': _naturalidade(aluno),
        'CPF': aluno.pessoa_fisica.cpf.replace('-', '').replace('.', ''),
        'RG': {
            'Numero': aluno.numero_rg.replace('-', '').replace('.', ''),
            'UF': aluno.uf_emissao_rg.get_sigla(),
        },
        'DataNascimento': aluno.pessoa_fisica.nascimento_data.strftime('%Y-%m-%d'),
    }


def _endereco(uo: UnidadeOrganizacional) -> dict:
    cidade = Cidade.get_cidade_by_municipio(uo.municipio)
    return {
        'NomeMunicipio': cidade.nome,
        'Número': uo.numero,
        'CodigoMunicipio': cidade.codigo,
        'Bairro': uo.bairro,
        'Logradouro': uo.endereco,
        'CEP': uo.cep.replace('.', '').replace('-', ''),
        'UF': uo.municipio.uf,
    }


def _ato_curso(ato: AtoRegulatorioCurso | None) -> dict | None:
    if not ato:
        return None
    return {
        'Tipo': ato.tipo_documento,
        'Numero': ato.get_numero_com_orgao(),
        'Data': ato.data.strftime('%Y-%m-%d'),
        'VeiculoPublicacao': ato.veiculo_publicacao or None,
        'DataPublicacao': ato.veiculo_publicacao and ato.data_publicacao.strftime('%Y-%m-%d') or None,
        'SecaoPublicacao': ato.veiculo_publicacao and ato.secao_publicacao or None,
        'PaginaPublicacao': ato.veiculo_publicacao and ato.pagina_publicacao or None,
    }


def _tramitacao_emec(tramitacao: TramitacaoProcessoEMEC | None) -> dict | None:
    if not tramitacao:
        return None
    return {
        'InformacoesTramitacaoEMEC': {
            'DataCadastro': tramitacao.data_cadastro.strftime('%Y-%m-%d'),
            'DataProtocolo': tramitacao.data_protocolo.strftime('%Y-%m-%d'),
            'NumeroProcesso': tramitacao.numero_processo,
            'TipoProcesso': tramitacao.tipo_processo,
        }
    }


def _ato_credenciamento(credenciamento: Credenciamento | None) -> dict | None:
    if not credenciamento:
        return None
    return {
        'Tipo': credenciamento.tipo_ato,
        'Numero': credenciamento.numero_ato,
        'Data': credenciamento.data_ato.strftime('%Y-%m-%d'),
        'VeiculoPublicacao': credenciamento.veiculo_publicacao,
        'DataPublicacao': credenciamento.data_publicacao.strftime('%Y-%m-%d'),
        'SecaoPublicacao': credenciamento.secao_publicacao,
        'PaginaPublicacao': credenciamento.pagina_publicacao,
    }


def _polo(polo: Polo | None) -> dict | None:
    if not polo:
        return None
    return {
        'Nome': polo.descricao,
        'Endereco': {
            'Logradouro': polo.logradouro,
            'Numero': polo.numero,
            'Complemento': '-',
            'Bairro': polo.bairro,
            'CodigoMunicipio': polo.cidade.codigo,
            'NomeMunicipio': polo.cidade.nome,
            'UF': polo.cidade.estado.get_sigla(),
            'CEP': polo.cep.replace('.', '').replace('-', ''),
        },
        'CodigoEMEC': polo.codigo_censup,
    }


def _dados_curso(aluno: Aluno, ead: bool, atos: _AtosRegulatorios) -> dict:
    curso_campus = aluno.curso_campus
    return {
        'NomeCurso': curso_campus.descricao_historico,
        'CodigoCursoEMEC': curso_campus.codigo_emec,
        'NomeHabilitacao': [curso_campus.descricao_historico],  # TODO
        'Modalidade': 'EAD' if ead else 'Presencial',
        'TituloConferido': {
            'OutroTitulo': aluno.pessoa_fisica.sexo == 'M' and curso_campus.titulo_certificado_masculino or curso_campus.titulo_certificado_feminino
        },
        'GrauConferido': _grau_conferido(curso_campus),
        'EnderecoCurso': {**_endereco(curso_campus.diretoria.setor.uo), 'Complemento': '-'},
        'Polo': _polo(aluno.polo),
        'Autorizacao': _ato_curso(atos.autorizacao),
        'Reconhecimento': _ato_curso(atos.reconhecimento) or _tramitacao_emec(atos.tramitacao_emec),
        'RenovacaoReconhecimento': _ato_curso(atos.renovacao_reconhecimento),
    }


def _ies_emissora(reitoria: UnidadeOrganizacional, atos: _AtosRegulatorios) -> dict:
    nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    cnpj = reitoria.cnpj.replace('.', '').replace('/', '').replace('-', '')
    return {
        'Nome': nome_instituicao,
        'CodigoMEC': Configuracao.get_valor_por_chave('edu', 'codigo_mec') or '1082',
        'CNPJ': cnpj,
        'Endereco': {**_endereco(reitoria), 'Complemento': '-'},
        'Credenciamento': _ato_credenciamento(atos.credenciamento),
        'Recredenciamento': _ato_credenciamento(atos.recredenciamento),
        'RenovacaoDeRecredenciamento': _ato_credenciamento(atos.renovacao_recredenciamento),
        'Mantenedora': {'CNPJ': cnpj, 'RazaoSocial': nome_instituicao, 'Endereco': _endereco(reitoria)},
    }


def _filiacao(aluno: Aluno) -> list[dict]:
    genitores = ((aluno.nome_mae, 'F'), (aluno.nome_pai, 'M'))
    return [{'Genitor': {'Nome': nome, 'NomeSocial': nome, 'Sexo': sexo}} for nome, sexo in genitores if nome]


def _dados_documentacao(
    registro: RegistroEmissaoDiploma, ead: bool, atos: _AtosRegulatorios, reitoria: UnidadeOrganizacional, historico: dict, documentos: list[dict]
) -> dict:
    """Payload da documentação acadêmica enviado ao RAP (esquema ``ESQUEMA_DOCUMENTACAO``)."""
    aluno = registro.aluno
    return {
        'meta': {
            'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
            'yourNumber': f'DOC{registro.pk}',
            'dltId': 'ethereum',
            'docType': 'academic_doc_mec_degree',
            'mimeType': 'text/xml',
            'groupId': f'REG{registro.pk}',
            'clientSignature': f'REG{registro.pk}',
        },
        'data': {
            'Versao': '1.05',
            'ambiente': 'Homologação' if settings.DEBUG else 'Produção',
            'RegistroReq': {
                'DadosDiploma': {
                    'Diplomado': _diplomado(aluno),
                    'DadosCurso': _dados_curso(aluno, ead, atos),
                    'IesEmissora': _ies_emissora(reitoria, atos),
                },
                'DadosPrivadosDiplomado': {'Filiacao': _filiacao(aluno), 'HistoricoEscolar': historico},
                'DocumentacaoComprobatoria': documentos,
            },
        },
    }


def _remover_campos_vazios(dados_diploma: dict) -> None:
    """Remove do payload os atos ausentes e os dados de publicação dos atos sem veículo de publicação."""
    ies = dados_diploma['IesEmissora']
    curso = dados_diploma['DadosCurso']
    for chave, dados in (('Recredenciamento', ies), ('RenovacaoDeRecredenciamento', ies), ('Polo', curso), ('RenovacaoReconhecimento', curso)):
        if dados[chave] is None:
            del dados[chave]
    for chave in ('Autorizacao', 'Reconhecimento', 'RenovacaoReconhecimento'):
        ato = curso.get(chave)
        if ato and 'VeiculoPublicacao' in ato and ato['VeiculoPublicacao'] is None:
            for campo in ('DataPublicacao', 'SecaoPublicacao', 'PaginaPublicacao', 'VeiculoPublicacao'):
                del ato[campo]


class MockedResponse:
    def __init__(self):
        self.text = '{"documentId":1}'


class AssinadorDigital:
    def __init__(self, debug=settings.DEBUG):
        self.token = None
        self.debug = debug

    def log(self, data):
        if self.debug:
            line = f'[{datetime.now()}] - {data}'
            logger.info(line)
            os.makedirs('deploy/logs/edu', exist_ok=True)
            with open('deploy/logs/edu/rap.log', 'a') as file:
                file.write(line)
                file.write('\n-------\n')

    def headers(self, multipart_encoder=None):
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        if self.token is None:
            url = f'{rap_api_url}/api/users/auth'
            data = {
                'email': Configuracao.get_valor_por_chave('edu', 'rap_api_user'),
                'password': Configuracao.get_valor_por_chave('edu', 'rap_api_password'),
            }
            self.log(url)
            response = requests.post(
                url,
                json=data,
                timeout=settings.REQUESTS_TIMEOUT,
            ).json()
            self.log(response)
            self.token = response.get('accessToken', None)
        data = {'Authorization': f'Bearer {self.token}'}
        if multipart_encoder:
            data['Content-Type'] = multipart_encoder.content_type
        return data

    def listar_documentos(self):
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents?page=0&limit=10'
        self.log(url)
        response = self.get_response(url)
        self.log(response.text)
        return json.loads(response.text)

    def registrar_erro_cadastro(self, assinatura_digital, detalhe, aditionalInfo=None):
        self.log(f'{assinatura_digital.id} - {detalhe}')
        detalhe = detalhe[0:255]
        sincronizacao = SincronizacaoAssinaturaDigital.objects.filter(assinatura_digital=assinatura_digital).order_by('-id').first()
        if sincronizacao is None or sincronizacao.detalhe != detalhe:
            SincronizacaoAssinaturaDigital.objects.create(assinatura_digital=assinatura_digital, detalhe=detalhe, informacao_adicional=aditionalInfo)

    def consultar_documento(self, assinatura_digital: AssinaturaDigital | HistoricoEscolarParcial, tipo: str = 'rap') -> int | None:
        try:
            id_attr = f'id_{tipo}'
            status_attr = f'status_{tipo}'
            if MOCK:
                return 10
            rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
            url = f'{rap_api_url}/api/documents/{getattr(assinatura_digital, id_attr)}/'
            self.log(url)
            response = self.get_response(url)
            self.log(response.text)
            codigo_retorno = json.loads(response.text).get('currentState')
            if isinstance(assinatura_digital, AssinaturaDigital) and codigo_retorno is not None:
                if codigo_retorno != getattr(assinatura_digital, status_attr):
                    detalhe = f'Alteração da situação do documento {getattr(assinatura_digital, id_attr)}: {STATUS[codigo_retorno]}.'
                    self.log(f'{assinatura_digital.id} - {detalhe}')
                    if codigo_retorno in STATUS_ERRO:
                        aditionalInfo = json.loads(response.text).get('aditionalInfo')
                        self.registrar_erro_cadastro(assinatura_digital=assinatura_digital, detalhe=detalhe, aditionalInfo=aditionalInfo)
                    else:
                        SincronizacaoAssinaturaDigital.objects.create(assinatura_digital=assinatura_digital, detalhe=detalhe)
                    setattr(assinatura_digital, status_attr, codigo_retorno)
                    assinatura_digital.save()
        # `get_response` levanta o ConnectionError embutido em resposta não-200; a falha de rede
        # vem do requests, que não herda dele (#17448).
        except ConnectionError, RequestException:
            return ERRO_CONECTIVIDADE
        return codigo_retorno

    def excluir_documento(self, id):
        if MOCK:
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/'
        self.log(url)
        response = requests.delete(
            url,
            timeout=settings.REQUESTS_TIMEOUT,
        )
        self.log(response.text)
        return json.loads(response.text)

    def revogar_documento(self, id):
        if MOCK:
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/revoke'
        self.log(url)
        response = requests.post(
            url,
            headers=self.headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        )
        self.log(response.text)
        try:
            return json.loads(response.text)
        except Exception as e:
            return {'error_message': str(e)}

    def consultar_status_documento(self, id):
        if MOCK:
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/state'
        self.log(url)
        response = self.get_response(url)
        self.log(response.text)
        status = []
        data = json.loads(response.text)
        for signature in data['signatures']:
            substitute = (
                '{} - {}'.format(mask_cpf(signature['substituteSigner']['identification']), signature['substituteSigner']['name'])
                if signature['substituteSigner']
                else ''
            )
            if len(signature['signerId']) == 11:
                documento = mask_cpf(signature['signerId'])
            else:
                documento = mask_cnpj(signature['signerId'])
            status.append(
                {
                    'documento': documento,
                    'nome': signature['signer'],
                    'tipo': signature['archivingSignature'] and 'ARQUIVAMENTO' or 'NORMAL',
                    'situacao': signature['signatureState'] == 2 and 'ASSINADO' or 'PENDENTE',
                    'substituto': substitute,
                }
            )
        return status

    def reprocessar_documento(self, id, command='restart-processing'):
        if MOCK:
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/{command}'
        self.log(url)
        response = requests.post(
            url,
            headers=self.headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        )
        self.log(response.text)
        return json.loads(response.text)

    def baixar_xml(self, id, as_http_response=False):
        if MOCK:
            return '<DadosDiploma id="1"></DadosDiploma>'
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/files/signedDocument'
        response = self.get_response(url)
        if as_http_response:
            return XmlResponse(response.text)
        else:
            return response.text

    def gerar_qr_code_historico(self, id, rap_id, nome_view):
        codigo_validacao = self.baixar_xml(rap_id).split('<CodigoValidacao>')[1].split('</CodigoValidacao>')[0]
        nome_arquivo_qrcode = f'historico_digital_{codigo_validacao}.png'
        url_validacao = f'{settings.SITE_URL}/edu/{nome_view}/{id}/{codigo_validacao}/'
        qr_code_path = os.path.join(settings.TEMP_DIR, nome_arquivo_qrcode)
        img = qrcode.make(url_validacao)
        img.save(qr_code_path)
        img_url = get_temp_storage().url(upload_temporary_file(qr_code_path))
        qr = {'url': url_validacao, 'image': img_url, 'code': codigo_validacao}
        return qr

    def baixar_pdf(self, id, as_http_response=False):
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/{id}/files/signedDocument'
        response = self.get_response(url)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.writelines(response)
            pdf_file_path = f.name
        if as_http_response:
            try:
                with open(pdf_file_path, 'rb') as f:
                    return PDFResponse(f.read())
            finally:
                os.unlink(pdf_file_path)
        else:
            return pdf_file_path

    def get_response(self, url):
        response = requests.get(
            url,
            headers=self.headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        )
        if response.status_code == 200:
            return response
        else:
            raise ConnectionError('Não foi possível conectar ao serviço RAP. Por favor, tente novamente em alguns minutos.')

    def sincronizar(self, assinatura_digital):
        documentos = (
            assinatura_digital.status_documentacao_academica_digital,
            assinatura_digital.status_historico_escolar,
            assinatura_digital.status_dados_diploma_digital,
            assinatura_digital.status_representacao_diploma_digital,
        )
        if all(s == status.DOCUMENTO_VALIDO for s in documentos):
            registro = assinatura_digital.registro_emissao_diploma
            if not registro.is_finalizado():
                registro.situacao = RegistroEmissaoDiploma.FINALIZADO
                registro.save()
            if not assinatura_digital.concluida:
                assinatura_digital.concluida = True
                assinatura_digital.save()

        elif (
            assinatura_digital.id_documentacao_academica_digital == 0
            or assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_DADOS
        ):
            self.enviar_documentacao_academica(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DOCUMENTACAO:
            self.consultar_documentacao_academica(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_HISTORICO:
            self.enviar_historico_escolar(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_HISTORICO:
            self.consultar_historico_escolar(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_DADOS_DIPLOMA:
            self.enviar_dados_diploma(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DIPLOMA:
            self.consultar_dados_diploma(assinatura_digital)
        elif assinatura_digital.registro_emissao_diploma.situacao == RegistroEmissaoDiploma.AGUARDANDO_CONFECCAO_DIPLOMA:
            self.consultar_representacao_diploma(assinatura_digital)

    def consultar_documentacao_academica(self, assinatura_digital):
        codigo_retorno = self.consultar_documento(assinatura_digital, 'documentacao_academica_digital')
        if codigo_retorno is None:
            SincronizacaoAssinaturaDigital.objects.create(
                assinatura_digital=assinatura_digital, detalhe='Arquivo da documentação acadêmica em criação.'
            )
        elif codigo_retorno == status.DOCUMENTO_VALIDO or (
            settings.DEBUG and codigo_retorno in (status.ERRO_INICIALIZANDO_REGISTRO, status.ERRO_FINALIZANDO_REGISTRO)
        ):
            self.enviar_historico_escolar(assinatura_digital)

    def consultar_historico_escolar(self, assinatura_digital):
        codigo_retorno = self.consultar_documento(assinatura_digital, 'historico_escolar')
        if codigo_retorno is None:
            SincronizacaoAssinaturaDigital.objects.create(assinatura_digital=assinatura_digital, detalhe='Arquivo do histórico escolar em criação.')
        elif codigo_retorno == status.DOCUMENTO_VALIDO or (
            settings.DEBUG and codigo_retorno in (status.ERRO_INICIALIZANDO_REGISTRO, status.ERRO_FINALIZANDO_REGISTRO)
        ):
            assinatura_digital = assinatura_digital.gerar_representacao_historico()
            self.enviar_dados_diploma(assinatura_digital)

    def consultar_dados_diploma(self, assinatura_digital):
        # self.consultar_documento(assinatura_digital, 'documentacao_academica_digital')
        codigo_retorno = self.consultar_documento(assinatura_digital, 'dados_diploma_digital')
        if codigo_retorno is None:
            SincronizacaoAssinaturaDigital.objects.create(assinatura_digital=assinatura_digital, detalhe='Arquivo dos dados do diploma em criação.')
        elif codigo_retorno == status.DOCUMENTO_VALIDO or (
            settings.DEBUG and codigo_retorno in (status.ERRO_INICIALIZANDO_REGISTRO, status.ERRO_FINALIZANDO_REGISTRO)
        ):
            assinatura_digital = assinatura_digital.gerar_representacao_visual()
            self.enviar_representacao_diploma(assinatura_digital)

    def consultar_representacao_diploma(self, assinatura_digital):
        # self.consultar_documento(assinatura_digital, 'documentacao_academica_digital')
        # self.consultar_documento(assinatura_digital, 'dados_diploma_digital')
        codigo_retorno = self.consultar_documento(assinatura_digital, 'representacao_diploma_digital')
        if codigo_retorno == status.DOCUMENTO_VALIDO or (
            settings.DEBUG and codigo_retorno in (status.ERRO_INICIALIZANDO_REGISTRO, status.ERRO_FINALIZANDO_REGISTRO)
        ):
            registro = assinatura_digital.registro_emissao_diploma
            registro.situacao = RegistroEmissaoDiploma.FINALIZADO
            registro.save()
            assinatura_digital.concluida = True
            assinatura_digital.save()
            registro.enviar_por_email()

    def get_dados_historico_escolar(self, aluno, data_emissao, data_expedicao):
        erros = []
        dados_enade = []
        disciplinas = []
        aaccs = []
        estagios = []
        conceito = False
        # dados do ENADE
        if aluno.is_qacademico():
            situacao_enade = None
            historico = aluno.get_historico_legado(final=True)
            data_colacao_grau = historico['data_colacao_grau']
            if historico['convocacoes']:
                for convocacao_enade in historico['convocacoes']:
                    situacao_enade = convocacao_enade['situacao_para_diploma_digital']
                    if situacao_enade:
                        ano_enade = convocacao_enade['ano_letivo_enade']
                        if situacao_enade != 'Ingressante / Participante':
                            MOTIVOS_DISPENSA_RAP = [
                                'Estudante não habilitado ao Enade em razão do calendário do ciclo avaliativo',
                                'Estudante não habilitado ao Enade em razão da natureza do projeto pedagógico do curso',
                            ]
                            if situacao_enade in MOTIVOS_DISPENSA_RAP:
                                dados_enade.append(
                                    {
                                        'SituacaoENADE': {
                                            'NaoHabilitado': {
                                                'Condicao': convocacao_enade['tipo_convocacao'],
                                                'Edicao': str(ano_enade),
                                                'Motivo': situacao_enade,
                                            }
                                        }
                                    }
                                )
                            else:
                                dados_enade.append(
                                    {
                                        'SituacaoENADE': {
                                            'NaoHabilitado': {
                                                'Condicao': convocacao_enade['tipo_convocacao'],
                                                'Edicao': str(ano_enade),
                                                'OutroMotivo': situacao_enade,
                                            }
                                        }
                                    }
                                )
                        else:
                            dados_enade.append(
                                {'SituacaoENADE': {'Habilitado': {'Condicao': convocacao_enade['tipo_convocacao'], 'Edicao': str(ano_enade)}}}
                            )
        else:
            conceito = aluno.matriz.estrutura.is_lancamento_conceito()
            historico = aluno.get_historico(final=True, ordernar_por=2)
            data_colacao_grau = aluno.get_data_colacao_grau()
            situacao_enade = None
            convocacoes = aluno.get_convocacoes_enade_diploma()
            try:
                dados_enade = [convocacao.get_situacao_para_diploma_digital() for convocacao in convocacoes]
            except Exception as e:
                erros.append(str(e))

        # Disciplinas
        for componentes in historico['grupos_componentes'].values():
            for componente_curricular in componentes:
                professores = {}
                for _, _, nome, titulacao in componente_curricular.get('professores', []):
                    if nome not in professores:
                        professores[nome] = titulacao
                if not professores:
                    professores['Não Informado'] = 'Graduação'  # TODO Caso a lista esteja vazia, ocorre um erro
                disciplinas.append(
                    {
                        'Disciplina': {
                            'NomeDisciplina': componente_curricular['descricao_componente'].strip(),
                            'CodigoDisciplina': componente_curricular['sigla_componente'].strip().replace(' ', '').replace('/', '-'),
                            'PeriodoLetivo': componente_curricular['ano_periodo_letivo'].replace('/', '.'),
                            'CargaHoraria': [{'HoraRelogio': '{:.2f}'.format(float(componente_curricular['carga_horaria']))}],
                            'ConceitoEspecificoDoCurso' if conceito else 'NotaAteCem': (
                                componente_curricular['media_final_disciplina']
                                if conceito
                                else '{:.2f}'.format(componente_curricular['media_final_disciplina'] or 0)
                            ),
                            'Docentes': [
                                {
                                    'Docente': {
                                        'Nome': nome.strip() if nome else 'Não Informado',
                                        'Titulacao': _titulacao(titulacao) if titulacao else 'Graduação',
                                    }
                                }
                                for nome, titulacao in professores.items()
                            ],
                            'Situacao': {'Aprovado': {'OutraFormaIntegralizacao': 'Dispensado'}}
                            if componente_curricular['situacao_display'] == 'Dispensado'
                            else {
                                'Aprovado': {
                                    'FormaIntegralizacao': 'Aproveitado'
                                    if (componente_curricular['certificada'] or componente_curricular['aproveitada'])
                                    else 'Cursado'  # TODO "Aprovado", "Reprovado", "Trancado"
                                }
                            },
                        }
                    }
                )

        for disciplina in disciplinas:
            if 'OutraFormaIntegralizacao' not in disciplina['Disciplina']['Situacao']['Aprovado']:
                for docente in disciplina['Disciplina']['Docentes']:
                    is_estagio = disciplina['Disciplina']['NomeDisciplina'] == 'ESTÁGIO'
                    if docente['Docente']['Titulacao'] in (None, 'Não Informada') and not is_estagio:
                        erros.append(
                            'Titulação do professor da disciplina "{} - {}" não informada'.format(
                                disciplina['Disciplina']['CodigoDisciplina'], disciplina['Disciplina']['NomeDisciplina']
                            )
                        )

        # Atividades Complementares (AACCs)
        for aacc in aluno.atividadecomplementar_set.filter(deferida=True):
            aaccs.append(
                {
                    'AtividadeComplementar': {
                        'CodigoAtividadeComplementar': f'{aacc.id}',
                        'DataInicio': aacc.data_atividade.strftime('%Y-%m-%d'),
                        'DataFim': aacc.get_data_conclusao_atividade().strftime('%Y-%m-%d'),
                        'DataRegistro': aacc.get_data_deferimento_atividade().strftime('%Y-%m-%d'),
                        'TipoAtividadeComplementar': aacc.tipo.descricao,
                        'Descricao': aacc.descricao,
                        'CargaHorariaEmHoraRelogio': [{'HoraRelogio': f'{float(aacc.carga_horaria):.2f}'}],
                        'DocentesResponsaveisPelaValidacao': [
                            {
                                'Docente': {
                                    'Nome': aluno.curso_campus.coordenador.pessoa.nome,
                                    'Titulacao': _titulacao(aluno.curso_campus.get_titulacao_coordenador())
                                    if aluno.curso_campus.get_titulacao_coordenador()
                                    else None,
                                    'Lattes': aluno.curso_campus.coordenador.pessoa.pessoafisica.get_lattes(),
                                    'CPF': aluno.curso_campus.coordenador.pessoa.pessoafisica.cpf.replace('-', '').replace('.', ''),
                                }
                            }
                        ],
                    }
                }
            )

        for aacc in aaccs:
            for docente in aacc['AtividadeComplementar']['DocentesResponsaveisPelaValidacao']:
                if docente['Docente']['Titulacao'] in (None, 'Não Informada'):
                    erros.append(
                        'Titulação do professor da atividade complementar "{}" não informada'.format(aacc['AtividadeComplementar']['Descricao'])
                    )

        # Estágios
        for pratica_profissional in aluno.get_estagios_historico(True):
            if pratica_profissional.empresa.eh_pessoajuridica():
                concedente = {
                    'RazaoSocial': pratica_profissional.empresa.nome,
                    'CNPJ': pratica_profissional.empresa.get_cpf_ou_cnpj().replace('-', '').replace('.', '').replace('/', ''),
                }
            else:
                concedente = {
                    'Nome': pratica_profissional.empresa.nome,
                    'CPF': pratica_profissional.empresa.get_cpf_ou_cnpj().replace('-', '').replace('.', '').replace('/', ''),
                }

            estagios.append(
                {
                    'Estagio': {
                        'CodigoUnidadeCurricular': f'{pratica_profissional.id}',
                        'DataInicio': pratica_profissional.data_inicio.strftime('%Y-%m-%d'),
                        'DataFim': pratica_profissional.data_fim.strftime('%Y-%m-%d'),
                        'CargaHorariaEmHorasRelogio': [{'HoraRelogio': f'{pratica_profissional.ch_final:.2f}'}],
                        'Descricao': pratica_profissional.get_tipo_display(),
                        'DocentesOrientadores': [
                            {
                                'Docente': {
                                    'Nome': pratica_profissional.orientador.vinculo.pessoa.nome,
                                    'Titulacao': _titulacao(pratica_profissional.orientador.get_titulacao())
                                    if pratica_profissional.orientador.get_titulacao()
                                    else None,
                                    'Lattes': pratica_profissional.orientador.vinculo.pessoa.pessoafisica.get_lattes(),
                                    'CPF': pratica_profissional.orientador.vinculo.pessoa.get_cpf_ou_cnpj().replace('-', '').replace('.', ''),
                                }
                            }
                        ],
                        'Concedente': concedente,
                    }
                }
            )

        for pratica_profissional in estagios:
            for docente in pratica_profissional['Estagio']['DocentesOrientadores']:
                if docente['Docente']['Titulacao'] in (None, 'Não Informada'):
                    erros.append('Titulação do professor do estágio "{}" não informada'.format(pratica_profissional['Estagio']['Descricao']))

        mp = aluno.get_ultima_matricula_periodo(excluir_em_aberto=True)
        if aluno.dt_conclusao_curso:
            situacao = 'Formado'
            detalhe_situacao = {
                'DataConclusaoCurso': aluno.dt_conclusao_curso.strftime('%Y-%m-%d'),
                'DataColacaoGrau': data_colacao_grau.strftime('%Y-%m-%d') if data_colacao_grau else None,
                'DataExpedicaoDiploma': data_expedicao.strftime('%Y-%m-%d'),
            }
            if data_colacao_grau is None:
                erros.append('Data de colação de grau não foi informada.')
        else:
            situacao = mp.situacao.get_situacao_diploma_digital()
            if situacao in ['IntercambioInternacional', 'IntercambioNacional']:
                detalhe_situacao = {}  # informação não disponível no SUAP.
            elif situacao == 'OutraSituacao':
                detalhe_situacao = mp.situacao.descricao
            else:
                detalhe_situacao = None
        situacao_final = situacao if detalhe_situacao is None else {situacao: detalhe_situacao}
        dados_historico_escolar = {
            'CodigoCurriculo': f'CC{aluno.matricula}',
            'HoraEmissaoHistorico': '12:00:00',
            'ElementosHistorico': disciplinas + aaccs + estagios,
            'DataEmissaoHistorico': data_emissao.strftime('%Y-%m-%d'),
            'SituacaoAtualDiscente': {
                'PeriodoLetivo': f'{mp.ano_letivo.ano}.{mp.periodo_letivo}',
                'Situacao': situacao_final,
            },
            'ENADE': dados_enade,
            'CargaHorariaCurso': {'HoraRelogio': '{:.2f}'.format(float(historico['ch_total']))},
            'IngressoCurso': {
                'Data': aluno.data_matricula.strftime('%Y-%m-%d'),
                'FormaAcesso': aluno.forma_ingresso.get_classificacao_diploma_digital_display() or 'Vestibular',
            },
            'CargaHorariaCursoIntegralizada': {'HoraRelogio': '{:.2f}'.format(float(historico['ch_total_cumprida']))},
        }
        return erros, dados_historico_escolar

    def _atos_regulatorios(self, aluno: Aluno) -> _AtosRegulatorios:
        curso_campus = aluno.curso_campus
        autorizacao = self.get_autorizacao(curso_campus)
        reconhecimento = self.get_reconhecimento(curso_campus)
        qs_credenciamento = Credenciamento.objects.filter(natureza_participacao=aluno.get_natureza_participacao_id()).order_by('data_ato')
        return _AtosRegulatorios(
            autorizacao=autorizacao,
            reconhecimento=reconhecimento,
            tramitacao_emec=self.get_tramitacao_emec(curso_campus) if reconhecimento is None else None,
            renovacao_reconhecimento=None if reconhecimento is None else self.get_renovacao_reconhecimento(curso_campus),
            credenciamento=qs_credenciamento.filter(tipo=Credenciamento.CREDECIAMENTO).last(),
            recredenciamento=qs_credenciamento.filter(tipo=Credenciamento.RECREDECIAMENTO).last(),
            renovacao_recredenciamento=qs_credenciamento.filter(tipo=Credenciamento.RENOVACAO_RECREDECIAMENTO).last(),
        )

    def _aguardar_correcao_dados(self, assinatura_digital: AssinaturaDigital, registro: RegistroEmissaoDiploma, detalhe: str) -> None:
        self.registrar_erro_cadastro(assinatura_digital=assinatura_digital, detalhe=detalhe)
        registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_DADOS
        registro.save()

    def _validar_esquema_documentacao(
        self, assinatura_digital: AssinaturaDigital, registro: RegistroEmissaoDiploma, dados_documentacao: dict, apenas_validacao: bool
    ) -> bool:
        """Valida o payload contra o esquema do MEC; devolve ``True`` só quando ele deve seguir para o envio ao RAP."""
        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_DOCUMENTACAO)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=dados_documentacao, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            lista_erros = e.context or [e]
            if apenas_validacao:
                for error in lista_erros:
                    logger.info(error.message, error.json_path)
                return False
            detail = []
            for error in lista_erros:
                detail.append(error.message[0:255] if error.message else 'Erro')
                detail.append(' : ')
                detail.append(error.json_path)
                detail.append(' | ')
            self._aguardar_correcao_dados(assinatura_digital, registro, ''.join(detail))
            return False
        if apenas_validacao:
            del dados_documentacao['data']['RegistroReq']['DocumentacaoComprobatoria']
            logger.info(dados_documentacao)
            return False
        return True

    def _enviar_documentacao_ao_rap(
        self, assinatura_digital: AssinaturaDigital, registro: RegistroEmissaoDiploma, documento_json: str, ids_documentos_alunos: list[int]
    ) -> None:
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/'

        multipart_encoder = MultipartEncoder(fields={'documentType': '4', 'documentData': documento_json, 'documentFile': ''})
        self.log(url)
        response = (
            MOCK
            and MockedResponse()
            or requests.post(
                url,
                data=multipart_encoder,
                headers=self.headers(multipart_encoder),
                timeout=settings.REQUESTS_TIMEOUT,
            )
        )
        self.log(response.text)
        data = json.loads(response.text)
        documentId = data.get('documentId')
        if documentId is None:
            erro = data.get('error') and data.get('error').get('message') or 'Sem retorno do documentID.'
            self.registrar_erro_cadastro(
                assinatura_digital=assinatura_digital,
                detalhe=f'Erro no envio da documentação acadêmica: {erro}',
                aditionalInfo=data.get('aditionalInfo'),
            )
            return
        assinatura_digital.id_documentacao_academica_digital = documentId
        assinatura_digital.save()
        registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DOCUMENTACAO
        registro.save()
        SincronizacaoAssinaturaDigital.objects.create(
            assinatura_digital=assinatura_digital, detalhe=f'Envio da documentação acadêmica. ID: {documentId}.'
        )
        AlunoArquivo.objects.filter(id__in=ids_documentos_alunos).update(em_diploma=True)

    def enviar_documentacao_academica(self, assinatura_digital: AssinaturaDigital, apenas_validacao: bool = False) -> None:
        registro = assinatura_digital.registro_emissao_diploma
        aluno = registro.aluno
        ead = _modalidade_ead(aluno)
        erros = [*_erros_polo_ou_curso(aluno), *_erros_colacao_e_enade(aluno), *_erros_identificacao(aluno)]
        reitoria = UnidadeOrganizacional.objects.suap().get(setor__sigla=get_sigla_reitoria())
        atos = self._atos_regulatorios(aluno)
        erros += _erros_enderecos_e_atos(aluno, reitoria, atos)
        erros += _erros_pasta_documental(aluno)
        documentos_aluno, ids_documentos_alunos = _documentos_comprobatorios(aluno, erros)
        erros += _erros_coordenacao_e_aacc(aluno)
        erros_historico, dados_historico_escolar = self.get_dados_historico_escolar(aluno, registro.data_registro, registro.data_expedicao)
        erros.extend(erros_historico)

        if erros:
            detalhe = 'É necessária a correção das seguintes informações: {}'.format('; '.join(erros))
            if apenas_validacao:
                logger.info(detalhe)
            else:
                self._aguardar_correcao_dados(assinatura_digital, registro, detalhe)
            return

        if not dados_historico_escolar['ENADE']:
            self._aguardar_correcao_dados(assinatura_digital, registro, 'Situação do ENADE')
            return

        dados_documentacao = _dados_documentacao(registro, ead, atos, reitoria, dados_historico_escolar, documentos_aluno)
        _remover_campos_vazios(dados_documentacao['data']['RegistroReq']['DadosDiploma'])
        documento_json = json.dumps(dados_documentacao, ensure_ascii=False)
        if self._validar_esquema_documentacao(assinatura_digital, registro, dados_documentacao, apenas_validacao):
            self._enviar_documentacao_ao_rap(assinatura_digital, registro, documento_json, ids_documentos_alunos)

    def enviar_historico_escolar(self, assinatura_digital, apenas_validacao=False):
        registro = assinatura_digital.registro_emissao_diploma
        reitoria = UnidadeOrganizacional.objects.suap().get(setor__sigla=get_sigla_reitoria())
        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        codigo_mec = Configuracao.get_valor_por_chave('edu', 'codigo_mec') or '1082'

        autorizacao = self.get_autorizacao(registro.aluno.curso_campus)
        if autorizacao is None:
            self.registrar_erro_cadastro(
                assinatura_digital=assinatura_digital, detalhe='Erro no envio do histórico escolar: Autorização não encontrada.'
            )
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_HISTORICO
            registro.save()
            return

        reconhecimento = self.get_reconhecimento(registro.aluno.curso_campus)
        tramitacaoEMEC = None
        renovacao_reconhecimento = None
        if reconhecimento is None:
            tramitacaoEMEC = self.get_tramitacao_emec(registro.aluno.curso_campus)
        else:
            renovacao_reconhecimento = self.get_renovacao_reconhecimento(registro.aluno.curso_campus)

        if reconhecimento is None and tramitacaoEMEC is None:
            self.registrar_erro_cadastro(
                assinatura_digital=assinatura_digital, detalhe='Erro no envio do histórico escolar: Reconhecimento não encontrado.'
            )
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_HISTORICO
            registro.save()
            return

        natureza_participacao_id = registro.aluno.get_natureza_participacao_id()
        credenciamento = (
            Credenciamento.objects.filter(tipo=Credenciamento.CREDECIAMENTO, natureza_participacao=natureza_participacao_id)
            .order_by('data_ato')
            .last()
        )
        dados_historico = {
            'meta': {
                'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
                'yourNumber': f'HST{registro.pk}',
                'dltId': 'ethereum',
                'docType': 'final_academic_transcript',
                'mimeType': 'text/xml',
                'groupId': f'REG{registro.pk}',
                'clientSignature': f'HST{registro.pk}',
            },
            'data': {
                'Versao': '1.05',
                'ambiente': 'Homologação' if settings.DEBUG else 'Produção',
                'infHistoricoEscolar': {
                    'Aluno': {
                        'Nome': registro.aluno.pessoa_fisica.nome,
                        'ID': str(registro.aluno.pk),
                    },
                    'DadosCurso': {
                        'CodigoCursoEMEC': registro.aluno.curso_campus.codigo_emec,
                        'NomeCurso': registro.aluno.curso_campus.descricao_historico,
                        'Autorizacao': autorizacao
                        and {
                            'Tipo': autorizacao.tipo_documento,
                            'Numero': autorizacao.get_numero_com_orgao(),
                            'Data': autorizacao.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': autorizacao.veiculo_publicacao and autorizacao.veiculo_publicacao or None,
                            'DataPublicacao': autorizacao.veiculo_publicacao and autorizacao.data_publicacao.strftime('%Y-%m-%d') or None,
                            'SecaoPublicacao': autorizacao.veiculo_publicacao and autorizacao.secao_publicacao or None,
                            'PaginaPublicacao': autorizacao.veiculo_publicacao and autorizacao.pagina_publicacao or None,
                        }
                        or None,
                        'Reconhecimento': reconhecimento
                        and {
                            'Tipo': reconhecimento.tipo_documento,
                            'Numero': reconhecimento.get_numero_com_orgao(),
                            'Data': reconhecimento.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.veiculo_publicacao or None,
                            'DataPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.data_publicacao.strftime('%Y-%m-%d') or None,
                            'SecaoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.secao_publicacao or None,
                            'PaginaPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.pagina_publicacao or None,
                        }
                        or tramitacaoEMEC
                        and {
                            'InformacoesTramitacaoEMEC': {
                                'DataCadastro': tramitacaoEMEC.data_cadastro.strftime('%Y-%m-%d'),
                                'DataProtocolo': tramitacaoEMEC.data_protocolo.strftime('%Y-%m-%d'),
                                'NumeroProcesso': tramitacaoEMEC.numero_processo,
                                'TipoProcesso': tramitacaoEMEC.tipo_processo,
                            }
                        },
                        'RenovacaoReconhecimento': renovacao_reconhecimento
                        and {
                            'Tipo': renovacao_reconhecimento.tipo_documento,
                            'Numero': renovacao_reconhecimento.get_numero_com_orgao(),
                            'Data': renovacao_reconhecimento.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': renovacao_reconhecimento.veiculo_publicacao and renovacao_reconhecimento.veiculo_publicacao or None,
                            'DataPublicacao': renovacao_reconhecimento.veiculo_publicacao
                            and renovacao_reconhecimento.data_publicacao.strftime('%Y-%m-%d')
                            or None,
                            'SecaoPublicacao': renovacao_reconhecimento.veiculo_publicacao and renovacao_reconhecimento.secao_publicacao or None,
                            'PaginaPublicacao': renovacao_reconhecimento.veiculo_publicacao and renovacao_reconhecimento.pagina_publicacao or None,
                        }
                        or None,
                    },
                    'IesEmissora': {
                        'Nome': nome_instituicao,
                        'CodigoMEC': codigo_mec,
                        'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                        'Endereco': {
                            'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                            'Número': reitoria.numero,
                            'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                            'Bairro': reitoria.bairro,
                            'Logradouro': reitoria.endereco,
                            'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                            'UF': reitoria.municipio.uf,
                            'Complemento': '-',
                        },
                        'Credenciamento': {
                            'Tipo': credenciamento.tipo_ato,
                            'Numero': credenciamento.numero_ato,
                            'Data': credenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': credenciamento.veiculo_publicacao,
                            'DataPublicacao': credenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': credenciamento.secao_publicacao,
                            'PaginaPublicacao': credenciamento.pagina_publicacao,
                        },
                    },
                },
            },
        }
        if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['VeiculoPublicacao'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['DataPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['SecaoPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['PaginaPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['VeiculoPublicacao']

        if 'VeiculoPublicacao' in dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']:
            if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['VeiculoPublicacao'] is None:
                del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['DataPublicacao']
                del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['SecaoPublicacao']
                del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['PaginaPublicacao']
                del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['VeiculoPublicacao']

        if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']
        elif dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['VeiculoPublicacao'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['DataPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['SecaoPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['PaginaPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['VeiculoPublicacao']
        s = json.dumps(dados_historico, ensure_ascii=False)
        # logger.info(s)

        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_HISTORICO_FINAL)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=dados_historico, schema=schema)
            if apenas_validacao:
                logger.info(dados_historico)
                return
        except jsonschema.exceptions.ValidationError as e:
            if apenas_validacao:
                for error in e.context:
                    logger.info(error.message, error.json_path)
                return
            detalhe = 'É necessário a correção do seguinte erro: {} ({})'.format(e.message, '->'.join([str(x) for x in e.path]))
            aditionalInfo = len(detalhe) > 255 and detalhe or None
            self.registrar_erro_cadastro(assinatura_digital=assinatura_digital, detalhe=detalhe, aditionalInfo=aditionalInfo)
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_HISTORICO
            registro.save()
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/'
        data = {'documentType': 3, 'documentData': s, 'documentFile': ''}
        self.log(url)
        response = (
            MOCK
            and MockedResponse()
            or requests.post(
                url,
                data=data,
                headers=self.headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            )
        )
        self.log(response.text)
        data = json.loads(response.text)
        documentId = data.get('documentId')
        if documentId is None:
            erro = data.get('error') and data.get('error').get('message') or 'Sem retorno do documentID.'
            aditionalInfo = data.get('aditionalInfo')
            self.registrar_erro_cadastro(
                assinatura_digital=assinatura_digital, detalhe=f'Erro no envio do histórico escolar: {erro}', aditionalInfo=aditionalInfo
            )
        else:
            assinatura_digital.id_historico_escolar = documentId
            assinatura_digital.save()
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_HISTORICO
            registro.save()
            SincronizacaoAssinaturaDigital.objects.create(
                assinatura_digital=assinatura_digital, detalhe=f'Envio do histórico escolar. ID: {documentId}.'
            )

    def enviar_arquivo_fiscalizacao_emissora(self, assinatura_digital, apenas_validacao=False):
        pk = 1
        hoje = date.today()
        reitoria = UnidadeOrganizacional.objects.suap().get(setor__sigla=get_sigla_reitoria())
        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        codigo_mec = Configuracao.get_valor_por_chave('edu', 'codigo_mec') or '1082'
        registro = assinatura_digital.registro_emissao_diploma

        natureza_participacao_id = registro.aluno.get_natureza_participacao_id()
        qs_credenciamento = Credenciamento.objects.filter(natureza_participacao=natureza_participacao_id).order_by('data_ato')
        credenciamento = qs_credenciamento.filter(tipo=Credenciamento.CREDECIAMENTO).last()
        recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RECREDECIAMENTO).last()
        renovacao_recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RENOVACAO_RECREDECIAMENTO).last()

        dados_arquivo = {
            'meta': {
                'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
                'yourNumber': f'AFE{pk}',
                'dltId': 'ethereum',
                'docType': 'audit_file_issuer',
                'mimeType': 'text/xml',
                'groupId': f'AFE{pk}',
                'clientSignature': f'AFE{pk}',
                'isDocSigned': 'true',
            },
            'data': {
                'Versao': '1.05',
                'ambiente': 'Produção',
                'infArquivoFiscalizacaoEmissora': {
                    'DataInicioFiscalizacao': hoje.strftime('%Y-%m-%d'),
                    'IesEmissora': {
                        'Nome': nome_instituicao,
                        'CodigoMEC': codigo_mec,
                        'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                        'Endereco': {
                            'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                            'Número': reitoria.numero,
                            'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                            'Bairro': reitoria.bairro,
                            'Logradouro': reitoria.endereco,
                            'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                            'UF': reitoria.municipio.uf,
                            'Complemento': '-',
                        },
                        'Credenciamento': credenciamento
                        and {
                            'Tipo': credenciamento.tipo_ato,
                            'Numero': credenciamento.numero_ato,
                            'Data': credenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': credenciamento.veiculo_publicacao,
                            'DataPublicacao': credenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': credenciamento.secao_publicacao,
                            'PaginaPublicacao': credenciamento.pagina_publicacao,
                        }
                        or None,
                        'Recredenciamento': recredenciamento
                        and {
                            'Tipo': recredenciamento.tipo_ato,
                            'Numero': recredenciamento.numero_ato,
                            'Data': recredenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': recredenciamento.veiculo_publicacao,
                            'DataPublicacao': recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': recredenciamento.secao_publicacao,
                            'PaginaPublicacao': recredenciamento.pagina_publicacao,
                        }
                        or None,
                        'RenovacaoDeRecredenciamento': renovacao_recredenciamento
                        and {
                            'Tipo': renovacao_recredenciamento.tipo_ato,
                            'Numero': renovacao_recredenciamento.numero_ato,
                            'Data': renovacao_recredenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': renovacao_recredenciamento.veiculo_publicacao,
                            'DataPublicacao': renovacao_recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': renovacao_recredenciamento.secao_publicacao,
                            'PaginaPublicacao': renovacao_recredenciamento.pagina_publicacao,
                        }
                        or None,
                        'Mantenedora': {
                            'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                            'RazaoSocial': nome_instituicao,
                            'Endereco': {
                                'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                                'Número': reitoria.numero,
                                'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                                'Bairro': reitoria.bairro,
                                'Logradouro': reitoria.endereco,
                                'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                                'UF': reitoria.municipio.uf,
                            },
                        },
                    },
                    'DiplomasFiscalizados': [
                        {
                            'IdDocumento': '47688161953',
                            'URLXMLdoDiplomado': 'https://exemplo.com/codigo',
                            'URLRVDD': 'https://exemplo.com/codigo',
                            'URLXMLdeRegistroAcademico': 'https://exemplo.com/codigo',
                        }
                    ],
                    'DataFimFiscalizacao': hoje.strftime('%Y-%m-%d'),
                },
            },
        }
        if not dados_arquivo['data']['infArquivoFiscalizacaoEmissora']['IesEmissora']['Recredenciamento']:
            del dados_arquivo['data']['infArquivoFiscalizacaoEmissora']['IesEmissora']['Recredenciamento']
        if not dados_arquivo['data']['infArquivoFiscalizacaoEmissora']['IesEmissora']['RenovacaoDeRecredenciamento']:
            del dados_arquivo['data']['infArquivoFiscalizacaoEmissora']['IesEmissora']['RenovacaoDeRecredenciamento']

        # s = json.dumps(dados_arquivo, ensure_ascii=False)
        # logger.info(s)

        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_ARQUIVO_FISCALIZACAO_EMISSORA)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=dados_arquivo, schema=schema)
            if apenas_validacao:
                logger.info(dados_arquivo)
                return
        except jsonschema.exceptions.ValidationError as e:
            if apenas_validacao:
                for error in e.context:
                    logger.info(error.message, error.json_path)
                return
            detalhe = 'É necessário a correção do seguinte erro: {} ({})'.format(e.message, '->'.join([str(x) for x in e.path]))
            logger.info(detalhe)
            return

    def enviar_historico_escolar_parcial(self, registro, apenas_validacao=False):
        hoje = date.today()
        reitoria = UnidadeOrganizacional.objects.suap().get(setor__sigla=get_sigla_reitoria())
        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        codigo_mec = Configuracao.get_valor_por_chave('edu', 'codigo_mec') or '1082'

        autorizacao = self.get_autorizacao(registro.aluno.curso_campus)
        if autorizacao is None:
            registro.erro_rap = 'Erro no envio do histórico escolar parcial: Autorização não encontrada.'
            registro.save()
            return

        reconhecimento = self.get_reconhecimento(registro.aluno.curso_campus)
        tramitacaoEMEC = None
        renovacao_reconhecimento = None
        if reconhecimento is None:
            tramitacaoEMEC = self.get_tramitacao_emec(registro.aluno.curso_campus)
        else:
            renovacao_reconhecimento = self.get_renovacao_reconhecimento(registro.aluno.curso_campus)

        if reconhecimento is None and tramitacaoEMEC is None:
            registro.erro_rap = 'Erro no envio do histórico escolar parcial: Reconhecimento não encontrado.'
            registro.save()
            return

        natureza_participacao_id = registro.aluno.get_natureza_participacao_id()
        qs_credenciamento = Credenciamento.objects.filter(natureza_participacao=natureza_participacao_id).order_by('data_ato')
        credenciamento = qs_credenciamento.filter(tipo=Credenciamento.CREDECIAMENTO).last()
        recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RECREDECIAMENTO).last()
        renovacao_recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RENOVACAO_RECREDECIAMENTO).last()

        _erros_historico, dados_historico_escolar = self.get_dados_historico_escolar(registro.aluno, hoje, hoje)
        dados_historico = {
            'meta': {
                'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
                'yourNumber': f'HSTP{registro.pk}',
                'dltId': 'ethereum',
                'docType': 'partial_academic_transcript',
                'mimeType': 'text/xml',
                'groupId': f'HSTP{registro.pk}',
                'clientSignature': f'HSTP{registro.pk}',
            },
            'data': {
                'Versao': '1.05',
                'ambiente': 'Homologação' if settings.DEBUG else 'Produção',
                'infHistoricoEscolar': {
                    'Aluno': {
                        'Nome': registro.aluno.pessoa_fisica.nome,
                        'ID': str(registro.aluno.pk),
                        'Sexo': registro.aluno.pessoa_fisica.sexo,
                        'Nacionalidade': registro.aluno.nacionalidade,
                        'Naturalidade': {
                            'CodigoMunicipio': f'{registro.aluno.naturalidade.codigo}',
                            'NomeMunicipio': registro.aluno.naturalidade.nome,
                            'UF': registro.aluno.naturalidade.estado.get_sigla(),
                        }
                        if registro.aluno.naturalidade.estado_id
                        else {'NomeMunicipioEstrangeiro': registro.aluno.naturalidade.nome},
                        'CPF': registro.aluno.pessoa_fisica.cpf.replace('-', '').replace('.', ''),
                        'RG': {
                            'Numero': registro.aluno.numero_rg.replace('-', '').replace('.', ''),
                            'UF': registro.aluno.uf_emissao_rg.get_sigla(),
                        },
                        'DataNascimento': registro.aluno.pessoa_fisica.nascimento_data.strftime('%Y-%m-%d'),
                    },
                    'IesEmissora': {
                        'Nome': nome_instituicao,
                        'CodigoMEC': codigo_mec,
                        'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                        'Endereco': {
                            'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                            'Número': reitoria.numero,
                            'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                            'Bairro': reitoria.bairro,
                            'Logradouro': reitoria.endereco,
                            'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                            'UF': reitoria.municipio.uf,
                            'Complemento': '-',
                        },
                        'Credenciamento': credenciamento
                        and {
                            'Tipo': credenciamento.tipo_ato,
                            'Numero': credenciamento.numero_ato,
                            'Data': credenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': credenciamento.veiculo_publicacao,
                            'DataPublicacao': credenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': credenciamento.secao_publicacao,
                            'PaginaPublicacao': credenciamento.pagina_publicacao,
                        }
                        or None,
                        'Recredenciamento': recredenciamento
                        and {
                            'Tipo': recredenciamento.tipo_ato,
                            'Numero': recredenciamento.numero_ato,
                            'Data': recredenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': recredenciamento.veiculo_publicacao,
                            'DataPublicacao': recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': recredenciamento.secao_publicacao,
                            'PaginaPublicacao': recredenciamento.pagina_publicacao,
                        }
                        or None,
                        'RenovacaoDeRecredenciamento': renovacao_recredenciamento
                        and {
                            'Tipo': renovacao_recredenciamento.tipo_ato,
                            'Numero': renovacao_recredenciamento.numero_ato,
                            'Data': renovacao_recredenciamento.data_ato.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': renovacao_recredenciamento.veiculo_publicacao,
                            'DataPublicacao': renovacao_recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                            'SecaoPublicacao': renovacao_recredenciamento.secao_publicacao,
                            'PaginaPublicacao': renovacao_recredenciamento.pagina_publicacao,
                        }
                        or None,
                        'Mantenedora': {
                            'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                            'RazaoSocial': nome_instituicao,
                            'Endereco': {
                                'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                                'Número': reitoria.numero,
                                'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                                'Bairro': reitoria.bairro,
                                'Logradouro': reitoria.endereco,
                                'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                                'UF': reitoria.municipio.uf,
                            },
                        },
                    },
                    'DadosCurso': {
                        'CodigoCursoEMEC': registro.aluno.curso_campus.codigo_emec,
                        'NomeCurso': registro.aluno.curso_campus.descricao_historico,
                        'Autorizacao': autorizacao
                        and {
                            'Tipo': autorizacao.tipo_documento,
                            'Numero': autorizacao.get_numero_com_orgao(),
                            'Data': autorizacao.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': autorizacao.veiculo_publicacao and autorizacao.veiculo_publicacao or None,
                            'DataPublicacao': autorizacao.veiculo_publicacao and autorizacao.data_publicacao.strftime('%Y-%m-%d') or None,
                            'SecaoPublicacao': autorizacao.veiculo_publicacao and autorizacao.secao_publicacao or None,
                            'PaginaPublicacao': autorizacao.veiculo_publicacao and autorizacao.pagina_publicacao or None,
                        }
                        or None,
                        'Reconhecimento': reconhecimento
                        and {
                            'Tipo': reconhecimento.tipo_documento,
                            'Numero': reconhecimento.get_numero_com_orgao(),
                            'Data': reconhecimento.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.veiculo_publicacao or None,
                            'DataPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.data_publicacao.strftime('%Y-%m-%d') or None,
                            'SecaoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.secao_publicacao or None,
                            'PaginaPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.pagina_publicacao or None,
                        }
                        or tramitacaoEMEC
                        and {
                            'InformacoesTramitacaoEMEC': {
                                'DataCadastro': tramitacaoEMEC.data_cadastro.strftime('%Y-%m-%d'),
                                'DataProtocolo': tramitacaoEMEC.data_protocolo.strftime('%Y-%m-%d'),
                                'NumeroProcesso': tramitacaoEMEC.numero_processo,
                                'TipoProcesso': tramitacaoEMEC.tipo_processo,
                            }
                        },
                        'RenovacaoReconhecimento': renovacao_reconhecimento
                        and {
                            'Tipo': reconhecimento.tipo_documento,
                            'Numero': reconhecimento.get_numero_com_orgao(),
                            'Data': reconhecimento.data.strftime('%Y-%m-%d'),
                            'VeiculoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.veiculo_publicacao or None,
                            'DataPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.data_publicacao.strftime('%Y-%m-%d') or None,
                            'SecaoPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.secao_publicacao or None,
                            'PaginaPublicacao': reconhecimento.veiculo_publicacao and reconhecimento.pagina_publicacao or None,
                        }
                        or None,
                    },
                    'HistoricoEscolar': dados_historico_escolar,
                },
            },
        }
        if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['VeiculoPublicacao'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['DataPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['SecaoPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['PaginaPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Autorizacao']['VeiculoPublicacao']

        if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['VeiculoPublicacao'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['DataPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['SecaoPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['PaginaPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['Reconhecimento']['VeiculoPublicacao']

        if dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']
        elif dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['VeiculoPublicacao'] is None:
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['DataPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['SecaoPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['PaginaPublicacao']
            del dados_historico['data']['infHistoricoEscolar']['DadosCurso']['RenovacaoReconhecimento']['VeiculoPublicacao']

        if not dados_historico['data']['infHistoricoEscolar']['IesEmissora']['Recredenciamento']:
            del dados_historico['data']['infHistoricoEscolar']['IesEmissora']['Recredenciamento']
        if not dados_historico['data']['infHistoricoEscolar']['IesEmissora']['RenovacaoDeRecredenciamento']:
            del dados_historico['data']['infHistoricoEscolar']['IesEmissora']['RenovacaoDeRecredenciamento']

        s = json.dumps(dados_historico, ensure_ascii=False)
        # logger.info(s)

        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_HISTORICO_PARCIAL)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=dados_historico, schema=schema)
            if apenas_validacao:
                logger.info(dados_historico)
                return
        except jsonschema.exceptions.ValidationError as e:
            if apenas_validacao:
                for error in e.context:
                    logger.info(error.message, error.json_path)
                return
            detalhe = 'É necessário a correção do seguinte erro: {} ({})'.format(e.message, '->'.join([str(x) for x in e.path]))
            registro.erro_rap = detalhe
            registro.save()
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/'
        data = {'documentType': 1, 'documentData': s, 'documentFile': ''}
        self.log(url)
        response = (
            MOCK
            and MockedResponse()
            or requests.post(
                url,
                data=data,
                headers=self.headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            )
        )
        self.log(response.text)
        data = json.loads(response.text)
        if data.get('documentId'):
            registro.id_rap = data.get('documentId')
        else:
            registro.erro_rap = 'Envio do histórico não retornou nenhum ID.'
        registro.save()

    def enviar_dados_diploma(self, assinatura_digital, apenas_validacao=False):
        registro = assinatura_digital.registro_emissao_diploma
        reitoria = UnidadeOrganizacional.objects.suap().get(setor__sigla=get_sigla_reitoria())

        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
        codigo_mec = Configuracao.get_valor_por_chave('edu', 'codigo_mec') or '1082'

        natureza_participacao_id = registro.aluno.get_natureza_participacao_id()
        qs_credenciamento = Credenciamento.objects.filter(natureza_participacao=natureza_participacao_id).order_by('data_ato')
        credenciamento = qs_credenciamento.filter(tipo=Credenciamento.CREDECIAMENTO).last()
        recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RECREDECIAMENTO).last()
        renovacao_recredenciamento = qs_credenciamento.filter(tipo=Credenciamento.RENOVACAO_RECREDECIAMENTO).last()

        if registro.aluno.is_qacademico():
            historico = registro.aluno.get_historico_legado(final=True)
            data_colacao_grau = historico['data_colacao_grau']
        else:
            data_colacao_grau = registro.aluno.get_data_colacao_grau()

        info = {
            'meta': {
                'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
                'yourNumber': f'DIP{registro.pk}',
                'dltId': 'ethereum',
                'docType': 'digital_degree',
                'mimeType': 'text/xml',
                'clientSignature': f'REG{registro.pk}',
                'groupId': f'REG{registro.pk}',
            },
            'data': {
                'Versao': '1.05',
                'ambiente': 'Homologação' if settings.DEBUG else 'Produção',
                'infDiploma': {
                    'DadosDiploma': {
                        'Diplomado': {
                            'Nome': registro.aluno.pessoa_fisica.nome,
                            'ID': str(registro.aluno.pk),
                        },
                        'DadosCurso': {
                            'CodigoCursoEMEC': registro.aluno.curso_campus.codigo_emec,
                            'NomeCurso': registro.aluno.curso_campus.descricao_historico,
                        },
                        'IesEmissora': {
                            'Nome': nome_instituicao,
                            'CodigoMEC': codigo_mec,
                            'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                        },
                    },
                    'DadosRegistro': {
                        'LivroRegistro': {
                            'ProcessoDoDiploma': str(registro.processo.numero_processo),
                            'DataColacaoGrau': data_colacao_grau.strftime('%Y-%m-%d'),
                            'DataRegistroDiploma': registro.data_expedicao.strftime('%Y-%m-%d'),
                            'ResponsavelRegistro': {
                                'IDouNumeroMatricula': registro.emissor.username,
                                'CPF': registro.emissor.get_vinculo().pessoa.pessoafisica.cpf.replace('.', '').replace('-', '').replace('*', '0'),
                                'Nome': registro.emissor.get_vinculo().pessoa.nome,
                            },
                            'LivroRegistro': str(registro.livro),
                            'NumeroSequenciaDoDiploma': str(registro.numero_registro),
                            'DataExpedicaoDiploma': registro.data_expedicao.strftime('%Y-%m-%d'),
                            'NumeroFolhaDoDiploma': str(registro.folha),
                        },
                        'IesRegistradora': {
                            'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                            'Nome': nome_instituicao,
                            'CodigoMEC': codigo_mec,
                            'Credenciamento': credenciamento
                            and {
                                'Tipo': credenciamento.tipo_ato,
                                'Numero': credenciamento.numero_ato,
                                'Data': credenciamento.data_ato.strftime('%Y-%m-%d'),
                                'VeiculoPublicacao': credenciamento.veiculo_publicacao,
                                'DataPublicacao': credenciamento.data_publicacao.strftime('%Y-%m-%d'),
                                'SecaoPublicacao': credenciamento.secao_publicacao,
                                'PaginaPublicacao': credenciamento.pagina_publicacao,
                            }
                            or None,
                            'Recredenciamento': recredenciamento
                            and {
                                'Tipo': recredenciamento.tipo_ato,
                                'Numero': recredenciamento.numero_ato,
                                'Data': recredenciamento.data_ato.strftime('%Y-%m-%d'),
                                'VeiculoPublicacao': recredenciamento.veiculo_publicacao,
                                'DataPublicacao': recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                                'SecaoPublicacao': recredenciamento.secao_publicacao,
                                'PaginaPublicacao': recredenciamento.pagina_publicacao,
                            }
                            or None,
                            'RenovacaoDeRecredenciamento': renovacao_recredenciamento
                            and {
                                'Tipo': renovacao_recredenciamento.tipo_ato,
                                'Numero': renovacao_recredenciamento.numero_ato,
                                'Data': renovacao_recredenciamento.data_ato.strftime('%Y-%m-%d'),
                                'VeiculoPublicacao': renovacao_recredenciamento.veiculo_publicacao,
                                'DataPublicacao': renovacao_recredenciamento.data_publicacao.strftime('%Y-%m-%d'),
                                'SecaoPublicacao': renovacao_recredenciamento.secao_publicacao,
                                'PaginaPublicacao': renovacao_recredenciamento.pagina_publicacao,
                            }
                            or None,
                            'Mantenedora': {
                                'CNPJ': reitoria.cnpj.replace('.', '').replace('/', '').replace('-', ''),
                                'RazaoSocial': nome_instituicao,
                                'Endereco': {
                                    'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                                    'Número': reitoria.numero,
                                    'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                                    'Bairro': reitoria.bairro,
                                    'Logradouro': reitoria.endereco,
                                    'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                                    'UF': reitoria.municipio.uf,
                                },
                            },
                            'Endereco': {
                                'NomeMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).nome,
                                'Número': '1',
                                'CodigoMunicipio': Cidade.get_cidade_by_municipio(reitoria.municipio).codigo,
                                'Bairro': reitoria.bairro,
                                'Logradouro': reitoria.endereco,
                                'CEP': reitoria.cep.replace('.', '').replace('-', ''),
                                'UF': reitoria.municipio.uf,
                            },
                        },
                    },
                },
            },
        }

        if not info['data']['infDiploma']['DadosRegistro']['IesRegistradora']['Recredenciamento']:
            del info['data']['infDiploma']['DadosRegistro']['IesRegistradora']['Recredenciamento']
        if not info['data']['infDiploma']['DadosRegistro']['IesRegistradora']['RenovacaoDeRecredenciamento']:
            del info['data']['infDiploma']['DadosRegistro']['IesRegistradora']['RenovacaoDeRecredenciamento']

        s = json.dumps(info, ensure_ascii=False)
        # logger.info(s)

        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_DIPLOMA)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=info, schema=schema)
            if apenas_validacao:
                logger.info(info)
                return
        except jsonschema.exceptions.ValidationError as e:
            if apenas_validacao:
                for error in e.context:
                    logger.info(error.message, error.json_path)
                return
            detalhe = 'É necessário que a TI corrija os seguinte erro: {} ({})'.format(e.message, '->'.join(e.path))
            aditionalInfo = len(detalhe) > 255 and detalhe or None
            self.registrar_erro_cadastro(assinatura_digital=assinatura_digital, detalhe=detalhe, aditionalInfo=aditionalInfo)
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_DADOS_DIPLOMA
            registro.save()
            return
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/'
        data = {'documentType': 2, 'documentData': s, 'documentFile': ''}
        self.log(url)
        response = (
            MOCK
            and MockedResponse()
            or requests.post(
                url,
                data=data,
                headers=self.headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            )
        )
        self.log(response.text)
        data = json.loads(response.text)
        documentId = data.get('documentId')
        if documentId is None:
            erro = data.get('error') and data.get('error').get('message') or 'Sem retorno do documentID.'
            aditionalInfo = data.get('aditionalInfo')
            self.registrar_erro_cadastro(
                assinatura_digital=assinatura_digital, detalhe=f'Erro no envio de dados do diploma: {erro}', aditionalInfo=aditionalInfo
            )
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CORRECAO_DADOS_DIPLOMA
        else:
            assinatura_digital.id_dados_diploma_digital = documentId
            assinatura_digital.save()
            SincronizacaoAssinaturaDigital.objects.create(
                assinatura_digital=assinatura_digital, detalhe=f'Envio dos dados do diploma. ID: {documentId}.'
            )
            registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_ASSINATURA_DIPLOMA
        registro.save()

    def enviar_representacao_diploma(self, assinatura_digital, apenas_validacao=False):
        registro = assinatura_digital.registro_emissao_diploma
        rap_api_url = Configuracao.get_valor_por_chave('edu', 'rap_api_url')
        url = f'{rap_api_url}/api/documents/'
        if apenas_validacao:
            referencia = '2885269.1681.a27ab1d09d04'
        else:
            response = requests.get(
                f'{url}{assinatura_digital.id_dados_diploma_digital}/',
                headers=self.headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            ).json()
            referencia = response['securityCode']
        info = {
            'meta': {
                'clientId': Configuracao.get_valor_por_chave('edu', 'rap_client_id'),
                'yourNumber': f'REP{registro.pk}',
                'dltId': 'ethereum',
                'docType': 'visual_rep_degree',
                'mimeType': 'application/pdf',
                'clientSignature': f'REP{registro.pk}',
                'isDocSigned': 'false',
                'groupId': f'REG{registro.pk}',
            },
            'data': {'ReferenciaDiploma': f'{referencia}'},
        }
        schema_file_path = os.path.join(settings.BASE_DIR, ESQUEMA_REPRESENTACAO_VISUAL)
        schema = json.load(open(schema_file_path))
        try:
            jsonschema.validate(instance=info, schema=schema)
            if apenas_validacao:
                logger.info(info)
                return
        except jsonschema.exceptions.ValidationError as e:
            if apenas_validacao:
                for error in e.context:
                    logger.info(error.message, error.json_path)
                return
        s = json.dumps(info, ensure_ascii=False)
        # logger.info(s)
        data = {'documentType': '5', 'documentData': s}

        file_path = MOCK and os.path.join(settings.BASE_DIR, 'edu/diploma_digital/pdf/tmp44ql3sbn.pdf') or cache_file(assinatura_digital.diploma.name)
        with open(file_path, 'rb') as f:
            content = f.read()
        files = {'documentFile': ('Diploma.pdf', content, 'application/pdf')}
        self.log(url)
        response = (
            MOCK
            and MockedResponse()
            or requests.post(
                url,
                data=data,
                files=files,
                headers=self.headers(),
                timeout=settings.REQUESTS_TIMEOUT,
            )
        )
        self.log(response.text)
        data = json.loads(response.text)
        documentId = data.get('documentId')
        assinatura_digital.id_representacao_diploma_digital = documentId
        assinatura_digital.save()
        registro.situacao = RegistroEmissaoDiploma.AGUARDANDO_CONFECCAO_DIPLOMA
        registro.save()
        SincronizacaoAssinaturaDigital.objects.create(
            assinatura_digital=assinatura_digital, detalhe=f'Envio da representação visual do diploma. ID: {documentId}.'
        )

    def get_autorizacao(self, curso_campus):
        curso_id = curso_campus.mesmo_curso and curso_campus.mesmo_curso_id or curso_campus.id
        return AtoRegulatorioCurso.objects.filter(curso_id=curso_id, tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO).first()

    def get_renovacao_reconhecimento(self, curso_campus):
        curso_id = curso_campus.mesmo_curso and curso_campus.mesmo_curso_id or curso_campus.id
        return AtoRegulatorioCurso.objects.filter(curso_id=curso_id, tipo=AtoRegulatorioCurso.TIPO_RENOVACAO).order_by('-data').first()

    def get_reconhecimento(self, curso_campus):
        curso_id = curso_campus.mesmo_curso and curso_campus.mesmo_curso_id or curso_campus.id
        return AtoRegulatorioCurso.objects.filter(curso_id=curso_id, tipo=AtoRegulatorioCurso.TIPO_RECONHECIMENTO).first()

    def get_tramitacao_emec(self, curso_campus):
        curso_id = curso_campus.mesmo_curso and curso_campus.mesmo_curso_id or curso_campus.id
        return TramitacaoProcessoEMEC.objects.filter(curso_id=curso_id).first()
