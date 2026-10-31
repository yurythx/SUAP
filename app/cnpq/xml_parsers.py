import logging
from datetime import datetime
from xml.dom import minidom

from django.conf import settings
from django.db import models, transaction

from cnpq.models import (
    ApresentacaoTrabalho,
    AreaAtuacao,
    AreaConhecimento,
    Artigo,
    AtuacaoProfissional,
    Autor,
    Capitulo,
    CartaMapaSimilar,
    CurriculoVittaeLattes,
    CursoCurtaDuracaoMinistrado,
    DadoComplementar,
    DadoGeral,
    DesenhoIndustrial,
    DesMatDidativoInstrucional,
    Editoracao,
    Endereco,
    FormacaoAcademicaTitulacao,
    InformacaoAdicinal,
    IntegranteProjeto,
    Livro,
    ManutencaoObraArtistica,
    Maquete,
    Marca,
    OrganizacaoEventos,
    OrientacaoAndamento,
    OrientacaoConcluida,
    OutraProducaoBibliografica,
    OutraProducaoTecnica,
    PalavraChave,
    ParticipacaoBancaJulgadora,
    ParticipacaoBancaTrabalhoConclusao,
    ParticipacaoEventoCongresso,
    ParticipacaoProjeto,
    ParticipanteBanca,
    ParticipanteEventoCongresso,
    Partitura,
    Patente,
    PeriodicoRevista,
    PrefacioPosfacio,
    PremioTitulo,
    ProcessoTecnica,
    ProdutoTecnologico,
    ProgramaRadioTV,
    ProjetoPesquisa,
    RegistroPatente,
    RelatorioPesquisa,
    SetorAtividade,
    Software,
    TextoJonalRevista,
    TrabalhoEvento,
    TrabalhoTecnico,
    Traducao,
    Vinculo,
)
from cnpq.orcid import ORCID_ATRIBUTOS_LATTES, get_orcid_documento

logger = logging.getLogger(__name__)

log_atributos = {}
log_filhos = {}

log_execucao = {}


def list_models():
    models_name = 'cnpq.models'
    try:
        models_module = __import__(models_name, fromlist=['models'])
        attributes = dir(models_module)
        for attr in attributes:
            try:
                attrib = models_module.__getattribute__(attr)
                if issubclass(attrib, models.Model) and attrib.__module__ == models_name:
                    if attrib.objects.exists():
                        logger.info(f'{models_name}.{attr} = {attrib.objects.count()}')
            except TypeError:
                pass
    except ImportError:
        pass


def verificar(no, atributos, filhos):
    verificarAtributos(no, atributos)
    verificarFilhos(no, filhos)


def verificarAtributos(no, atributos):
    if settings.DEBUG:
        for attr in no._attrs:
            if attr not in atributos:
                if not log_atributos.get(no.tagName):
                    log_atributos[no.tagName] = []
                if attr not in log_atributos.get(no.tagName):
                    log_atributos[no.tagName].append(attr)
                logger.info(f'Tag: {no.tagName} \t Falta Atributo: {attr}\n')


def verificarFilhos(no, filhos):
    if settings.DEBUG:
        for filho in no._get_childNodes():
            if filho.nodeType == filho.ELEMENT_NODE:
                if filho.tagName not in filhos:
                    if not log_atributos.get(no.tagName):
                        log_filhos[no.tagName] = []
                    if filho.tagName not in log_filhos.get(no.tagName):
                        log_filhos[no.tagName].append(filho.tagName)
                    logger.info(f'Tag: {no.tagName} \t Falta Tag: {filho.tagName}\n')


def getText(node):
    if node.nodeType == node.TEXT_NODE:
        return node.data
    return ''


class CurriculoVittaeLattesParser:
    FILHOS = ['DADOS-GERAIS', 'PRODUCAO-BIBLIOGRAFICA', 'PRODUCAO-TECNICA', 'OUTRA-PRODUCAO', 'DADOS-COMPLEMENTARES']

    def __init__(self, curriculo_str, data_atualizacao, identificador_cnpq, forcar=False):
        """

        :param curriculo_str: conetúdo do currículo lattes no formato XML
        :param data_atualizacao: data da última atualização do currículo lattes
        :param identificador_cnpq: identificador do currículo lattes no CNPQ.
        :param forcar: se verdadeiro, os dados dos currículos serão atualizados independente se o conteúdo dos models já estão atualizados com o conteúdo do XML
        :return:
        """
        if curriculo_str:
            self.no = minidom.parseString(curriculo_str).documentElement
        else:
            self.no = minidom.parse('../curriculo.xml').documentElement
        self.data_atualizacao = data_atualizacao
        self.identificador_cnpq = identificador_cnpq
        self.forcar = forcar

        verificarFilhos(self.no, CurriculoVittaeLattesParser.FILHOS)

    def get_data_atualizacao(self):
        data = self.no.getAttribute('DATA-ATUALIZACAO')  # 23072016
        hora = self.no.getAttribute('HORA-ATUALIZACAO')  # 082808
        return datetime.strptime(f'{data} {hora}', '%d%m%Y %H%M%S')

    @transaction.atomic
    def parse(self, vinculo: object) -> bool:
        """
        Faz o parse do XML do currículo lattes com os modelos relacionados.
        Não faz o parse se a data de da última atualuzação do currículo for igual a data de atualização registrada no modelo, exceto se forcar = True.
        """
        model = self.get_model(self.no, vinculo)
        pessoafisica = vinculo.pessoa.pessoafisica

        if not model:
            # Chegando aqui é pq a data de atualização do currículo registrada no modelo está igual a data de atualização do XML, ou seja,
            # não há diferença entre o conteúdo do XML e o conteúdo dos modelos relacionados.

            log_execucao[pessoafisica.cpf] = f'ATUAL\t {pessoafisica.nome}'
            return False

        self.atualizar_orcid_pessoa_fisica(pessoafisica)
        self.atualizar_link_lattes_pessoa_fisica(pessoafisica, self.identificador_cnpq)
        log_execucao[pessoafisica.cpf] = f'PASER\t {pessoafisica.nome}'
        for filho in self.no.getElementsByTagName(CurriculoVittaeLattesParser.FILHOS[0]):
            parser = DadoGeralParser()
            model.dado_geral = parser.parse(filho, model)

        # TODO: ver com Adelson onde está sendo criado o objeto DadoComplementar e associado à variável model.
        # A linha abaixo foi inclusa para evitar o erro save() prohibited to prevent data loss due to unsaved related object 'dado_complementar'.
        try:
            if hasattr(model, 'dado_complementar') and model.dado_complementar and model.dado_complementar.pk is None:
                model.dado_complementar = None
            model.save()
        except Exception:
            return False

        for filho in self.no.getElementsByTagName(CurriculoVittaeLattesParser.FILHOS[1]):
            parser = ProducaoBibliograficaParser()
            parser.parse(filho, model)
        for filho in self.no.getElementsByTagName(CurriculoVittaeLattesParser.FILHOS[2]):
            parser = ProducaoTecnicaParser()
            parser.parse(filho, model)
        for filho in self.no.getElementsByTagName(CurriculoVittaeLattesParser.FILHOS[3]):
            parser = OutraProducaoParser()
            parser.parse(filho, model)

        for filho in self.no.getElementsByTagName(CurriculoVittaeLattesParser.FILHOS[4]):
            parser = DadoComplementarParser()
            model.dado_complementar = parser.parse(filho, model)

        model.save()
        return True

    def atualizar_orcid_pessoa_fisica(self, pessoafisica: object) -> None:
        if pessoafisica.orcid:
            return
        orcid = self.get_orcid()
        if not orcid:
            return
        pessoafisica.orcid = orcid
        pessoafisica.save(update_fields=['orcid'])

    def get_orcid(self) -> str:
        return get_orcid_documento(self.no)

    def atualizar_link_lattes_pessoa_fisica(self, pessoafisica, numero_identificador):
        if pessoafisica.lattes:
            return
        pessoafisica.lattes = f'http://lattes.cnpq.br/{numero_identificador}'
        pessoafisica.save(update_fields=['lattes'])

    def get_model(self, no, vinculo):
        ATRIBUTOS = ['SISTEMA-ORIGEM-XML', 'NUMERO-IDENTIFICADOR', 'DATA-ATUALIZACAO', 'HORA-ATUALIZACAO']
        verificarAtributos(no, ATRIBUTOS)

        try:
            model = vinculo.vinculo_curriculo_lattes
        except Exception:
            model = CurriculoVittaeLattes()
            model.vinculo = vinculo

        model.sistema_origem_xml = no.getAttribute(ATRIBUTOS[0])
        model.numero_identificador = self.identificador_cnpq

        if self.data_atualizacao:
            model.datahora_atualizacao = self.data_atualizacao
        else:
            model.datahora_atualizacao = parse_datetime(no.getAttribute(ATRIBUTOS[2]), no.getAttribute(ATRIBUTOS[3]))

        # Se nao conseguir recuperar a data de atualizacao pelo webservice deve ser feito o procedimento abaixo
        datahora_antiga = model.datahora_atualizacao
        if not model.pk:
            return model

        datahora_atual = model.datahora_atualizacao
        if datahora_atual > datahora_antiga or self.forcar:
            # Apaga o curriculo e todos os relacionamento para criar novos
            model.delete()
            return model
        else:
            return None


######################
#    DADOS GERAIS    #
######################
class DadoGeralParser:
    def parse(self, no, model):
        FILHOS = [
            'RESUMO-CV',
            'OUTRAS-INFORMACOES-RELEVANTES',
            'ENDERECO',
            'FORMACAO-ACADEMICA-TITULACAO',
            'ATUACOES-PROFISSIONAIS',
            'AREAS-DE-ATUACAO',
            'IDIOMAS',
            'PREMIOS-TITULOS',
        ]

        model = self.get_model(no, model)

        for filho in no.getElementsByTagName(FILHOS[2]):
            parser = EnderecoParser()
            parser.parse(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[3]):
            parser = FormacaoAcademicaTitulacaoParser()
            parser.parse(filho, model)

        for filho in no.getElementsByTagName(FILHOS[4]):
            for atuacao in filho.getElementsByTagName('ATUACAO-PROFISSIONAL'):
                parser = AtuacaoProfissionalParser()
                parser.parse(atuacao, model)

        for filho in no.getElementsByTagName(FILHOS[5]):
            for area_atuacao in filho.getElementsByTagName('AREA-DE-ATUACAO'):
                parser = AreaAtuacaoParser()
                parser.parse(area_atuacao, model)

        """
        for filho in no.getElementsByTagName(FILHOS[6]):
            for idioma in filho.getElementsByTagName('IDIOMA'):
                parser = IdiomaParser()
                parser.parse(idioma, model)
        """
        for filho in no.getElementsByTagName(FILHOS[7]):
            for premio_titulo in filho.getElementsByTagName('PREMIO-TITULO'):
                parser = PremioTituloParser()
                parser.parse(premio_titulo, model)

        model.save()

        return model

    def get_model(self, no, dono):
        ATRIBUTOS = [
            'NOME-COMPLETO',
            'NOME-EM-CITACOES-BIBLIOGRAFICAS',
            'NACIONALIDADE',
            'CPF',
            'NUMERO-DO-PASSAPORTE',
            'PAIS-DE-NASCIMENTO',
            'UF-NASCIMENTO',
            'CIDADE-NASCIMENTO',
            'DATA-NASCIMENTO',
            'SEXO',
            'NUMERO-IDENTIDADE',
            'ORGAO-EMISSOR',
            'UF-ORGAO-EMISSOR',
            'DATA-DE-EMISSAO',
            'NOME-DO-PAI',
            'NOME-DA-MAE',
            'PERMISSAO-DE-DIVULGACAO',
            'NOME-DO-ARQUIVO-DE-FOTO',
            'TEXTO-RESUMO-CV-RH',
            'OUTRAS-INFORMACOES-RELEVANTES',
            *ORCID_ATRIBUTOS_LATTES,
        ]
        FILHOS = [
            'RESUMO-CV',
            'OUTRAS-INFORMACOES-RELEVANTES',
            'ENDERECO',
            'FORMACAO-ACADEMICA-TITULACAO',
            'ATUACOES-PROFISSIONAIS',
            'AREAS-DE-ATUACAO',
            'IDIOMAS',
            'PREMIOS-TITULOS',
        ]
        verificar(no, ATRIBUTOS, FILHOS)
        try:
            model = dono.dado_geral
        except Exception:
            model = None
        if not model:
            model = DadoGeral()

        model.nome_completo = no.getAttribute(ATRIBUTOS[0])
        model.nome_citacao = no.getAttribute(ATRIBUTOS[1])
        model.nacionalidade = no.getAttribute(ATRIBUTOS[2])
        model.cpf = no.getAttribute(ATRIBUTOS[3])
        model.numero_passaporte = no.getAttribute(ATRIBUTOS[4])
        model.pais_nascimento = no.getAttribute(ATRIBUTOS[5])
        model.uf_nascimento = no.getAttribute(ATRIBUTOS[6])
        model.cidade_nascimento = no.getAttribute(ATRIBUTOS[7])
        model.data_nascimento = parse_date(no.getAttribute(ATRIBUTOS[8]))
        model.sexo = no.getAttribute(ATRIBUTOS[9])
        model.numero_identidade = no.getAttribute(ATRIBUTOS[10])
        model.orgao_emissor = no.getAttribute(ATRIBUTOS[11])
        model.uf_orgao_emissor = no.getAttribute(ATRIBUTOS[12])
        model.data_emissao = parse_date(no.getAttribute(ATRIBUTOS[13]))
        model.nome_pai = no.getAttribute(ATRIBUTOS[14])
        model.nome_mae = no.getAttribute(ATRIBUTOS[15])
        model.permissao_divulgacao = no.getAttribute(ATRIBUTOS[16])
        model.nome_arquivo_foto = no.getAttribute(ATRIBUTOS[17])
        model.texto_resumo = no.getAttribute(ATRIBUTOS[18])
        model.outras_informacoes_relevantes = no.getAttribute(ATRIBUTOS[19])

        if not model.texto_resumo:
            for filho in no.getElementsByTagName('RESUMO-CV'):
                model.texto_resumo = filho.getAttribute('TEXTO-RESUMO-CV-RH')

        if not model.outras_informacoes_relevantes:
            for filho in no.getElementsByTagName('OUTRAS-INFORMACOES-RELEVANTES'):
                model.outras_informacoes_relevantes = filho.getAttribute('OUTRAS-INFORMACOES-RELEVANTES')

        return model


class EnderecoParser:
    def parse(self, no, dono):
        ATRIBUTOS = ['FLAG-DE-PREFERENCIA']
        FILHOS = ['ENDERECO-PROFISSIONAL', 'ENDERECO-RESIDENCIAL']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            model = self.get_model_profissional(filho, dono)
            model.save()
            dono.endereco_profissional = model

        for filho in no.getElementsByTagName(FILHOS[1]):
            model = self.get_model_residencial(filho, dono)
            model.save()
            dono.endereco_residencial = model

        if no.getAttribute(ATRIBUTOS[0] == 'ENDERECO_INSTITUCIONAL'):
            dono.endereco_preferencial = dono.endereco_profissional

        elif no.getAttribute(ATRIBUTOS[0] == 'ENDERECO_RESIDENCIAL'):
            dono.endereco_preferencial = dono.endereco_residencial

        dono.save()

    def get_model_residencial(self, no, dono):
        ATRIBUTOS_RESIDENCIAL = [
            'LOGRADOURO',
            'PAIS',
            'UF',
            'CEP',
            'CIDADE',
            'BAIRRO',
            'DDD',
            'TELEFONE',
            'RAMAL',
            'FAX',
            'CAIXA-POSTAL',
            'E-MAIL',
            'HOME-PAGE',
        ]
        verificarAtributos(no, ATRIBUTOS_RESIDENCIAL)

        model = dono.endereco_residencial
        if not model:
            model = Endereco()

        model.logradouro = no.getAttribute(ATRIBUTOS_RESIDENCIAL[0])
        model.pais = no.getAttribute(ATRIBUTOS_RESIDENCIAL[1])
        model.uf = no.getAttribute(ATRIBUTOS_RESIDENCIAL[2])
        model.cep = no.getAttribute(ATRIBUTOS_RESIDENCIAL[3])
        model.cidade = no.getAttribute(ATRIBUTOS_RESIDENCIAL[4])
        model.bairro = no.getAttribute(ATRIBUTOS_RESIDENCIAL[5])
        model.ddd = no.getAttribute(ATRIBUTOS_RESIDENCIAL[6])
        model.telefone = no.getAttribute(ATRIBUTOS_RESIDENCIAL[7])
        model.ramal = no.getAttribute(ATRIBUTOS_RESIDENCIAL[8])
        model.fax = no.getAttribute(ATRIBUTOS_RESIDENCIAL[9])
        model.caixa_postal = no.getAttribute(ATRIBUTOS_RESIDENCIAL[10])
        model.email = no.getAttribute(ATRIBUTOS_RESIDENCIAL[11])
        model.home_page = no.getAttribute(ATRIBUTOS_RESIDENCIAL[12])
        return model

    def get_model_profissional(self, no, dono):
        ATRIBUTOS_PROFISSIONAL = [
            'CODIGO-INSTITUICAO-EMPRESA',
            'NOME-INSTITUICAO-EMPRESA',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-UNIDADE',
            'NOME-UNIDADE',
            'LOGRADOURO-COMPLEMENTO',
            'PAIS',
            'UF',
            'CEP',
            'CIDADE',
            'BAIRRO',
            'DDD',
            'TELEFONE',
            'RAMAL',
            'FAX',
            'CAIXA-POSTAL',
            'E-MAIL',
            'HOME-PAGE',
        ]
        verificarAtributos(no, ATRIBUTOS_PROFISSIONAL)

        model = dono.endereco_profissional
        if not model:
            model = Endereco()

        model.codigo_instituicao_empresa = no.getAttribute(ATRIBUTOS_PROFISSIONAL[0])
        model.nome_instituicao_empresa = no.getAttribute(ATRIBUTOS_PROFISSIONAL[1])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS_PROFISSIONAL[2])
        model.nome_orgao = no.getAttribute(ATRIBUTOS_PROFISSIONAL[3])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS_PROFISSIONAL[4])
        model.nome_unidade = no.getAttribute(ATRIBUTOS_PROFISSIONAL[5])
        model.logradouro = no.getAttribute(ATRIBUTOS_PROFISSIONAL[6])
        model.pais = no.getAttribute(ATRIBUTOS_PROFISSIONAL[7])
        model.uf = no.getAttribute(ATRIBUTOS_PROFISSIONAL[8])
        model.cep = no.getAttribute(ATRIBUTOS_PROFISSIONAL[9])
        model.cidade = no.getAttribute(ATRIBUTOS_PROFISSIONAL[10])
        model.bairro = no.getAttribute(ATRIBUTOS_PROFISSIONAL[11])
        model.ddd = no.getAttribute(ATRIBUTOS_PROFISSIONAL[12])
        model.telefone = no.getAttribute(ATRIBUTOS_PROFISSIONAL[13])
        model.ramal = no.getAttribute(ATRIBUTOS_PROFISSIONAL[14])
        model.fax = no.getAttribute(ATRIBUTOS_PROFISSIONAL[15])
        model.caixa_postal = no.getAttribute(ATRIBUTOS_PROFISSIONAL[16])
        model.email = no.getAttribute(ATRIBUTOS_PROFISSIONAL[17])
        model.home_page = no.getAttribute(ATRIBUTOS_PROFISSIONAL[18])
        return model


class FormacaoAcademicaTitulacaoParser:
    def parse(self, no, dono):
        FILHOS = [
            'GRADUACAO',
            'ESPECIALIZACAO',
            'MESTRADO',
            'DOUTORADO',
            'POS-DOUTORADO',
            'LIVRE-DOCENCIA',
            'CURSO-TECNICO-PROFISSIONALIZANTE',
            'MESTRADO-PROFISSIONALIZANTE',
            'ENSINO-FUNDAMENTAL-PRIMEIRO-GRAU',
            'ENSINO-MEDIO-SEGUNDO-GRAU',
            'RESIDENCIA-MEDICA',
            'APERFEICOAMENTO',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            model = self.get_model_graduacao(filho)
            model.dado_geral = dono
            model.save()
            self.get_filhos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            model = self.get_model_especializacao(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[2]):
            model = self.get_model_mestrado(filho)
            model.dado_geral = dono
            model.save()
            self.get_filhos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[3]):
            model = self.get_model_doutorado(filho)
            model.dado_geral = dono
            model.save()
            self.get_filhos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[4]):
            model = self.get_model_pos_doutorado(filho)
            model.dado_geral = dono
            model.save()
            self.get_filhos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[5]):
            model = self.get_model_livre_docencia(filho)
            model.dado_geral = dono
            model.save()
            self.get_filhos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[6]):
            model = self.get_model_tecnico_profissionalizante(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[7]):
            model = self.get_model_mestrado(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[8]):
            model = self.get_model_ensino_fundamental_primeiro_grau(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[9]):
            model = self.get_model_ensino_medio_segundo_grau(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[10]):
            model = self.get_model_residencia_medica(filho)
            model.dado_geral = dono
            model.save()

        for filho in no.getElementsByTagName(FILHOS[11]):
            model = self.get_model_aperfeicoamento(filho)
            model.dado_geral = dono
            model.save()

    def get_filhos(self, no, model):
        for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
            parser = PalavraChaveParser()
            parser.parse(filho, model)

        for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
            parser = AreaConhecimentoParser()
            parser.parse(filho, model)

        for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
            parser = SetorAtividadeParser()
            parser.parse(filho, model)

    def get_model_tecnico_profissionalizante(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[4])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[5])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[6])
        model.nome_curso = no.getAttribute(ATRIBUTOS[7])
        model.status_curso = no.getAttribute(ATRIBUTOS[8])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[9])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[10])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[11]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[12])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[13])
        return model

    def get_model_ensino_fundamental_primeiro_grau(self, no):
        ATRIBUTOS = ['SEQUENCIA-FORMACAO', 'NIVEL', 'CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'STATUS-DO-CURSO', 'ANO-DE-INICIO', 'ANO-DE-CONCLUSAO']
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.status_curso = no.getAttribute(ATRIBUTOS[4])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[5])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[6])
        return model

    def get_model_ensino_medio_segundo_grau(self, no):
        ATRIBUTOS = ['SEQUENCIA-FORMACAO', 'NIVEL', 'CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'STATUS-DO-CURSO', 'ANO-DE-INICIO', 'ANO-DE-CONCLUSAO']
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.status_curso = no.getAttribute(ATRIBUTOS[4])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[5])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[6])
        return model

    def get_model_graduacao(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'TITULO-DO-TRABALHO-DE-CONCLUSAO-DE-CURSO',
            'NOME-DO-ORIENTADOR',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'CODIGO-AREA-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'NUMERO-ID-ORIENTADOR',
            'CODIGO-CURSO-CAPES',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[2])
        model.nome_orientador = no.getAttribute(ATRIBUTOS[3])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[4])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[8])
        model.nome_curso = no.getAttribute(ATRIBUTOS[9])
        model.codigo_area_curso = no.getAttribute(ATRIBUTOS[10])
        model.status_curso = no.getAttribute(ATRIBUTOS[11])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[12])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[13])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[14]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[15])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[16])
        model.numero_id_orientador = no.getAttribute(ATRIBUTOS[17])
        model.codigo_curso_capes = no.getAttribute(ATRIBUTOS[18])
        return model

    def get_model_aperfeicoamento(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'TITULO-DA-MONOGRAFIA',
            'NOME-DO-ORIENTADOR',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'CODIGO-AREA-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'CARGA-HORARIA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[2])
        model.nome_orientador = no.getAttribute(ATRIBUTOS[3])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[4])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[8])
        model.nome_curso = no.getAttribute(ATRIBUTOS[9])
        model.codigo_area_curso = no.getAttribute(ATRIBUTOS[10])
        model.status_curso = no.getAttribute(ATRIBUTOS[11])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[12])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[13])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[14]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[15])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[16])
        model.codigo_curso_capes = no.getAttribute(ATRIBUTOS[17])
        return model

    def get_model_especializacao(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'TITULO-DA-MONOGRAFIA',
            'NOME-DO-ORIENTADOR',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'CARGA-HORARIA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[2])
        model.nome_orientador = no.getAttribute(ATRIBUTOS[3])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[4])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[8])
        model.nome_curso = no.getAttribute(ATRIBUTOS[9])
        model.status_curso = no.getAttribute(ATRIBUTOS[10])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[11])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[12])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[13]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[14])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[15])
        model.carga_horaria = no.getAttribute(ATRIBUTOS[16])
        return model

    def get_model_mestrado(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'CODIGO-AREA-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'ANO-DE-OBTENCAO-DO-TITULO',
            'TITULO-DA-DISSERTACAO-TESE',
            'NOME-COMPLETO-DO-ORIENTADOR',
            'NUMERO-ID-ORIENTADOR',
            'CODIGO-CURSO-CAPES',
        ]
        verificarAtributos(no, ATRIBUTOS)
        FILHOS = ['PALAVRAS-CHAVE', 'AREAS-DO-CONHECIMENTO', 'SETORES-DE-ATIVIDADE']
        verificarFilhos(no, FILHOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[5])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[4])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[6])
        model.nome_curso = no.getAttribute(ATRIBUTOS[7])
        model.codigo_area_curso = no.getAttribute(ATRIBUTOS[8])
        model.status_curso = no.getAttribute(ATRIBUTOS[9])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[10])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[11])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[12]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[13])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[14])
        model.ano_obtencao = no.getAttribute(ATRIBUTOS[15])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[16])
        model.nome_orientador = no.getAttribute(ATRIBUTOS[17])
        model.numero_id_orientador = no.getAttribute(ATRIBUTOS[18])
        model.codigo_curso_capes = no.getAttribute(ATRIBUTOS[19])
        return model

    def get_model_doutorado(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-CURSO',
            'NOME-CURSO',
            'CODIGO-AREA-CURSO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'ANO-DE-OBTENCAO-DO-TITULO',
            'TITULO-DA-DISSERTACAO-TESE',
            'NOME-COMPLETO-DO-ORIENTADOR',
            'TIPO-DOUTORADO',
            'CODIGO-INSTITUICAO-DOUT',
            'NOME-INSTITUICAO-DOUT',
            'CODIGO-INSTITUICAO-OUTRA-DOUT',
            'NOME-INSTITUICAO-OUTRA-DOUT',
            'NOME-ORIENTADOR-DOUT',
            'NUMERO-ID-ORIENTADOR',
            'CODIGO-CURSO-CAPES',
        ]
        verificarAtributos(no, ATRIBUTOS)
        FILHOS = ['PALAVRAS-CHAVE', 'AREAS-DO-CONHECIMENTO', 'SETORES-DE-ATIVIDADE']
        verificarFilhos(no, FILHOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[5])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[4])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[6])
        model.nome_curso = no.getAttribute(ATRIBUTOS[7])
        model.codigo_area_curso = no.getAttribute(ATRIBUTOS[8])
        model.status_curso = no.getAttribute(ATRIBUTOS[9])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[10])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[11])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[12]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[13])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[14])
        model.ano_obtencao = no.getAttribute(ATRIBUTOS[15])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[16])
        model.nome_orientador = no.getAttribute(ATRIBUTOS[17])
        model.tipo_doutorado = no.getAttribute(ATRIBUTOS[18])
        model.codigo_instituicao_dout = no.getAttribute(ATRIBUTOS[19])
        model.nome_instituicao_dout = no.getAttribute(ATRIBUTOS[20])
        model.codigo_instituicao_outra_dout = no.getAttribute(ATRIBUTOS[21])
        model.nome_instituicao_outra_dout = no.getAttribute(ATRIBUTOS[22])
        model.nome_orientador_dout = no.getAttribute(ATRIBUTOS[23])
        model.numero_id_orientador = no.getAttribute(ATRIBUTOS[24])
        model.codigo_curso_capes = no.getAttribute(ATRIBUTOS[25])
        return model

    def get_model_residencia_medica(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'STATUS-DO-CURSO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'TITULO-DA-RESIDENCIA-MEDICA',
            'NUMERO-DO-REGISTRO',
        ]
        verificarAtributos(no, ATRIBUTOS)
        FILHOS = ['PALAVRAS-CHAVE', 'AREAS-DO-CONHECIMENTO', 'SETORES-DE-ATIVIDADE']
        verificarFilhos(no, FILHOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.status_curso = no.getAttribute(ATRIBUTOS[4])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[5])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[6])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[8])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[9])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[10])
        model.numero_registro = no.getAttribute(ATRIBUTOS[11])
        return model

    def get_model_livre_docencia(self, no):
        ATRIBUTOS = ['SEQUENCIA-FORMACAO', 'NIVEL', 'CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'ANO-DE-OBTENCAO-DO-TITULO', 'TITULO-DO-TRABALHO']
        verificarAtributos(no, ATRIBUTOS)
        FILHOS = ['PALAVRAS-CHAVE', 'AREAS-DO-CONHECIMENTO', 'SETORES-DE-ATIVIDADE']
        verificarFilhos(no, FILHOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.ano_obtencao = no.getAttribute(ATRIBUTOS[4])
        model.titulo_trabalho_conclusao = no.getAttribute(ATRIBUTOS[5])
        return model

    def get_model_pos_doutorado(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FORMACAO',
            'NIVEL',
            'CODIGO-INSTITUICAO',
            'NOME-INSTITUICAO',
            'ANO-DE-INICIO',
            'ANO-DE-CONCLUSAO',
            'ANO-DE-OBTENCAO-DO-TITULO',
            'FLAG-BOLSA',
            'CODIGO-AGENCIA-FINANCIADORA',
            'NOME-AGENCIA',
            'STATUS-DO-ESTAGIO',
            'STATUS-DO-CURSO',
            'NUMERO-ID-ORIENTADOR',
            'CODIGO-CURSO-CAPES',
        ]
        verificarAtributos(no, ATRIBUTOS)
        FILHOS = ['PALAVRAS-CHAVE', 'AREAS-DO-CONHECIMENTO', 'SETORES-DE-ATIVIDADE']
        verificarFilhos(no, FILHOS)

        model = FormacaoAcademicaTitulacao()
        model.tipo = no.tagName
        model.sequencia_formacao = no.getAttribute(ATRIBUTOS[0])
        model.nivel = no.getAttribute(ATRIBUTOS[1])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[3])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[4])
        model.ano_conclusao = no.getAttribute(ATRIBUTOS[5])
        model.ano_obtencao = no.getAttribute(ATRIBUTOS[6])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.codigo_agencia_financiadora = no.getAttribute(ATRIBUTOS[8])
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[9])
        model.status_estagio = no.getAttribute(ATRIBUTOS[10])
        model.status_curso = no.getAttribute(ATRIBUTOS[11])
        model.numero_id_orientador = no.getAttribute(ATRIBUTOS[12])
        model.codigo_curso_capes = no.getAttribute(ATRIBUTOS[13])
        return model


class PalavraChaveParser:
    def parse(self, no, dono):
        ATRIBUTOS = ['PALAVRA-CHAVE-1', 'PALAVRA-CHAVE-2', 'PALAVRA-CHAVE-3', 'PALAVRA-CHAVE-4', 'PALAVRA-CHAVE-5', 'PALAVRA-CHAVE-6']
        verificarAtributos(no, ATRIBUTOS)

        ordem = 0
        for atributo in ATRIBUTOS:
            ordem += 1
            model = self.get_model(no, ordem, atributo)
            if model.palavra:
                model.save()
                dono.palavras_chave.add(model)

    def get_model(self, no, ordem, atributo):
        model = PalavraChave()
        model.ordem = ordem
        model.palavra = no.getAttribute(atributo)
        return model


class AreaConhecimentoParser:
    def parse(self, no, dono):
        FILHOS = ['AREA-DO-CONHECIMENTO-1', 'AREA-DO-CONHECIMENTO-2', 'AREA-DO-CONHECIMENTO-3']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            model = self.get_model(filho, 1)
            model.save()
            dono.areas_conhecimento.add(model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            model = self.get_model(filho, 2)
            model.save()
            dono.areas_conhecimento.add(model)

        for filho in no.getElementsByTagName(FILHOS[2]):
            model = self.get_model(filho, 3)
            model.save()
            dono.areas_conhecimento.add(model)

    def get_model(self, no, ordem):
        ATRIBUTOS = ['NOME-GRANDE-AREA-DO-CONHECIMENTO', 'NOME-DA-AREA-DO-CONHECIMENTO', 'NOME-DA-SUB-AREA-DO-CONHECIMENTO', 'NOME-DA-ESPECIALIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AreaConhecimento()
        model.nome_grande_area = no.getAttribute(ATRIBUTOS[0])
        model.nome_area = no.getAttribute(ATRIBUTOS[1])
        model.nome_sub_area = no.getAttribute(ATRIBUTOS[2])
        model.nome_especializacao = no.getAttribute(ATRIBUTOS[3])
        return model


class SetorAtividadeParser:
    def parse(self, no, dono):
        ATRIBUTOS = ['SETOR-DE-ATIVIDADE-1', 'SETOR-DE-ATIVIDADE-2', 'SETOR-DE-ATIVIDADE-3']
        verificarAtributos(no, ATRIBUTOS)

        ordem = 0
        for atributo in ATRIBUTOS:
            ordem += 1
            model = self.get_model(no, ordem, atributo)
            if model:
                model.save()
                dono.setores_atividade.add(model)
                dono.save()

    def get_model(self, no, ordem, atributo):
        model = SetorAtividade()
        model.ordem = ordem
        model.setor = no.getAttribute(atributo)
        if model.setor:
            return model
        else:
            return None


class AtuacaoProfissionalParser:
    def parse(self, no, dono):
        FILHOS = [
            'VINCULOS',
            'ATIVIDADES-DE-DIRECAO-E-ADMINISTRACAO',
            'ATIVIDADES-DE-PESQUISA-E-DESENVOLVIMENTO',
            'ATIVIDADES-DE-ENSINO',
            'ATIVIDADES-DE-ESTAGIO',
            'ATIVIDADES-DE-SERVICO-TECNICO-ESPECIALIZADO',
            'ATIVIDADES-DE-EXTENSAO-UNIVERSITARIA',
            'ATIVIDADES-DE-TREINAMENTO-MINISTRADO',
            'OUTRAS-ATIVIDADES-TECNICO-CIENTIFICA',
            'ATIVIDADES-DE-CONSELHO-COMISSAO-E-CONSULTORIA',
            'ATIVIDADES-DE-PARTICIPACAO-EM-PROJETO',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no)
        model.dado_geral = dono
        model.save()

        for filho in no.getElementsByTagName('ATIVIDADES-DE-PARTICIPACAO-EM-PROJETO'):
            for atuacao in filho.getElementsByTagName('PARTICIPACAO-EM-PROJETO'):
                parser = ParticipacaoProjetoParser()
                parser.parse(atuacao, model)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = VinculoParser()
            parser.parse(filho, model)
            #
            # for filho_tag in FILHOS:
            #     if filho_tag == 'VINCULOS':
            #         for filho in no.getElementsByTagName(filho_tag):
            #             parser = VinculoParser()
            #             parser.parse(filho, model)
            #     else:
            #         for filho in no.getElementsByTagName(filho_tag):
            #             parser = AtividadeProfissionalParser()
            #             parser.parse(filho, model)

    def get_model(self, no):
        ATRIBUTOS = ['CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'SEQUENCIA-ATIVIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtuacaoProfissional()
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[1])
        model.sequencia_atividade = no.getAttribute(ATRIBUTOS[2])
        return model


class AreaAtuacaoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.dado_geral = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-AREA-DE-ATUACAO',
            'NOME-GRANDE-AREA-DO-CONHECIMENTO',
            'NOME-DA-AREA-DO-CONHECIMENTO',
            'NOME-DA-SUB-AREA-DO-CONHECIMENTO',
            'NOME-DA-ESPECIALIDADE',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = AreaAtuacao()
        model.sequencia_area_atuacao = no.getAttribute(ATRIBUTOS[0])
        nome_grande_area_conhecimento = no.getAttribute(ATRIBUTOS[1])
        model.nome_grande_area_conhecimento = AreaConhecimento.get_descricao_grande_area(nome_grande_area_conhecimento)
        model.nome_area_conhecimento = no.getAttribute(ATRIBUTOS[2])
        model.nome_sub_area_conhecimento = no.getAttribute(ATRIBUTOS[3])
        model.nome_especialidade_conhecimento = no.getAttribute(ATRIBUTOS[4])
        return model


class ParticipacaoProjetoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.atuacao_profissional = dono
        model.save()

        for filho in no.getElementsByTagName('PROJETO-DE-PESQUISA'):
            parser = ProjetoPesquisaParser()
            parser.parse(filho, model)

    def get_model(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-FUNCAO-ATIVIDADE',
            'FLAG-PERIODO',
            'MES-INICIO',
            'ANO-INICIO',
            'MES-FIM',
            'ANO-FIM',
            'CODIGO-ORGAO',
            'NOME-ORGAO',
            'CODIGO-UNIDADE',
            'NOME-UNIDADE',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = ParticipacaoProjeto()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])
        return model


class ProjetoPesquisaParser:
    def parse(self, no, dono):
        FILHOS = ['EQUIPE-DO-PROJETO', 'FINANCIADORES-DO-PROJETO', 'PRODUCOES-CT-DO-PROJETO', 'ORIENTACOES']
        verificarFilhos(no, FILHOS)

        model = self.get_model(no)
        model.participacao_projeto = dono
        model.save()

        for filho in no.getElementsByTagName(FILHOS[0]):
            for integrante in filho.getElementsByTagName('INTEGRANTES-DO-PROJETO'):
                parser = IntegranteProjetoParser()
                parser.parse(integrante, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            for financiador in filho.getElementsByTagName('FINANCIADOR-DO-PROJETO'):
                parser = FinanciadorProjetoParser()
                parser.parse(financiador, model)

                # for filho in no.getElementsByTagName(FILHOS[2]):
                #     for producao in filho.getElementsByTagName('PRODUCAO-CT-DO-PROJETO'):
                #         parser = ProducaoProjetoParser()
                #         parser.parse(producao, model)
                #
                # for filho in no.getElementsByTagName(FILHOS[3]):
                #     for orientacao in filho.getElementsByTagName('ORIENTACAO'):
                #         parser = OrientacaoProjetoParser()
                #         parser.parse(orientacao, model)

    def get_model(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-PROJETO',
            'ANO-INICIO',
            'ANO-FIM',
            'NOME-DO-PROJETO',
            'SITUACAO',
            'NATUREZA',
            'NUMERO-GRADUACAO',
            'NUMERO-ESPECIALIZACAO',
            'NUMERO-MESTRADO-ACADEMICO',
            'NUMERO-MESTRADO-PROF',
            'NUMERO-DOUTORADO',
            'DESCRICAO-DO-PROJETO',
            'IDENTIFICADOR-PROJETO',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = ProjetoPesquisa()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[1])
        model.ano_fim = no.getAttribute(ATRIBUTOS[2])
        model.nome = no.getAttribute(ATRIBUTOS[3])
        model.situacao = no.getAttribute(ATRIBUTOS[4])
        model.natureza = no.getAttribute(ATRIBUTOS[5])
        model.descricao = no.getAttribute(ATRIBUTOS[11])
        return model


class IntegranteProjetoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.projeto_pesquisa = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['NOME-COMPLETO', 'NOME-PARA-CITACAO', 'ORDEM-DE-INTEGRACAO', 'FLAG-RESPONSAVEL']
        verificarAtributos(no, ATRIBUTOS)

        model = IntegranteProjeto()
        model.nome_completo = no.getAttribute(ATRIBUTOS[0])
        model.nome_citacao = no.getAttribute(ATRIBUTOS[1])
        model.ordem_integracao = no.getAttribute(ATRIBUTOS[2])
        model.flag_responsavel = parse_boolean(no.getAttribute(ATRIBUTOS[3]))
        return model


class FinanciadorProjetoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.projeto_pesquisa = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-FINANCIADOR', 'CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'NATUREZA']
        verificarAtributos(no, ATRIBUTOS)

        model = IntegranteProjeto()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.natureza = no.getAttribute(ATRIBUTOS[3])
        return model


class VinculoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.atuacao_profissional = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = [
            'SEQUENCIA-HISTORICO',
            'TIPO-DE-VINCULO',
            'ENQUADRAMENTO-FUNCIONAL',
            'CARGA-HORARIA-SEMANAL',
            'FLAG-DEDICACAO-EXCLUSIVA',
            'MES-INICIO',
            'ANO-INICIO',
            'MES-FIM',
            'ANO-FIM',
            'OUTRAS-INFORMACOES',
            'FLAG-VINCULO-EMPREGATICIO',
            'OUTRO-VINCULO-INFORMADO',
            'OUTRO-ENQUADRAMENTO-FUNCIONAL-INFORMADO',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = Vinculo()
        model.sequencia_historico = no.getAttribute(ATRIBUTOS[0])
        model.tipo_vinculo = no.getAttribute(ATRIBUTOS[1])
        model.enquadramento_funcional = no.getAttribute(ATRIBUTOS[2])
        model.carga_horaria = no.getAttribute(ATRIBUTOS[3])
        model.flag_dedicacao_exclusiva = parse_boolean(no.getAttribute(ATRIBUTOS[4]))
        model.mes_inicio = no.getAttribute(ATRIBUTOS[5])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[6])
        model.mes_fim = no.getAttribute(ATRIBUTOS[7])
        model.ano_fim = no.getAttribute(ATRIBUTOS[8])
        model.outras_informacoes = no.getAttribute(ATRIBUTOS[9])
        model.flag_vinculo_empregaticio = parse_boolean(no.getAttribute(ATRIBUTOS[10]))
        model.outro_vinculo_informado = no.getAttribute(ATRIBUTOS[11])
        model.outro_enquadramento_funcional_informado = no.getAttribute(ATRIBUTOS[12])
        return model


"""
class AtividadeProfissionalParser:
    def parse(self, no, dono):

        for filho in no.getElementsByTagName('DIRECAO-E-ADMINISTRACAO'):
            model = self.get_model_direcao_administracao(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('PESQUISA-E-DESENVOLVIMENTO'):
            model = self.get_model_pesquisa_desenvolvimento(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('ENSINO'):
            model = self.get_model_ensino(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('ESTAGIO'):
            model = self.get_model_estagio(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('SERVICO-TECNICO-ESPECIALIZADO'):
            model = self.get_model_servico_tecnico_especializado(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('EXTENSAO-UNIVERSITARIA'):
            model = self.get_model_extensao_universitaria(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('TREINAMENTO-MINISTRADO'):
            model = self.get_model_treinamento_ministrado(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('OUTRA-ATIVIDADE-TECNICO-CIENTIFICA'):
            model = self.get_model_outra_atividade_tecnico_cientifica(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('CONSELHO-COMISSAO-E-CONSULTORIA'):
            model = self.get_model_conselho_comissao_consultoria(filho, dono)
            model.save()

        for filho in no.getElementsByTagName('PARTICIPACAO-EM-PROJETO'):
            model = self.get_model_participacao_projeto(filho, dono)
            model.save()


    def get_model_direcao_administracao(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'FORMATO-CARGO-OU-FUNCAO', 'CARGO-OU-FUNCAO', 'NOME-UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.formato_cargo_funcao = no.getAttribute(ATRIBUTOS[9])
        model.cargo_funcao = no.getAttribute(ATRIBUTOS[10])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[11])
        return model


    def get_model_pesquisa_desenvolvimento(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])

        model.save()

        for filho in no.getElementsByTagName('LINHA-DE-PESQUISA'):
            parser = LinhaPesquisaParser()
            parser.parse(filho, model)

        return model


    def get_model_ensino(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'TIPO-ENSINO', 'MES-INICIO',
                     'ANO-INICIO', 'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO',
                     'CODIGO-CURSO', 'NOME-CURSO']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.tipo_ensino = no.getAttribute(ATRIBUTOS[2])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[3])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[4])
        model.mes_fim = no.getAttribute(ATRIBUTOS[5])
        model.ano_fim = no.getAttribute(ATRIBUTOS[6])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[7])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[8])
        model.codigo_curso = no.getAttribute(ATRIBUTOS[9])
        model.nome_curso = no.getAttribute(ATRIBUTOS[10])

        model.save()

        for filho in no.getElementsByTagName('DISCIPLINA'):
            parser = DisciplinaParser()
            parser.parse(filho, model)

        return model


    def get_model_estagio(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE', 'ESTAGIO-REALIZADO']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])
        model.atividade_realizada = no.getAttribute(ATRIBUTOS[10])
        return model


    def get_model_servico_tecnico_especializado(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE', 'SERVICO-REALIZADO']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])
        model.atividade_realizada = no.getAttribute(ATRIBUTOS[10])
        return model


    def get_model_extensao_universitaria(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE', 'ATIVIDADE-DE-EXTENSAO-REALIZADA']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])
        model.atividade_realizada = no.getAttribute(ATRIBUTOS[10])
        return model


    def get_model_treinamento_ministrado(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])

        model.save()

        for filho in no.getElementsByTagName('TREINAMENTO'):
            parser = TreinamentoParser()
            parser.parse(filho, model)

        return model


    def get_model_outra_atividade_tecnico_cientifica(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'ATIVIDADE-DE-EXTENSAO-REALIZADA', 'NOME-UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.atividade_realizada = no.getAttribute(ATRIBUTOS[9])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[10])
        return model


    def get_model_conselho_comissao_consultoria(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE', 'ESPECIFICACAO']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])
        model.especificacao = no.getAttribute(ATRIBUTOS[10])
        return model


    def get_model_participacao_projeto(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-FUNCAO-ATIVIDADE', 'FLAG-PERIODO', 'MES-INICIO', 'ANO-INICIO',
                     'MES-FIM', 'ANO-FIM', 'CODIGO-ORGAO', 'NOME-ORGAO', 'CODIGO-UNIDADE',
                     'NOME-UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model = AtividadeProfissional()
        model.atuacao_profissional = dono
        model.tipo = no.tagName
        model.sequencia_funcao_atividade = no.getAttribute(ATRIBUTOS[0])
        model.flag_periodo = no.getAttribute(ATRIBUTOS[1])
        model.mes_inicio = no.getAttribute(ATRIBUTOS[2])
        model.ano_inicio = no.getAttribute(ATRIBUTOS[3])
        model.mes_fim = no.getAttribute(ATRIBUTOS[4])
        model.ano_fim = no.getAttribute(ATRIBUTOS[5])
        model.codigo_orgao = no.getAttribute(ATRIBUTOS[6])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[7])
        model.codigo_unidade = no.getAttribute(ATRIBUTOS[8])
        model.nome_unidade = no.getAttribute(ATRIBUTOS[9])

        model.save()

        for filho in no.getElementsByTagName('PROJETO-DE-PESQUISA'):
            parser = ProjetoPesquisaParser()
            parser.parse(filho, model)

        return model


class DisciplinaParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.atividade_profissional = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-ESPECIFICACAO']
        verificarAtributos(no, ATRIBUTOS)
        model = Disciplina()
        model.sequencia_especificacao = no.getAttribute(ATRIBUTOS[0])
        texto = getText(no)
        return model

class LinhaPesquisaParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.atividade_profissional = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-LINHA', 'TITULO-DA-LINHA-DE-PESQUISA',
                     'FLAG-LINHA-DE-PESQUISA-ATIVA', 'OBJETIVOS-LINHA-DE-PESQUISA']
        verificarAtributos(no, ATRIBUTOS)

        model = LinhaPesquisa()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.flag_ativa = parse_boolean(no.getAttribute(ATRIBUTOS[2]))
        model.objetivos = no.getAttribute(ATRIBUTOS[3])
        return model

class TreinamentoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.atividade_profissional = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-ESPECIFICACAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Treinamento()
        model.sequencia_especificacao = no.getAttribute(ATRIBUTOS[0])
        texto = getText(no)
        return model


class ProducaoProjetoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.projeto_pesquisa = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO-CT', 'TITULO-DA-PRODUCAO-CT', 'TIPO-PRODUCAO-CT']
        verificarAtributos(no, ATRIBUTOS)

        model = IntegranteProjeto()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.tipo = no.getAttribute(ATRIBUTOS[2])
        return model


class OrientacaoProjetoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.projeto_pesquisa = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['SEQUENCIA-ORIENTACAO', 'TITULO-ORIENTACAO', 'TIPO-ORIENTACAO']
        verificarAtributos(no, ATRIBUTOS)

        model = IntegranteProjeto()
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.tipo = no.getAttribute(ATRIBUTOS[2])
        return model


class IdiomaParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.dado_geral = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['IDIOMA', 'DESCRICAO-DO-IDIOMA', 'PROFICIENCIA-DE-LEITURA',
                     'PROFICIENCIA-DE-FALA', 'PROFICIENCIA-DE-ESCRITA',
                     'PROFICIENCIA-DE-COMPREENSAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Idioma()
        model.idioma = no.getAttribute(ATRIBUTOS[0])
        model.descricao = no.getAttribute(ATRIBUTOS[0])
        model.proficiencia_leitura = no.getAttribute(ATRIBUTOS[0])
        model.proficiencia_fala = no.getAttribute(ATRIBUTOS[0])
        model.proficiencia_escrita = no.getAttribute(ATRIBUTOS[0])
        model.proficiencia_compreensao = no.getAttribute(ATRIBUTOS[0])
        return model
"""


class PremioTituloParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.dado_geral = dono
        model.save()

    def get_model(self, no):
        ATRIBUTOS = ['NOME-DO-PREMIO-OU-TITULO', 'NOME-DA-ENTIDADE-PROMOTORA', 'ANO-DA-PREMIACAO', 'NOME-DO-PREMIO-OU-TITULO-INGLES']
        verificarAtributos(no, ATRIBUTOS)

        model = PremioTitulo()
        model.nome_premio_titulo = no.getAttribute(ATRIBUTOS[0])
        model.nome_entidade_promotora = no.getAttribute(ATRIBUTOS[1])
        model.ano_premiacao = no.getAttribute(ATRIBUTOS[2])
        model.nome_do_premio_ou_titulo_ingles = no.getAttribute(ATRIBUTOS[3])
        return model


################################
#    PRODUCAO BIBLIOGRAFICA    #
################################
class ProducaoBibliograficaParser:
    def parse(self, no, dono):
        FILHOS = [
            'TRABALHOS-EM-EVENTOS',
            'ARTIGOS-PUBLICADOS',
            'LIVROS-E-CAPITULOS',
            'TEXTOS-EM-JORNAIS-OU-REVISTAS',
            'DEMAIS-TIPOS-DE-PRODUCAO-BIBLIOGRAFICA',
            'ARTIGOS-ACEITOS-PARA-PUBLICACAO',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_trabalhos_eventos(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_artigos_publicados(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_livros_capitulos(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_texto_jornais_revistas(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_demais_tipos_producao_bibliografia(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[5]):
            self.get_artigos_aceitos(filho, dono)

    def get_filhos(self, no, model):
        try:
            model.save()
            for filho in no.getElementsByTagName('AUTORES'):
                parser = AutorParser()
                parser.parse(filho, model)
            for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
                parser = PalavraChaveParser()
                parser.parse(filho, model)
            for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
                parser = AreaConhecimentoParser()
                parser.parse(filho, model)
            for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
                parser = SetorAtividadeParser()
                parser.parse(filho, model)
            for filho in no.getElementsByTagName('INFORMACOES-ADICIONAIS'):
                parser = InformacaoAdicionalParser()
                parser.parse(filho, model)
        except Exception:
            pass

    def get_trabalhos_eventos(self, no, dono):
        FILHOS = ['TRABALHO-EM-EVENTOS']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = TrabalhoEventoParser()
            parser.parse(filho, dono)

    def get_artigos_publicados(self, no, dono):
        FILHOS = ['ARTIGO-PUBLICADO']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = ArtigoParser()
            parser.parse(filho, dono)

    def get_livros_capitulos(self, no, dono):
        FILHOS = ['LIVROS-PUBLICADOS-OU-ORGANIZADOS', 'CAPITULOS-DE-LIVROS-PUBLICADOS']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            FILHOS_LIVRO = ['LIVRO-PUBLICADO-OU-ORGANIZADO']
            verificarFilhos(filho, FILHOS)
            for livro in filho.getElementsByTagName(FILHOS_LIVRO[0]):
                parser = LivroParser()
                parser.parse(livro, dono)
        for filho in no.getElementsByTagName(FILHOS[1]):
            FILHOS_CAPITULO = ['CAPITULO-DE-LIVRO-PUBLICADO']
            verificarFilhos(filho, FILHOS)
            for capitulo in filho.getElementsByTagName(FILHOS_CAPITULO[0]):
                parser = CapituloParser()
                parser.parse(capitulo, dono)

    def get_texto_jornais_revistas(self, no, dono):
        FILHOS = ['TEXTO-EM-JORNAL-OU-REVISTA']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = TextoJonalRevistaParser()
            parser.parse(filho, dono)

    def get_demais_tipos_producao_bibliografia(self, no, dono):
        FILHOS = ['OUTRA-PRODUCAO-BIBLIOGRAFICA', 'PARTITURA-MUSICAL', 'PREFACIO-POSFACIO', 'TRADUCAO']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = OutraProducaoBibliograficaParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            parser = PartituraParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            parser = PrefacioPosfacioParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            parser = TraducaoParser()
            parser.parse(filho, dono)

    def get_artigos_aceitos(self, no, dono):
        FILHOS = ['ARTIGO-ACEITO-PARA-PUBLICACAO']
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = ArtigoParser()
            parser.parse(filho, dono)


class TrabalhoEventoParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-TRABALHO',
            'DETALHAMENTO-DO-TRABALHO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            model = self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            model = self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = TrabalhoEvento()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-TRABALHO',
            'ANO-DO-TRABALHO',
            'PAIS-DO-EVENTO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'CLASSIFICACAO-DO-EVENTO',
            'NOME-DO-EVENTO',
            'CIDADE-DO-EVENTO',
            'ANO-DE-REALIZACAO',
            'TITULO-DOS-ANAIS-OU-PROCEEDINGS',
            'VOLUME',
            'FASCICULO',
            'SERIE',
            'PAGINA-INICIAL',
            'PAGINA-FINAL',
            'ISBN',
            'NOME-DA-EDITORA',
            'CIDADE-DA-EDITORA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.classificacao_evento = no.getAttribute(ATRIBUTOS[0])
        model.nome_evento = no.getAttribute(ATRIBUTOS[1])
        model.cidade_evento = no.getAttribute(ATRIBUTOS[2])
        model.ano_realizacao = no.getAttribute(ATRIBUTOS[3])
        model.titulo_anais_proceeding = no.getAttribute(ATRIBUTOS[4])
        model.volume = no.getAttribute(ATRIBUTOS[5])
        model.fasciculo = no.getAttribute(ATRIBUTOS[6])
        model.serie = no.getAttribute(ATRIBUTOS[7])
        model.pagina_inicial = no.getAttribute(ATRIBUTOS[8])
        model.pagina_final = no.getAttribute(ATRIBUTOS[9])
        model.isbn = no.getAttribute(ATRIBUTOS[10])
        model.nome_editora = no.getAttribute(ATRIBUTOS[11])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[12])
        return model


class ArtigoParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-ARTIGO',
            'DETALHAMENTO-DO-ARTIGO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Artigo()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-ARTIGO',
            'ANO-DO-ARTIGO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.tagName
        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'TITULO-DO-PERIODICO-OU-REVISTA',
            'ISSN',
            'VOLUME',
            'FASCICULO',
            'SERIE',
            'PAGINA-INICIAL',
            'PAGINA-FINAL',
            'LOCAL-DE-PUBLICACAO',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.tagName
        model.titulo_periodico_revista = no.getAttribute(ATRIBUTOS[0])
        model.issn = no.getAttribute(ATRIBUTOS[1])
        try:
            if model.issn:
                qs = PeriodicoRevista.objects.filter(issn=model.issn)
                if qs.exists():
                    periodico = qs[0]
                else:
                    periodico, _created = PeriodicoRevista.objects.get_or_create(issn=model.issn, nome=model.titulo_periodico_revista)
                model.periodico = periodico
        except Exception:
            pass
        model.volume = no.getAttribute(ATRIBUTOS[2])
        model.fasciculo = no.getAttribute(ATRIBUTOS[3])
        model.serie = no.getAttribute(ATRIBUTOS[4])
        model.pagina_inicial = no.getAttribute(ATRIBUTOS[5])
        model.pagina_final = no.getAttribute(ATRIBUTOS[6])
        model.local_publicacao = no.getAttribute(ATRIBUTOS[7])
        return model


class LivroParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-LIVRO',
            'DETALHAMENTO-DO-LIVRO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Livro()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'TIPO',
            'NATUREZA',
            'TITULO-DO-LIVRO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[6])
        model.home_page = no.getAttribute(ATRIBUTOS[7])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[8]))
        model.doi = no.getAttribute(ATRIBUTOS[9])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'NUMERO-DE-VOLUMES',
            'NUMERO-DE-PAGINAS',
            'ISBN',
            'NUMERO-DA-EDICAO-REVISAO',
            'NUMERO-DA-SERIE',
            'CIDADE-DA-EDITORA',
            'NOME-DA-EDITORA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.numero_volumes = no.getAttribute(ATRIBUTOS[0])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[1])
        model.isbn = no.getAttribute(ATRIBUTOS[2])
        model.numero_edicao_revisao = no.getAttribute(ATRIBUTOS[3])
        model.numero_serie = no.getAttribute(ATRIBUTOS[4])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[5])
        model.nome_editora = no.getAttribute(ATRIBUTOS[6])
        return model


class CapituloParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-CAPITULO',
            'DETALHAMENTO-DO-CAPITULO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Capitulo()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'TIPO',
            'TITULO-DO-CAPITULO-DO-LIVRO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'TITULO-DO-LIVRO',
            'NUMERO-DE-VOLUMES',
            'PAGINA-INICIAL',
            'PAGINA-FINAL',
            'ISBN',
            'ORGANIZADORES',
            'NUMERO-DA-EDICAO-REVISAO',
            'NUMERO-DA-SERIE',
            'CIDADE-DA-EDITORA',
            'NOME-DA-EDITORA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.titulo_livro = no.getAttribute(ATRIBUTOS[0])
        model.numero_volumes = no.getAttribute(ATRIBUTOS[1])
        model.pagina_inicial = no.getAttribute(ATRIBUTOS[2])
        model.pagina_final = no.getAttribute(ATRIBUTOS[3])
        model.isbn = no.getAttribute(ATRIBUTOS[4])
        model.organizadores = no.getAttribute(ATRIBUTOS[5])
        model.numero_edicao_revisao = no.getAttribute(ATRIBUTOS[6])
        model.numero_serie = no.getAttribute(ATRIBUTOS[7])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[8])
        model.nome_editora = no.getAttribute(ATRIBUTOS[9])
        return model


class TextoJonalRevistaParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-TEXTO',
            'DETALHAMENTO-DO-TEXTO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = TextoJonalRevista()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-TEXTO',
            'ANO-DO-TEXTO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['TITULO-DO-JORNAL-OU-REVISTA', 'ISSN', 'DATA-DE-PUBLICACAO', 'VOLUME', 'PAGINA-INICIAL', 'PAGINA-FINAL', 'LOCAL-DE-PUBLICACAO']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo_jonal_revista = no.getAttribute(ATRIBUTOS[0])
        model.issn = no.getAttribute(ATRIBUTOS[1])
        model.data_publicacao = parse_date(no.getAttribute(ATRIBUTOS[2]))
        model.volume = no.getAttribute(ATRIBUTOS[3])
        model.pagina_inicial = no.getAttribute(ATRIBUTOS[4])
        model.pagina_final = no.getAttribute(ATRIBUTOS[5])
        model.local_publicacao = no.getAttribute(ATRIBUTOS[6])
        return model


class OutraProducaoBibliograficaParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRA-PRODUCAO',
            'DETALHAMENTO-DE-OUTRA-PRODUCAO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = OutraProducaoBibliografica()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['EDITORA', 'CIDADE-DA-EDITORA', 'NUMERO-DE-PAGINAS', 'ISSN-ISBN']
        verificarAtributos(no, ATRIBUTOS)

        model.editora = no.getAttribute(ATRIBUTOS[0])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[1])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[2])
        model.issn_isbn = no.getAttribute(ATRIBUTOS[3])
        return model


class PartituraParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTITURA',
            'DETALHAMENTO-DA-PARTITURA',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Partitura()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FORMACAO-INSTRUMENTAL', 'EDITORA', 'CIDADE-DA-EDITORA', 'NUMERO-DE-PAGINAS', 'NUMERO-DO-CATALOGO']
        verificarAtributos(no, ATRIBUTOS)

        model.formacao_instrumental = no.getAttribute(ATRIBUTOS[0])
        model.editora = no.getAttribute(ATRIBUTOS[1])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[2])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[3])
        model.numero_catalogo = no.getAttribute(ATRIBUTOS[4])
        return model


class PrefacioPosfacioParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-PREFACIO-POSFACIO',
            'DETALHAMENTO-DO-PREFACIO-POSFACIO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = PrefacioPosfacio()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'TIPO',
            'NATUREZA',
            'TITULO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[6])
        model.home_page = no.getAttribute(ATRIBUTOS[7])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[8]))
        model.doi = no.getAttribute(ATRIBUTOS[9])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'NOME-DO-AUTOR-DA-PUBLICACAO',
            'TITULO-DA-PUBLICACAO',
            'ISSN-ISBN',
            'NUMERO-DA-EDICAO-REVISAO',
            'VOLUME',
            'SERIE',
            'FASCICULO',
            'EDITORA-DO-PREFACIO-POSFACIO',
            'CIDADE-DA-EDITORA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.nome_autor_publicacao = no.getAttribute(ATRIBUTOS[0])
        model.titulo_publicacao = no.getAttribute(ATRIBUTOS[1])
        model.issn_isbn = no.getAttribute(ATRIBUTOS[2])
        model.numero_edicao_revisao = no.getAttribute(ATRIBUTOS[3])
        model.volume = no.getAttribute(ATRIBUTOS[4])
        model.serie = no.getAttribute(ATRIBUTOS[5])
        model.fasciculo = no.getAttribute(ATRIBUTOS[6])
        model.editora_prefacio_posfacio = no.getAttribute(ATRIBUTOS[7])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[8])
        return model


class TraducaoParser(ProducaoBibliograficaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-TRADUCAO',
            'DETALHAMENTO-DA-TRADUCAO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Traducao()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'TIPO',
            'NATUREZA',
            'TITULO',
            'ANO',
            'PAIS-DE-PUBLICACAO',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[6])
        model.home_page = no.getAttribute(ATRIBUTOS[7])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[8]))
        model.doi = no.getAttribute(ATRIBUTOS[9])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'NOME-DO-AUTOR-TRADUZIDO',
            'TITULO-DA-OBRA-ORIGINAL',
            'ISSN-ISBN',
            'IDIOMA-DA-OBRA-ORIGINAL',
            'EDITORA-DA-TRADUCAO',
            'CIDADE-DA-EDITORA',
            'NUMERO-DE-PAGINAS',
            'NUMERO-DA-EDICAO-REVISAO',
            'VOLUME',
            'FASCICULO',
            'SERIE',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.nome_autor_traduzido = no.getAttribute(ATRIBUTOS[0])
        model.titulo_obra_original = no.getAttribute(ATRIBUTOS[1])
        model.issn_isbn = no.getAttribute(ATRIBUTOS[2])
        model.idioma_obra_original = no.getAttribute(ATRIBUTOS[3])
        model.editora_traducao = no.getAttribute(ATRIBUTOS[4])
        model.cidade_editora = no.getAttribute(ATRIBUTOS[5])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[6])
        model.numero_edicao_revisao = no.getAttribute(ATRIBUTOS[7])
        model.volume = no.getAttribute(ATRIBUTOS[8])
        model.fasciculo = no.getAttribute(ATRIBUTOS[9])
        model.serie = no.getAttribute(ATRIBUTOS[10])
        return model


class AutorParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.save()
        dono.autores.add(model)
        dono.save()

    def get_model(self, no):
        ATRIBUTOS = ['NOME-COMPLETO-DO-AUTOR', 'NOME-PARA-CITACAO', 'ORDEM-DE-AUTORIA', 'CPF']
        verificarAtributos(no, ATRIBUTOS)

        model = Autor()
        model.nome_completo = no.getAttribute(ATRIBUTOS[0])
        model.nome_citacao = no.getAttribute(ATRIBUTOS[1])
        model.ordem = no.getAttribute(ATRIBUTOS[2])
        model.cpf = no.getAttribute(ATRIBUTOS[3])
        return model


class InformacaoAdicionalParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        if model:
            model.save()
            dono.informacao_adicional = model
            dono.save()

    def get_model(self, no):
        ATRIBUTOS = ['DESCRICAO-INFORMACOES-ADICIONAIS']
        verificarAtributos(no, ATRIBUTOS)

        model = InformacaoAdicinal()
        model.descricao = no.getAttribute(ATRIBUTOS[0])
        if model.descricao:
            return model
        else:
            return None


##########################
#    PRODUCAO TECNICA    #
##########################
class ProducaoTecnicaParser:
    def get_filhos(self, no, model):
        model.save()
        for filho in no.getElementsByTagName('AUTORES'):
            parser = AutorParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
            parser = PalavraChaveParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
            parser = AreaConhecimentoParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
            parser = SetorAtividadeParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('INFORMACOES-ADICIONAIS'):
            parser = InformacaoAdicionalParser()
            parser.parse(filho, model)

    def parse(self, no, dono):
        FILHOS = [
            'SOFTWARE',
            'PRODUTO-TECNOLOGICO',
            'PROCESSOS-OU-TECNICAS',
            'TRABALHO-TECNICO',
            'DEMAIS-TIPOS-DE-PRODUCAO-TECNICA',
            'PATENTE',
            'MARCA',
            'DESENHO-INDUSTRIAL',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = SoftwareParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            parser = ProdutoTecnologicoParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            parser = ProcessoTecnicaParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            parser = TrabalhoTecnicoParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_demais_tipos_producao_tecnica(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[5]):
            parser = PatenteParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[6]):
            parser = MarcaParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[7]):
            parser = DesenhoIndustrialParser()
            parser.parse(filho, dono)

    def get_demais_tipos_producao_tecnica(self, no, dono):
        FILHOS = [
            'APRESENTACAO-DE-TRABALHO',
            'CARTA-MAPA-OU-SIMILAR',
            'CURSO-DE-CURTA-DURACAO-MINISTRADO',
            'DESENVOLVIMENTO-DE-MATERIAL-DIDATICO-OU-INSTRUCIONAL',
            'EDITORACAO',
            'MANUTENCAO-DE-OBRA-ARTISTICA',
            'MAQUETE',
            'ORGANIZACAO-DE-EVENTO',
            'OUTRA-PRODUCAO-TECNICA',
            'PROGRAMA-DE-RADIO-OU-TV',
            'RELATORIO-DE-PESQUISA',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = ApresentacaoTrabalhoParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            parser = CartaMapaSimilarParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            parser = CursoCurtaDuracaoMinistradoParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            parser = DesMatDidativoInstrucionalParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            parser = EditoracaoParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[5]):
            parser = ManutencaoObraArtisticaParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[6]):
            parser = MaqueteParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[7]):
            parser = OrganizacaoEventosParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[8]):
            parser = OutraProducaoTecnicaParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[9]):
            parser = ProgramaRadioTVParser()
            parser.parse(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[10]):
            parser = RelatorioPesquisaParser()
            parser.parse(filho, dono)


class SoftwareParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-SOFTWARE',
            'DETALHAMENTO-DO-SOFTWARE',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Software()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-SOFTWARE',
            'ANO',
            'PAIS',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'PLATAFORMA', 'AMBIENTE', 'DISPONIBILIDADE', 'INSTITUICAO-FINANCIADORA']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.plataforma = no.getAttribute(ATRIBUTOS[1])
        model.ambiente = no.getAttribute(ATRIBUTOS[2])
        model.disponibilidade = no.getAttribute(ATRIBUTOS[3])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[4])
        return model


class ProdutoTecnologicoParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-PRODUTO-TECNOLOGICO',
            'DETALHAMENTO-DO-PRODUTO-TECNOLOGICO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = ProdutoTecnologico()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'TIPO-PRODUTO',
            'NATUREZA',
            'TITULO-DO-PRODUTO',
            'ANO',
            'PAIS',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[6])
        model.home_page = no.getAttribute(ATRIBUTOS[7])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[8]))
        model.doi = no.getAttribute(ATRIBUTOS[9])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'DISPONIBILIDADE', 'CIDADE-DO-PRODUTO', 'INSTITUICAO-FINANCIADORA']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.disponibilidade = no.getAttribute(ATRIBUTOS[1])
        model.cidade_produto = no.getAttribute(ATRIBUTOS[2])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[3])
        return model


class ProcessoTecnicaParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-PROCESSOS-OU-TECNICAS',
            'DETALHAMENTO-DO-PROCESSOS-OU-TECNICAS',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = ProcessoTecnica()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-PROCESSO',
            'ANO',
            'PAIS',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'DISPONIBILIDADE', 'INSTITUICAO-FINANCIADORA', 'CIDADE-DO-PROCESSO']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.disponibilidade = no.getAttribute(ATRIBUTOS[1])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[2])
        model.cidade_processo = no.getAttribute(ATRIBUTOS[3])
        return model


class TrabalhoTecnicoParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-TRABALHO-TECNICO',
            'DETALHAMENTO-DO-TRABALHO-TECNICO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = TrabalhoTecnico()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO-DO-TRABALHO-TECNICO',
            'ANO',
            'PAIS',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'IDIOMA',
            'FLAG-RELEVANCIA',
            'DOI',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.idioma = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'DURACAO-EM-MESES', 'NUMERO-DE-PAGINAS', 'DISPONIBILIDADE', 'INSTITUICAO-FINANCIADORA', 'CIDADE-DO-PROCESSO']
        verificarAtributos(no, ATRIBUTOS)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.duracao_meses = no.getAttribute(ATRIBUTOS[1])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[2])
        model.disponibilidade = no.getAttribute(ATRIBUTOS[3])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[4])
        model.cidade_trabalho = no.getAttribute(ATRIBUTOS[5])
        return model


class PatenteParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PATENTE',
            'DETALHAMENTO-DA-PATENTE',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Patente()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TITULO', 'ANO-DESENVOLVIMENTO', 'PAIS', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE', 'FLAG-RELEVANCIA', 'FLAG-POTENCIAL-INOVACAO']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo = no.getAttribute(ATRIBUTOS[0])
        model.ano = no.getAttribute(ATRIBUTOS[1])
        model.pais = no.getAttribute(ATRIBUTOS[2])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[3])
        model.home_page = no.getAttribute(ATRIBUTOS[4])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        model.flag_potencial_inovacao = no.getAttribute(ATRIBUTOS[6])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'INSTITUICAO-FINANCIADORA', 'PLATAFORMA']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[1])
        model.categoria = no.getAttribute(ATRIBUTOS[2])
        return model


class MarcaParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-MARCA',
            'DETALHAMENTO-DA-MARCA',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Marca()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TITULO', 'ANO-DESENVOLVIMENTO', 'PAIS', 'FLAG-RELEVANCIA', 'FLAG-POTENCIAL-INOVACAO']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo = no.getAttribute(ATRIBUTOS[0])
        model.ano = no.getAttribute(ATRIBUTOS[1])
        model.pais = no.getAttribute(ATRIBUTOS[2])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[3]))
        model.flag_potencial_inovacao = no.getAttribute(ATRIBUTOS[4])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'NATUREZA']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        return model


class DesenhoIndustrialParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-DESENHO-INDUSTRIAL',
            'DETALHAMENTO-DO-DESENHO-INDUSTRIAL',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = DesenhoIndustrial()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TITULO', 'ANO-DESENVOLVIMENTO', 'PAIS', 'FLAG-RELEVANCIA', 'FLAG-POTENCIAL-INOVACAO']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo = no.getAttribute(ATRIBUTOS[0])
        model.ano = no.getAttribute(ATRIBUTOS[1])
        model.pais = no.getAttribute(ATRIBUTOS[2])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[3]))
        model.flag_potencial_inovacao = no.getAttribute(ATRIBUTOS[4])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'INSTITUICAO-FINANCIADORA']
        FILHOS = ['REGISTRO-OU-PATENTE']
        verificar(no, ATRIBUTOS, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            parser = RegistroPatenteParser()
            parser.parse(filho, model)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[1])
        return model


class ApresentacaoTrabalhoParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-APRESENTACAO-DE-TRABALHO',
            'DETALHAMENTO-DA-APRESENTACAO-DE-TRABALHO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = ApresentacaoTrabalho()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        model.doi = no.getAttribute(ATRIBUTOS[6])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NOME-DO-EVENTO', 'INSTITUICAO-PROMOTORA', 'LOCAL-DA-APRESENTACAO', 'CIDADE-DA-APRESENTACAO']
        verificarAtributos(no, ATRIBUTOS)

        model.nome_evento = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_promotora = no.getAttribute(ATRIBUTOS[1])
        model.local_apresentacao = no.getAttribute(ATRIBUTOS[2])
        model.cidade_apresentacao = no.getAttribute(ATRIBUTOS[3])
        return model


class CartaMapaSimilarParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-CARTA-MAPA-OU-SIMILAR',
            'DETALHAMENTO-DE-CARTA-MAPA-OU-SIMILAR',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = CartaMapaSimilar()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['TEMA-DA-CARTA-MAPA-OU-SIMILAR', 'TECNICA-UTILIZADA', 'FINALIDADE', 'AREA-REPRESENTADA', 'INSTITUICAO-FINANCIADORA']
        verificarAtributos(no, ATRIBUTOS)

        model.tema = no.getAttribute(ATRIBUTOS[0])
        model.tecnica_utilizada = no.getAttribute(ATRIBUTOS[1])
        model.finalidade = no.getAttribute(ATRIBUTOS[2])
        model.area_representada = no.getAttribute(ATRIBUTOS[3])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[4])
        return model


class CursoCurtaDuracaoMinistradoParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-CURSOS-CURTA-DURACAO-MINISTRADO',
            'DETALHAMENTO-DE-CURSOS-CURTA-DURACAO-MINISTRADO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = CursoCurtaDuracaoMinistrado()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NIVEL-DO-CURSO', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.nivel_curso = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['PARTICIPACAO-DOS-AUTORES', 'INSTITUICAO-PROMOTORA-DO-CURSO', 'LOCAL-DO-CURSO', 'CIDADE', 'DURACAO', 'UNIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.participacao_autores = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_promotora_curso = no.getAttribute(ATRIBUTOS[1])
        model.local_curso = no.getAttribute(ATRIBUTOS[2])
        model.cidade = no.getAttribute(ATRIBUTOS[3])
        model.duracao = no.getAttribute(ATRIBUTOS[4])
        model.unidade = no.getAttribute(ATRIBUTOS[5])
        return model


"""
#Desenvolvimento de Material Didativo Instrucional
"""


class DesMatDidativoInstrucionalParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-MATERIAL-DIDATICO-OU-INSTRUCIONAL',
            'DETALHAMENTO-DO-MATERIAL-DIDATICO-OU-INSTRUCIONAL',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = DesMatDidativoInstrucional()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        return model


class EditoracaoParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-EDITORACAO',
            'DETALHAMENTO-DE-EDITORACAO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Editoracao()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NUMERO-DE-PAGINAS', 'INSTITUICAO-PROMOTORA', 'EDITORA', 'CIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.numero_paginas = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_promotora = no.getAttribute(ATRIBUTOS[1])
        model.editora = no.getAttribute(ATRIBUTOS[2])
        model.cidade = no.getAttribute(ATRIBUTOS[3])
        return model


class ManutencaoObraArtisticaParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-MANUTENCAO-DE-OBRA-ARTISTICA',
            'DETALHAMENTO-DE-MANUTENCAO-DE-OBRA-ARTISTICA',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = ManutencaoObraArtistica()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TIPO', 'NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[6]))
        model.doi = no.getAttribute(ATRIBUTOS[7])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NOME-DA-OBRA', 'AUTOR-DA-OBRA', 'ANO-DA-OBRA', 'ACERVO', 'LOCAL', 'CIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.nome_obra = no.getAttribute(ATRIBUTOS[0])
        model.autor_obra = no.getAttribute(ATRIBUTOS[1])
        model.ano_obra = no.getAttribute(ATRIBUTOS[2])
        model.arcevo = no.getAttribute(ATRIBUTOS[3])
        model.local = no.getAttribute(ATRIBUTOS[4])
        model.cidade = no.getAttribute(ATRIBUTOS[5])
        return model


class MaqueteParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-MAQUETE',
            'DETALHAMENTO-DA-MAQUETE',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = Maquete()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo = no.getAttribute(ATRIBUTOS[0])
        model.ano = no.getAttribute(ATRIBUTOS[1])
        model.pais = no.getAttribute(ATRIBUTOS[2])
        model.idioma = no.getAttribute(ATRIBUTOS[3])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[6]))
        model.doi = no.getAttribute(ATRIBUTOS[7])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'OBJETO-REPRESENTADO', 'MATERIAL-UTILIZADO', 'INSTITUICAO-FINANCIADORA']
        verificarAtributos(no, ATRIBUTOS)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.objetivo_representador = no.getAttribute(ATRIBUTOS[1])
        model.material_utilizado = no.getAttribute(ATRIBUTOS[2])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[3])
        return model


class OrganizacaoEventosParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORGANIZACAO-DE-EVENTO',
            'DETALHAMENTO-DA-ORGANIZACAO-DE-EVENTO',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = OrganizacaoEventos()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TIPO', 'NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.natureza = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.ano = no.getAttribute(ATRIBUTOS[3])
        model.pais = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[6])
        model.home_page = no.getAttribute(ATRIBUTOS[7])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[8]))
        model.doi = no.getAttribute(ATRIBUTOS[9])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['INSTITUICAO-PROMOTORA', 'DURACAO-EM-SEMANAS', 'FLAG-EVENTO-ITINERANTE', 'FLAG-CATALOGO', 'LOCAL', 'CIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.instituicao_promotora = no.getAttribute(ATRIBUTOS[0])
        model.duracao_semanas = no.getAttribute(ATRIBUTOS[1])
        model.flag_evento_itinerante = parse_boolean(no.getAttribute(ATRIBUTOS[2]))
        model.flag_catalogo = no.getAttribute(ATRIBUTOS[3])
        model.local = no.getAttribute(ATRIBUTOS[4])
        model.cidade = no.getAttribute(ATRIBUTOS[5])
        return model


class OutraProducaoTecnicaParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRA-PRODUCAO-TECNICA',
            'DETALHAMENTO-DE-OUTRA-PRODUCAO-TECNICA',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = OutraProducaoTecnica()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'MEIO-DE-DIVULGACAO', 'IDIOMA', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[4])
        model.idioma = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[7]))
        model.doi = no.getAttribute(ATRIBUTOS[8])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['FINALIDADE', 'INSTITUICAO-PROMOTORA', 'LOCAL', 'CIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.finalidade = no.getAttribute(ATRIBUTOS[0])
        model.instituicao_promotora = no.getAttribute(ATRIBUTOS[1])
        model.local = no.getAttribute(ATRIBUTOS[2])
        model.cidade = no.getAttribute(ATRIBUTOS[3])
        return model


class ProgramaRadioTVParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-PROGRAMA-DE-RADIO-OU-TV',
            'DETALHAMENTO-DO-PROGRAMA-DE-RADIO-OU-TV',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = ProgramaRadioTV()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        model.doi = no.getAttribute(ATRIBUTOS[6])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['EMISSORA', 'TEMA', 'DATA-DA-APRESENTACAO', 'DURACAO-EM-MINUTOS', 'CIDADE']
        verificarAtributos(no, ATRIBUTOS)

        model.emissora = no.getAttribute(ATRIBUTOS[0])
        model.tema = no.getAttribute(ATRIBUTOS[1])
        model.data_apresentacao = parse_date(no.getAttribute(ATRIBUTOS[2]))
        model.duracao_minutos = no.getAttribute(ATRIBUTOS[3])
        model.cidade = no.getAttribute(ATRIBUTOS[4])
        return model


class RelatorioPesquisaParser(ProducaoTecnicaParser):
    def parse(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DO-RELATORIO-DE-PESQUISA',
            'DETALHAMENTO-DO-RELATORIO-DE-PESQUISA',
            'AUTORES',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()

    def get_model(self, no, dono):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = RelatorioPesquisa()
        model.curriculo = dono
        model.tipo_pub = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['TITULO', 'ANO', 'PAIS', 'IDIOMA', 'MEIO-DE-DIVULGACAO', 'HOME-PAGE-DO-TRABALHO', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.titulo = no.getAttribute(ATRIBUTOS[0])
        model.ano = no.getAttribute(ATRIBUTOS[1])
        model.pais = no.getAttribute(ATRIBUTOS[2])
        model.idioma = no.getAttribute(ATRIBUTOS[3])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[6]))
        model.doi = no.getAttribute(ATRIBUTOS[7])
        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NOME-DO-PROJETO', 'NUMERO-DE-PAGINAS', 'DISPONIBILIDADE', 'INSTITUICAO-FINANCIADORA']
        verificarAtributos(no, ATRIBUTOS)

        model.nome_projeto = no.getAttribute(ATRIBUTOS[0])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[1])
        model.disponibilidade = no.getAttribute(ATRIBUTOS[2])
        model.instituicao_financiadora = no.getAttribute(ATRIBUTOS[3])
        return model


class RegistroPatenteParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.curriculo = dono.curriculo
        model.save()
        dono.registros_patentes.add(model)
        dono.save()

    def get_model(self, no):
        ATRIBUTOS = [
            'TIPO-PATENTE',
            'CODIGO-DO-REGISTRO-OU-PATENTE',
            'TITULO-PATENTE',
            'DATA-PEDIDO-DE-DEPOSITO',
            'DATA-DE-PEDIDO-DE-EXAME',
            'DATA-DE-CONCESSAO',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = RegistroPatente()
        model.tipo = no.getAttribute(ATRIBUTOS[0])
        model.codigo = no.getAttribute(ATRIBUTOS[1])
        model.titulo = no.getAttribute(ATRIBUTOS[2])
        model.data_pedido_deposito = parse_date(no.getAttribute(ATRIBUTOS[3]))
        model.data_pedido_exame = parse_date(no.getAttribute(ATRIBUTOS[4]))
        model.data_concessao = parse_date(no.getAttribute(ATRIBUTOS[5]))
        return model


######################################
#    OUTRA PRODUCAO BIBLIOGRAFICA    #
######################################
class OutraProducaoParser:
    def get_filhos(self, no, model):
        model.save()
        for filho in no.getElementsByTagName('AUTORES'):
            parser = AutorParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
            parser = PalavraChaveParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
            parser = AreaConhecimentoParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
            parser = SetorAtividadeParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('INFORMACOES-ADICIONAIS'):
            parser = InformacaoAdicionalParser()
            parser.parse(filho, model)

    def parse(self, no, dono):
        FILHOS = ['PRODUCAO-ARTISTICA-CULTURAL', 'ORIENTACOES-CONCLUIDAS', 'DEMAIS-TRABALHOS']
        verificarFilhos(no, FILHOS)

        #        for filho in no.getElementsByTagName(FILHOS[0]):
        #            parser = ProducaoArtisticaCulturalParser()
        #            parser.parse(filho, dono)
        for filho in no.getElementsByTagName(FILHOS[1]):
            parser = OrientacaoConcluidaParser()
            parser.parse(filho, dono)


# for filho in no.getElementsByTagName(FILHOS[2]):
#            parser = OutroTrabalhoParser()
#            parser.parse(filho, dono)


class OrientacaoConcluidaParser(OutraProducaoParser):
    def parse(self, no, dono):
        FILHOS = [
            'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO',
            'ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO',
            'ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO',
            'OUTRAS-ORIENTACOES-CONCLUIDAS',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_orientacoes_mestrado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_orientacoes_doutorado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_orientacoes_posdoutorado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_outras_orientacoes(filho, dono)

    def get_orientacoes_mestrado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-ORIENTACOES-CONCLUIDAS-PARA-MESTRADO',
            'DETALHAMENTO-DE-ORIENTACOES-CONCLUIDAS-PARA-MESTRADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_doutorado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO',
            'DETALHAMENTO-DE-ORIENTACOES-CONCLUIDAS-PARA-DOUTORADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_posdoutorado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO',
            'DETALHAMENTO-DE-ORIENTACOES-CONCLUIDAS-PARA-POS-DOUTORADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_outras_orientacoes(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS',
            'DETALHAMENTO-DE-OUTRAS-ORIENTACOES-CONCLUIDAS',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_model(self, no, dono, FILHOS):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = OrientacaoConcluida()
        model.curriculo = dono
        model.tipo = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'HOME-PAGE', 'FLAG-RELEVANCIA', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        if model.tipo == 'OUTRAS-ORIENTACOES-CONCLUIDAS':
            model.natureza = model.tipo
            model.tipo = no.getAttribute(ATRIBUTOS[0])
        else:
            model.natureza = no.getAttribute(ATRIBUTOS[0])

        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.flag_relevancia = parse_boolean(no.getAttribute(ATRIBUTOS[6]))
        model.doi = no.getAttribute(ATRIBUTOS[7])
        if no.tagName == 'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO':
            model.tipo_mestrado = no.getAttribute('TIPO')

        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = [
            'TIPO-DE-ORIENTACAO',
            'NOME-DO-ORIENTADO',
            'NOME-DA-INSTITUICAO',
            'NOME-ORGAO',
            'NOME-DO-CURSO',
            'FLAG-BOLSA',
            'NOME-DA-AGENCIA',
            'NUMERO-DE-PAGINAS',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.tipo_orientacao = no.getAttribute(ATRIBUTOS[0])
        model.nome_orientando = no.getAttribute(ATRIBUTOS[1])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[3])
        model.nome_curso = no.getAttribute(ATRIBUTOS[4])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[6])
        model.numero_paginas = no.getAttribute(ATRIBUTOS[7])
        return model


##############################
#    DADOS COMPLEMENTARES    #
##############################
class DadoComplementarParser:
    def parse(self, no, dono):
        FILHOS = [
            'FORMACAO-COMPLEMENTAR',
            'PARTICIPACAO-EM-BANCA-TRABALHOS-CONCLUSAO',
            'PARTICIPACAO-EM-BANCA-JULGADORA',
            'PARTICIPACAO-EM-EVENTOS-CONGRESSOS',
            'ORIENTACOES-EM-ANDAMENTO',
            'INFORMACOES-ADICIONAIS-INSTITUICOES',
            'INFORMACOES-ADICIONAIS-CURSOS',
        ]
        verificarFilhos(no, FILHOS)

        model = self.get_model(no, dono)

        model.save()

        #        for filho in no.getElementsByTagName(FILHOS[0]):
        #            parser = FormacaoComplementarParser()
        #            parser.parse(filho, dono)
        for filho in no.getElementsByTagName(FILHOS[1]):
            parser = ParticipacaoBancaTrabalhoConclusaoParser()
            parser.parse(filho, model)

        for filho in no.getElementsByTagName(FILHOS[2]):
            parser = ParticipacaoBancaJulgadoraParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName(FILHOS[3]):
            parser = ParticipacaoEventoCongressoParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName(FILHOS[4]):
            parser = OrientacaoAndamentoParser()
            parser.parse(filho, model)
        #        for filho in no.getElementsByTagName(FILHOS[5]):
        #            parser = InformacaoAdicionalInstituicaoParser()
        #            parser.parse(filho, dono)
        #        for filho in no.getElementsByTagName(FILHOS[6]):
        #            parser = InformacaoAdicionalCursoParser()
        #            parser.parse(filho, dono)
        model.save()

        return model

    def get_model(self, no, dono):
        try:
            model = dono.dado_complementar
        except Exception:
            model = None
        if not model:
            model = DadoComplementar()

        return model


class ParticipanteBancaParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.save()
        dono.participantes.add(model)
        dono.save()

    def get_model(self, no):
        ATRIBUTOS = [
            'NOME-COMPLETO-DO-PARTICIPANTE-DA-BANCA',
            'NOME-PARA-CITACAO-DO-PARTICIPANTE-DA-BANCA',
            'ORDEM-PARTICIPANTE',
            'CPF-DO-PARTICIPANTE-DA-BANCA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = ParticipanteBanca()
        model.nome_completo = no.getAttribute(ATRIBUTOS[0])
        model.nome_citacao = no.getAttribute(ATRIBUTOS[1])
        model.ordem = no.getAttribute(ATRIBUTOS[2])
        model.cpf = no.getAttribute(ATRIBUTOS[3])
        return model


class ParticipacaoBancaParse:
    model_class = None

    def get_model(self, no, dono, FILHOS):
        if self.model_class is None:
            raise RuntimeError('model_class can not be None.')
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = self.model_class()
        model.dado_complementar = dono
        model.tipo = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()
        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)

        self.get_filhos(no, model)
        model.save()
        return model

    def popula_model(self, no, dono, FILHOS):
        verificarFilhos(no, FILHOS)
        return self.get_model(no, dono, FILHOS)

    def get_filhos(self, no, model):
        model.save()
        for filho in no.getElementsByTagName('PARTICIPANTE-BANCA'):
            parser = ParticipanteBancaParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
            parser = PalavraChaveParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
            parser = AreaConhecimentoParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
            parser = SetorAtividadeParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('INFORMACOES-ADICIONAIS'):
            parser = InformacaoAdicionalParser()
            parser.parse(filho, model)

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO', 'ANO', 'PAIS', 'IDIOMA', 'HOME-PAGE', 'DOI', 'TITULO-INGLES']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.doi = no.getAttribute(ATRIBUTOS[6])
        model.titulo_ingles = no.getAttribute(ATRIBUTOS[7])
        return model


class ParticipacaoBancaTrabalhoConclusaoParser(ParticipacaoBancaParse):
    model_class = ParticipacaoBancaTrabalhoConclusao

    def parse(self, no, dono):
        FILHOS = [
            'PARTICIPACAO-EM-BANCA-DE-MESTRADO',
            'PARTICIPACAO-EM-BANCA-DE-DOUTORADO',
            'PARTICIPACAO-EM-BANCA-DE-EXAME-QUALIFICACAO',
            'PARTICIPACAO-EM-BANCA-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'PARTICIPACAO-EM-BANCA-DE-GRADUACAO',
            'OUTRAS-PARTICIPACOES-EM-BANCA',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_participacoes_mestrado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_participacoes_doutorado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_participacoes_exame_qualificacao(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_participacoes_aperfeicoamento_especializacao(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_participacoes_graduacao(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[5]):
            self.get_outras_participacoes(filho, dono)

    def get_participacoes_mestrado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTICIPACAO-EM-BANCA-DE-MESTRADO',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-BANCA-DE-MESTRADO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        model = self.popula_model(no, dono, FILHOS)
        model.tipo_mestrado = no.getAttribute('TIPO')

    def get_participacoes_doutorado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTICIPACAO-EM-BANCA-DE-DOUTORADO',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-BANCA-DE-DOUTORADO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_participacoes_exame_qualificacao(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTICIPACAO-EM-BANCA-DE-EXAME-QUALIFICACAO',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-BANCA-DE-EXAME-QUALIFICACAO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_participacoes_aperfeicoamento_especializacao(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTICIPACAO-EM-BANCA-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-BANCA-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_participacoes_graduacao(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-PARTICIPACAO-EM-BANCA-DE-GRADUACAO',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-BANCA-DE-GRADUACAO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_outras_participacoes(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRAS-PARTICIPACOES-EM-BANCA',
            'DETALHAMENTO-DE-OUTRAS-PARTICIPACOES-EM-BANCA',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NOME-DO-CANDIDATO', 'NOME-INSTITUICAO', 'NOME-ORGAO', 'NOME-CURSO', 'NOME-CURSO-INGLES']
        verificarAtributos(no, ATRIBUTOS)

        model.nome_candidato = no.getAttribute(ATRIBUTOS[0])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[1])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[2])
        model.nome_curso = no.getAttribute(ATRIBUTOS[3])
        model.nome_curso_ingles = no.getAttribute(ATRIBUTOS[4])
        return model


class ParticipacaoBancaJulgadoraParser(ParticipacaoBancaParse):
    model_class = ParticipacaoBancaJulgadora

    def parse(self, no, dono):
        FILHOS = [
            'BANCA-JULGADORA-PARA-PROFESSOR-TITULAR',
            'BANCA-JULGADORA-PARA-CONCURSO-PUBLICO',
            'BANCA-JULGADORA-PARA-LIVRE-DOCENCIA',
            'BANCA-JULGADORA-PARA-AVALIACAO-CURSOS',
            'OUTRAS-BANCAS-JULGADORAS',
        ]
        verificarFilhos(no, FILHOS)
        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_banca_julgadora_para_professor_titular(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_banca_julgadora_para_concurso_publico(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_banca_julgadora_para_livre_docencia(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_banca_julgadora_para_avaliacao_cursos(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_outras_bancas_julgadoras(filho, dono)

    def get_banca_julgadora_para_professor_titular(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-BANCA-JULGADORA-PARA-PROFESSOR-TITULAR',
            'DETALHAMENTO-DA-BANCA-JULGADORA-PARA-PROFESSOR-TITULAR',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_banca_julgadora_para_concurso_publico(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-BANCA-JULGADORA-PARA-CONCURSO-PUBLICO',
            'DETALHAMENTO-DA-BANCA-JULGADORA-PARA-CONCURSO-PUBLICO',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_banca_julgadora_para_livre_docencia(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-BANCA-JULGADORA-PARA-LIVRE-DOCENCIA',
            'DETALHAMENTO-DA-BANCA-JULGADORA-PARA-LIVRE-DOCENCIA',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_banca_julgadora_para_avaliacao_cursos(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-BANCA-JULGADORA-PARA-AVALIACAO-CURSOS',
            'DETALHAMENTO-DA-BANCA-JULGADORA-PARA-AVALIACAO-CURSOS',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_outras_bancas_julgadoras(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRAS-BANCAS-JULGADORAS',
            'DETALHAMENTO-DE-OUTRAS-BANCAS-JULGADORAS',
            'PARTICIPANTE-BANCA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        self.popula_model(no, dono, FILHOS)

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['CODIGO-INSTITUICAO', 'NOME-INSTITUICAO']
        verificarAtributos(no, ATRIBUTOS)

        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[0])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[1])
        return model


class ParticipanteEventoCongressoParser:
    def parse(self, no, dono):
        model = self.get_model(no)
        model.save()
        dono.participantes.add(model)
        dono.save()

    def get_model(self, no):
        ATRIBUTOS = [
            'NOME-COMPLETO-DO-PARTICIPANTE-DE-EVENTOS-CONGRESSOS',
            'NOME-PARA-CITACAO-DO-PARTICIPANTE-DE-EVENTOS-CONGRESSOS',
            'ORDEM-PARTICIPANTE',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model = ParticipanteEventoCongresso()
        model.nome_completo = no.getAttribute(ATRIBUTOS[0])
        model.nome_citacao = no.getAttribute(ATRIBUTOS[1])
        model.ordem = no.getAttribute(ATRIBUTOS[2])
        return model


class ParticipacaoEventoCongressoParser:
    def get_filhos(self, no, model):
        model.save()

        for filho in no.getElementsByTagName('PARTICIPANTE-DE-EVENTOS-CONGRESSOS'):
            parser = ParticipanteEventoCongressoParser()
            parser.parse(filho, model)

    def parse(self, no, dono):
        FILHOS = [
            'PARTICIPACAO-EM-CONGRESSO',
            'PARTICIPACAO-EM-SEMINARIO',
            'PARTICIPACAO-EM-OFICINA',
            'PARTICIPACAO-EM-ENCONTRO',
            'OUTRAS-PARTICIPACOES-EM-EVENTOS-CONGRESSOS',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_participacao_congresso(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_participacao_seminario(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_participacao_oficina(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_participacao_encontro(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_participacao_outros_eventos(filho, dono)

    def get_participacao_congresso(self, no, dono):
        FILHOS = ['DADOS-BASICOS-DA-PARTICIPACAO-EM-CONGRESSO', 'DETALHAMENTO-DA-PARTICIPACAO-EM-CONGRESSO', 'PARTICIPANTE-DE-EVENTOS-CONGRESSOS']
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_participacao_seminario(self, no, dono):
        FILHOS = ['DADOS-BASICOS-DA-PARTICIPACAO-EM-SEMINARIO', 'DETALHAMENTO-DA-PARTICIPACAO-EM-SEMINARIO', 'PARTICIPANTE-DE-EVENTOS-CONGRESSOS']
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_participacao_oficina(self, no, dono):
        FILHOS = ['DADOS-BASICOS-DA-PARTICIPACAO-EM-OFICINA', 'DETALHAMENTO-DA-PARTICIPACAO-EM-OFICINA', 'PARTICIPANTE-DE-EVENTOS-CONGRESSOS']
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_participacao_encontro(self, no, dono):
        FILHOS = ['DADOS-BASICOS-DA-PARTICIPACAO-EM-ENCONTRO', 'DETALHAMENTO-DA-PARTICIPACAO-EM-ENCONTRO', 'PARTICIPANTE-DE-EVENTOS-CONGRESSOS']
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_participacao_outros_eventos(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRAS-PARTICIPACOES-EM-EVENTOS-CONGRESSOS',
            'DETALHAMENTO-DA-PARTICIPACAO-EM-CONGRESSO',
            'PARTICIPANTE-DE-EVENTOS-CONGRESSOS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_model(self, no, dono, FILHOS):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)
        model = ParticipacaoEventoCongresso()
        model.dado_complementar = dono
        model.tipo = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = [
            'NATUREZA',
            'TITULO',
            'ANO',
            'PAIS',
            'IDIOMA',
            'MEIO-DE-DIVULGACAO',
            'HOME-PAGE-DO-TRABALHO',
            'FLAG-RELEVANCIA',
            'TIPO-PARTICIPACAO',
            'FORMA-PARTICIPACAO',
            'DOI',
            'TITULO-INGLES',
            'FLAG-DIVULGACAO-CIENTIFICA',
        ]
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.meio_divulgacao = no.getAttribute(ATRIBUTOS[5])
        model.home_page = no.getAttribute(ATRIBUTOS[6])
        model.flag_relevancia = no.getAttribute(ATRIBUTOS[7])
        model.tipo_participacao = no.getAttribute(ATRIBUTOS[8])
        model.forma_participacao = no.getAttribute(ATRIBUTOS[9])
        model.doi = no.getAttribute(ATRIBUTOS[10])
        model.titulo_ingles = no.getAttribute(ATRIBUTOS[11])
        model.flag_divulgacao_cientifica = no.getAttribute(ATRIBUTOS[12])

        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['NOME-DO-EVENTO', 'CODIGO-INSTITUICAO', 'NOME-INSTITUICAO', 'LOCAL-DO-EVENTO', 'CIDADE-DO-EVENTO', 'NOME-DO-EVENTO-INGLES']
        verificarAtributos(no, ATRIBUTOS)

        model.nome_evento = no.getAttribute(ATRIBUTOS[0])
        model.codigo_instituicao = no.getAttribute(ATRIBUTOS[1])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.local_evento = no.getAttribute(ATRIBUTOS[3])
        model.cidade_evento = no.getAttribute(ATRIBUTOS[4])
        model.nome_evento_ingles = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        return model


class OrientacaoAndamentoParser:
    def get_filhos(self, no, model):
        model.save()
        for filho in no.getElementsByTagName('AUTORES'):
            parser = AutorParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('PALAVRAS-CHAVE'):
            parser = PalavraChaveParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('AREAS-DO-CONHECIMENTO'):
            parser = AreaConhecimentoParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('SETORES-DE-ATIVIDADE'):
            parser = SetorAtividadeParser()
            parser.parse(filho, model)
        for filho in no.getElementsByTagName('INFORMACOES-ADICIONAIS'):
            parser = InformacaoAdicionalParser()
            parser.parse(filho, model)

    def parse(self, no, dono):
        FILHOS = [
            'ORIENTACAO-EM-ANDAMENTO-DE-MESTRADO',
            'ORIENTACAO-EM-ANDAMENTO-DE-DOUTORADO',
            'ORIENTACAO-EM-ANDAMENTO-DE-POS-DOUTORADO',
            'ORIENTACAO-EM-ANDAMENTO-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO',
            'ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA',
            'OUTRAS-ORIENTACOES-EM-ANDAMENTO',
        ]
        verificarFilhos(no, FILHOS)

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_orientacoes_mestrado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_orientacoes_doutorado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[2]):
            self.get_orientacoes_posdoutorado(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[3]):
            self.get_orientacoes_aperfeicoamento_especializacao(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[4]):
            self.get_orientacoes_graduacao(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[5]):
            self.get_orientacoes_iniciacao_cientifica(filho, dono)

        for filho in no.getElementsByTagName(FILHOS[6]):
            self.get_outras_orientacoes(filho, dono)

    def get_orientacoes_mestrado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-MESTRADO',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-MESTRADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_doutorado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-DOUTORADO',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-DOUTORADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_posdoutorado(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-POS-DOUTORADO',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-POS-DOUTORADO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_aperfeicoamento_especializacao(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-APERFEICOAMENTO-ESPECIALIZACAO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_graduacao(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-GRADUACAO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_orientacoes_iniciacao_cientifica(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DA-ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA',
            'DETALHAMENTO-DA-ORIENTACAO-EM-ANDAMENTO-DE-INICIACAO-CIENTIFICA',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_outras_orientacoes(self, no, dono):
        FILHOS = [
            'DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-EM-ANDAMENTO',
            'DETALHAMENTO-DE-OUTRAS-ORIENTACOES-EM-ANDAMENTO',
            'PALAVRAS-CHAVE',
            'AREAS-DO-CONHECIMENTO',
            'SETORES-DE-ATIVIDADE',
            'INFORMACOES-ADICIONAIS',
        ]
        verificarFilhos(no, FILHOS)

        self.get_model(no, dono, FILHOS)

    def get_model(self, no, dono, FILHOS):
        ATRIBUTOS = ['SEQUENCIA-PRODUCAO']
        verificarAtributos(no, ATRIBUTOS)

        model = OrientacaoAndamento()
        model.dado_complementar = dono
        model.tipo = no.tagName
        model.sequencia = no.getAttribute(ATRIBUTOS[0])

        for filho in no.getElementsByTagName(FILHOS[0]):
            self.get_dados_basicos(filho, model)

        model.save()

        for filho in no.getElementsByTagName(FILHOS[1]):
            self.get_detalhamento(filho, model)
        self.get_filhos(no, model)
        model.save()
        return model

    def get_dados_basicos(self, no, model):
        ATRIBUTOS = ['NATUREZA', 'TITULO-DO-TRABALHO', 'ANO', 'PAIS', 'IDIOMA', 'HOME-PAGE', 'DOI']
        verificarAtributos(no, ATRIBUTOS)

        model.natureza = no.getAttribute(ATRIBUTOS[0])
        model.titulo = no.getAttribute(ATRIBUTOS[1])
        model.ano = no.getAttribute(ATRIBUTOS[2])
        model.pais = no.getAttribute(ATRIBUTOS[3])
        model.idioma = no.getAttribute(ATRIBUTOS[4])
        model.home_page = no.getAttribute(ATRIBUTOS[5])
        model.doi = no.getAttribute(ATRIBUTOS[6])
        if no.tagName == 'ORIENTACOES-CONCLUIDAS-PARA-MESTRADO':
            model.tipo_mestrado = no.getAttribute('TIPO')

        return model

    def get_detalhamento(self, no, model):
        ATRIBUTOS = ['TIPO-DE-ORIENTACAO', 'NOME-DO-ORIENTANDO', 'NOME-INSTITUICAO', 'NOME-ORGAO', 'NOME-CURSO', 'FLAG-BOLSA', 'NOME-DA-AGENCIA']
        verificarAtributos(no, ATRIBUTOS)

        model.tipo_orientacao = no.getAttribute(ATRIBUTOS[0])
        model.nome_orientando = no.getAttribute(ATRIBUTOS[1])
        model.nome_instituicao = no.getAttribute(ATRIBUTOS[2])
        model.nome_orgao = no.getAttribute(ATRIBUTOS[3])
        model.nome_curso = no.getAttribute(ATRIBUTOS[4])
        model.flag_bolsa = parse_boolean(no.getAttribute(ATRIBUTOS[5]))
        model.nome_agencia_financiadora = no.getAttribute(ATRIBUTOS[6])
        return model


def parse_datetime(dateStr, timeStr):
    if dateStr:
        return datetime.strptime(dateStr + timeStr, '%d%m%Y%H%M%S')
    return None


def parse_date(dateStr):
    if dateStr:
        return datetime.strptime(dateStr, '%d%m%Y').date()
    return None


def parse_boolean(flag):
    if flag == 'NAO':
        return False
    elif flag == 'SIM':
        return True
    return None
