from ninja import Schema

from comum.utils import get_setor, get_uo
from conectagov_pen.models import TramiteBarramento
from conectagov_pen.utils import get_nivel_acesso_documento
from processo_eletronico.models import DocumentoDigitalizado, DocumentoTexto, Minuta, Tramite

from .models import HipoteseLegalPEN, MapeamentoTiposDocumento


def get_hipotese_legal(obj):
    if obj.hipotese_legal:
        try:
            return {
                'nome': obj.hipotese_legal.hipoteselegalpen.nome,
                'baseLegal': obj.hipotese_legal.hipoteselegalpen.base_legal,
                'identificacao': obj.hipotese_legal.hipoteselegalpen.id_hipotese_legal_pen,
            }
        except HipoteseLegalPEN.DoesNotExist:
            # Se não tem hipotese mapeada retorna padrão - Documento Pessoal
            hipotese_padrao = HipoteseLegalPEN.get_hipotese_padrao()
            return {'nome': hipotese_padrao.nome, 'baseLegal': hipotese_padrao.base_legal, 'identificacao': hipotese_padrao.id_hipotese_legal_pen}
    return None


def get_interessados(obj):
    interessados = []
    for interes in obj.interessados.all():
        interessado = {
            'nome': interes.nome,
            'documentosDeIdentificacao': [
                {'codigo': interes.get_cpf_ou_cnpj(), 'emissor': 'CPF_CNPJ', 'tipo': 'CI', 'nomeNoDocumento': interes.nome}
            ],
        }
        interessados.append(interessado)
    return interessados


def get_documentos(obj, context=None):
    documentos = []
    documentos_processo = context.get('documentos')
    processo_barramento = context.get('processo_barramento')
    for doc in documentos_processo:
        id_tipo_documento = None
        data_criacao = None
        if doc['tipo_parte_processo'] == 'DOCUMENTO_TEXTO':
            objeto_documento = DocumentoTexto.objects.get(id=doc['id_documento'])
        elif doc['tipo_parte_processo'] == 'DOCUMENTO_DIGITALIZADO':
            objeto_documento = DocumentoDigitalizado.objects.get(id=doc['id_documento'])
        elif doc['tipo_parte_processo'] == 'DESPACHO':
            objeto_documento = Tramite.objects.get(id=doc['id_documento'])
            id_tipo_documento = 42
            nome_tipo_documento = 'Despacho'
            data_criacao = objeto_documento.data_hora_encaminhamento.strftime('%Y-%m-%d' + 'T' + '%H:%M:%S-03:00')
        elif doc['tipo_parte_processo'] == 'MINUTA':
            objeto_documento = Minuta.objects.get(id=doc['id_documento'])
            id_tipo_documento = 83
            nome_tipo_documento = 'Minuta'
        elif doc['tipo_parte_processo'] == 'REQUERIMENTO':
            objeto_documento = DocumentoDigitalizado.objects.get(id=doc['id_documento'])
            id_tipo_documento = 125
            nome_tipo_documento = 'Requerimento'

        if not hasattr(objeto_documento, 'assunto') or not objeto_documento.assunto:
            objeto_documento.assunto = 'Assunto não informado'

        nome_documento = str(objeto_documento.id) + '.pdf'
        mime_type = 'application/pdf'
        tipo_conteudo = 'txt'
        dados_complementares_tipo_arquivo = None

        if not id_tipo_documento and MapeamentoTiposDocumento.objects.filter(tipo_doc_suap=objeto_documento.tipo).exists():
            mapeamento_tipo = MapeamentoTiposDocumento.objects.get(tipo_doc_suap=objeto_documento.tipo)
            id_tipo_documento = mapeamento_tipo.tipo_doc_barramento_pen.id_tipo_doc_pen
            nome_tipo_documento = mapeamento_tipo.tipo_doc_barramento_pen.nome

        if TramiteBarramento.objects.filter(processo_barramento=processo_barramento, status=TramiteBarramento.STATUS_RECEBIDO).exists():
            tramite_barramento = (
                TramiteBarramento.objects.filter(processo_barramento=processo_barramento, status=TramiteBarramento.STATUS_RECEBIDO)
                .order_by('-data_hora_encaminhamento')
                .first()
            )
            if 'processo' in tramite_barramento.metadados_processo:
                documentos_metadados = tramite_barramento.metadados_processo['processo']['documentos']
            elif 'documentos' in tramite_barramento.metadados_processo:
                documentos_metadados = tramite_barramento.metadados_processo['documentos']

            for meta_doc_recebido in documentos_metadados:
                if meta_doc_recebido['ordem'] == doc['ordem']:
                    id_tipo_documento = meta_doc_recebido['especie']['codigo']
                    nome_tipo_documento = meta_doc_recebido['especie']['nomeNoProdutor']
                    nome_documento = meta_doc_recebido['componentesDigitais'][0]['nome']
                    mime_type = meta_doc_recebido['componentesDigitais'][0]['mimeType']
                    if meta_doc_recebido['componentesDigitais'][0]['mimeType'] == 'outro':
                        dados_complementares_tipo_arquivo = meta_doc_recebido['componentesDigitais'][0]['dadosComplementaresDoTipoDeArquivo']
                    tipo_conteudo = meta_doc_recebido['componentesDigitais'][0]['tipoDeConteudo']

        """No caso de despachos de Tramite, Parecer e Minuta recebem o nivel de acesso e hipótese legal do processo"""
        if not hasattr(objeto_documento, 'nivel_acesso'):
            nivel_acesso = obj.nivel_acesso
            hipotese_legal = get_hipotese_legal(obj)
        else:
            nivel_acesso = obj.nivel_acesso
            """Se nível de acesso do processo for 1 = Público a hipotese_legal será nula = None"""
            if nivel_acesso == 1:
                hipotese_legal = None
            else:
                nivel_acesso = get_nivel_acesso_documento(objeto_documento.nivel_acesso)
                hipotese_legal = get_hipotese_legal_documento_pen(objeto_documento)

        """No caso de despachos de Tramite e  Parecer que nao tem o attr data_criacao"""
        if not data_criacao and hasattr(objeto_documento, 'data_criacao'):
            data_criacao = objeto_documento.data_criacao.strftime('%Y-%m-%d' + 'T' + '%H:%M:%S-03:00')
        else:
            data_criacao = obj.data_hora_criacao.strftime('%Y-%m-%d' + 'T' + '%H:%M:%S-03:00')

        documento = {
            'ordem': doc['ordem'],
            'nivelDeSigilo': nivel_acesso,
            'produtor': {
                'nome': obj.usuario_gerador.get_profile().nome
                + ' - '
                + get_setor(obj.usuario_gerador).sigla
                + ' - '
                + get_uo(obj.usuario_gerador).sigla,
                'tipo': 'orgaopublico',
            },
            'descricao': (objeto_documento.assunto[:45] + '...') if len(objeto_documento.assunto) > 50 else objeto_documento.assunto,
            'hipoteseLegal': hipotese_legal,
            'dataHoraDeProducao': data_criacao,
            'dataHoraDeRegistro': data_criacao,
            'especie': {'codigo': id_tipo_documento, 'nomeNoProdutor': nome_tipo_documento},
            'componentesDigitais': [
                {
                    'nome': nome_documento,
                    'hash': {'algoritmo': 'SHA256', 'conteudo': doc['hash_documento']},  # No exemplo é SHA256  # documento.hash_conteudo
                    'tipoDeConteudo': tipo_conteudo,  # Padrao de tipo para PDF do barramento
                    'mimeType': mime_type,
                    'tamanhoEmBytes': doc['tamanho_bytes'],
                    'ordem': doc['ordem'],
                    'dadosComplementaresDoTipoDeArquivo': dados_complementares_tipo_arquivo,
                }
            ],
        }

        if documento is not None:
            documentos.append(documento)
    return documentos


def get_hipotese_legal_documento_pen(obj):
    """
    Retorna a Hipótese Legal do PEN para o documento
    :param obj:
    :return:
    """
    try:
        return {
            'nome': obj.hipotese_legal.hipoteselegalpen.nome,
            'baseLegal': obj.hipotese_legal.hipoteselegalpen.base_legal,
            'identificacao': obj.hipotese_legal.hipoteselegalpen.id_hipotese_legal_pen,
        }
    except HipoteseLegalPEN.DoesNotExist:
        # Se não tem hipotese mapeada retorna padrão - Documento Pessoal
        hipotese_padrao = HipoteseLegalPEN.get_hipotese_padrao()
        return {'nome': hipotese_padrao.nome, 'baseLegal': hipotese_padrao.base_legal, 'identificacao': hipotese_padrao.id_hipotese_legal_pen}
    return None


class ProcessoConectaGOVSchema(Schema):
    cabecalho: dict = None
    processo: dict = None

    @staticmethod
    def resolve_cabecalho(obj, context=None):
        return {
            'remetente': {
                'identificacaoDoRepositorioDeEstruturas': obj.setor_atual.uo.id_repositorio_pen,
                'numeroDeIdentificacaoDaEstrutura': obj.setor_atual.uo.id_estrutura_pen,
            },
            'destinatario': {
                'identificacaoDoRepositorioDeEstruturas': '',
                'numeroDeIdentificacaoDaEstrutura': '',
            },  # Vazio pois sera setado pelo id que vem do form
            'NRE': obj.get_nre_processo_barramento,
            'obrigarEnvioDeTodosOsComponentesDigitais': 'false',
        }

    @staticmethod
    def resolve_processo(obj, context=None):
        return {
            'protocolo': obj.numero_protocolo_fisico,
            'nivelDeSigilo': obj.nivel_acesso,
            'hipoteseLegal': get_hipotese_legal(obj),
            'produtor': {
                # "nome": obj.usuario_gerador.get_profile().nome+" - "+get_setor(obj.usuario_gerador).sigla
                #         +" - "+get_uo(obj.usuario_gerador).sigla,
                'nome': 'suap',
                'tipo': 'orgaopublico',
            },
            'descricao': obj.assunto[0:100],
            'dataHoraDeProducao': obj.data_hora_criacao.strftime('%Y-%m-%d' + 'T' + '%H:%M:%S-03:00'),
            'dataHoraDeRegistro': obj.data_hora_criacao.strftime('%Y-%m-%d' + 'T' + '%H:%M:%S-03:00'),
            'documentos': get_documentos(obj, context=context),
            'interessados': get_interessados(obj),
        }
