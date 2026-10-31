import csv
import decimal
import re
import sys
from datetime import datetime

from django.conf import settings
from sentry_sdk import capture_exception

from tesouro_gerencial.models import (
    GRU,
    RAP,
    AcaoGoverno,
    ClassificacaoInstitucional,
    ContaContabil,
    DocumentoBase,
    DocumentoEmpenho,
    DocumentoEmpenhoItem,
    DocumentoLiquidacao,
    DocumentoLiquidacaoItem,
    DocumentoPagamento,
    DocumentoPagamentoItem,
    EsferaOrcamentaria,
    EventoNotaDotacao,
    EventoNotaEmpenho,
    FonteRecurso,
    NaturezaDespesa,
    NotaCredito,
    NotaCreditoItem,
    NotaDotacao,
    NotaDotacaoItem,
    PlanoInterno,
    ProgramaTrabalhoResumido,
    RAPItem,
    ReceitaGRU,
    SubElementoNaturezaDespesa,
    UnidadeGestora,
)

"""
* Verificar a possibilidade de trabalhar melhor a criação dos PTRES
"""


class MyCache:
    def __init__(self):
        self._cache = {}

    def get_item(self, key, item):
        if key in self._cache and item in self._cache[key]:
            return self._cache[key][item]
        return None

    def add_item(self, key, item, obj):
        if key not in self._cache:
            self._cache[key] = {}
        self._cache[key][item] = obj


class Importador:
    LOG_PRINT = 1
    LOG_ARQUIVO = 0

    _cache = MyCache()

    def __init__(
        self, arquivos, encoding='ISO-8859-1', tipo_log=LOG_PRINT, log_level=1, log_nome_arquivo=f'{settings.BASE_DIR}/deploy/logs/siafi_log.txt'
    ):
        self.ini_row = 0
        self.ignore_last_row = False
        self.arquivos = arquivos
        self.encoding = encoding
        self.tipo_log = tipo_log
        self.log_level = log_level
        self.log_nome_arquivo = log_nome_arquivo
        self.ordenar = False

    def log(self, txt, tipo_log=-1):
        if tipo_log == -1:
            tipo_log = self.tipo_log
        self.stdout = open(self.log_nome_arquivo, 'a') if tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write(txt)

    def format_data(self, data):
        dia, mes, ano = data.split('/')
        return datetime(year=int(ano), month=int(mes), day=int(dia))

    def get_conta_contabil(self, codigo, nome):
        self.log(f'Obtendo Conta Contábil - {codigo}...\n')
        conta_contabil = self._cache.get_item('conta_contabil', codigo)
        if conta_contabil is None:
            conta_contabil, _ = ContaContabil.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('conta_contabil', codigo, conta_contabil)

        return conta_contabil

    def get_unidade_gestora(self, codigo, nome):
        self.log(f'Obtendo Unidade Gestora - {codigo}...\n')
        ug = self._cache.get_item('unidade_gestora', codigo)
        if ug is None:
            ug, _ = UnidadeGestora.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('unidade_gestora', codigo, ug)

        return ug

    def get_classificacao_institucional(self, codigo, nome):
        self.log(f'Obtendo Classificação Institucional - {codigo}...\n')
        ci = self._cache.get_item('classificacao_institucional', codigo)

        if ci is None:
            ci, _ = ClassificacaoInstitucional.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('classificacao_institucional', codigo, ci)

        return ci

    def get_esfera_orcamentaria(self, codigo, nome):
        self.log(f'Obtendo Esfera Orçamentária - {codigo}...\n')
        esfera_orcamentaria = self._cache.get_item('esfera_orcamentaria', codigo)
        if esfera_orcamentaria is None:
            esfera_orcamentaria, _ = EsferaOrcamentaria.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('esfera_orcamentaria', codigo, esfera_orcamentaria)

        return esfera_orcamentaria

    def get_ptres(self, codigo):
        self.log(f'Obtendo PTRES - {codigo}...\n')
        ptres = self._cache.get_item('ptres', codigo)
        if ptres is None:
            ptres, _ = ProgramaTrabalhoResumido.objects.get_or_create(codigo=codigo)
            self._cache.add_item('ptres', codigo, ptres)

        return ptres

    def get_fonte_recurso(self, codigo, nome):
        self.log(f'Obtendo Fonte de Recurso - {codigo}...\n')
        fonte = self._cache.get_item('fonte_recurso', codigo)
        if fonte is None:
            fonte, _ = FonteRecurso.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('fonte_recurso', codigo, fonte)

        return fonte

    def get_natureza_despesa(self, codigo, nome):
        self.log(f'Obtendo Naturesa de Despesa - {codigo}...\n')
        natureza_despesa = self._cache.get_item('natureza_despesa', codigo)
        if natureza_despesa is None:
            # TODO: ver como fazer, não tem informação sobre  categoria, grupo, modalidade e elemento de despesa
            natureza_despesa, _ = NaturezaDespesa.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('natureza_despesa', codigo, natureza_despesa)

        return natureza_despesa

    def get_subitem_natureza_despesa(self, natureza_despesa, codigo, nome):
        self.log(f'Obtendo Subitem - {codigo}...\n')
        sub_codigo = f'{natureza_despesa.codigo}{codigo}'
        subelemento = self._cache.get_item('subelemento', sub_codigo)
        if subelemento is None:
            subelemento, _ = SubElementoNaturezaDespesa.objects.get_or_create(
                codigo_subelemento=codigo, natureza_despesa=natureza_despesa, defaults={'nome': nome}
            )
            subelemento.save()
            self._cache.add_item('subelemento', sub_codigo, subelemento)

        return subelemento

    def get_plano_interno(self, codigo, nome, detalhamento=None):
        self.log(f'Obtendo Plano Interno - {codigo}...\n')
        plano = self._cache.get_item('plano_interno', codigo)
        if plano is None:
            plano, _ = PlanoInterno.objects.get_or_create(codigo=codigo, defaults={'nome': nome, 'detalhamento': detalhamento})
            self._cache.add_item('plano_interno', codigo, plano)

        return plano

    def get_acao_governo(self, codigo, nome):
        self.log(f'Obtendo Plano Interno - {codigo}...\n')
        acao_governo = self._cache.get_item('acao_governo', codigo)
        # TODO: ainda está faltando mais dados para isso ou criar um novo modelo
        if acao_governo is None:
            acao_governo, _ = AcaoGoverno.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('acao_governo', codigo, acao_governo)

        return acao_governo

    def get_gru(self, codigo, nome):
        self.log(f'Obtendo GRU - {codigo}...\n')
        gru = self._cache.get_item('unidade_gestora', codigo)
        if gru is None:
            gru, _ = GRU.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('unidade_gestora', codigo, gru)

        return gru

    def get_evento_nota_credito(self, codigo, nome):
        self.log(f'Obtendo Evento de Nota de Dotação - {codigo}...\n')
        evento_nota_credito = self._cache.get_item('evento_nota_credito', codigo)
        if evento_nota_credito is None:
            evento_nota_credito, _ = EventoNotaDotacao.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('evento_nota_credito', codigo, evento_nota_credito)

        return evento_nota_credito

    def get_evento_nota_empenho(self, codigo, nome):
        self.log(f'Obtendo Evento de Nota de Empenho - {codigo}...\n')
        evento_nota_empenho = self._cache.get_item('evento_nota_empenho', codigo)
        if evento_nota_empenho is None:
            evento_nota_empenho, _ = EventoNotaEmpenho.objects.get_or_create(codigo=codigo, defaults={'nome': nome})
            self._cache.add_item('evento_nota_empenho', codigo, evento_nota_empenho)

        return evento_nota_empenho

    def get_valor(self, parte_chave):
        texto = self.get_texto(parte_chave)
        if texto:
            return decimal.Decimal(texto.replace('.', '').replace(',', '.').replace('(', '-').replace(')', ''))

        # TODO: ver porque existe essas inconsistências
        return decimal.Decimal(0)

    def iterar(self, rows):
        for row in rows:
            self.processar(row)

    def montar_cabecalho(self, arquivo, delimiter='\t'):
        """
        Lê as linhas especificadas em self.cabecalho_linhas e monta o nome das colunas.
        Se o nome da coluna estiver vazio, herda o nome da coluna anterior.
        """
        if self.cabecalho_linhas is None:
            raise ValueError("Defina 'cabecalho_linhas' no importador.")
        with open(arquivo, encoding=self.encoding) as file:
            leitor = csv.reader(file, delimiter=delimiter)
            todas_linhas = list(leitor)
        colunas = [todas_linhas[i] for i in self.cabecalho_linhas]
        max_cols = max(len(col) for col in colunas)
        nomes_colunas = []
        for idx in range(max_cols):
            partes = []
            for col in colunas:
                if idx < len(col) and col[idx].strip():
                    partes.append(col[idx].replace('"', ''))
            nome = ' '.join(partes).strip()
            if not nome and idx > 0:
                # Herda o nome da coluna anterior se estiver vazio
                nome = f'{nomes_colunas[idx - 1]} Nome'
            nomes_colunas.append(nome)
        return nomes_colunas

    def mapear_colunas(self, nomes_colunas):
        """
        Cria um dicionário: nome_coluna -> índice
        """
        return {nome: idx for idx, nome in enumerate(nomes_colunas)}

    def set_row(self, row):
        self.row = row

    def get_indice(self, parte_chave):
        """
        Retorna o índice da coluna que contém a parte_chave.
        Se não encontrar, retorna None.
        """
        for chave, valor in self.colunas.items():
            if parte_chave == chave:
                return valor
        for chave, valor in self.colunas.items():
            if parte_chave in chave:
                return valor
        return None

    def get_texto(self, parte_chave, row=None):
        if row is None:
            row = self.row
        indice = self.get_indice(parte_chave)
        if indice is not None:
            return row[indice].strip() if row[indice] else None
        return None

    def run(self):
        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        conteudo_arquivos = []
        for arquivo in self.arquivos:
            try:
                nomes_colunas = self.montar_cabecalho(arquivo, delimiter=self.delimiter)
                self.colunas = self.mapear_colunas(nomes_colunas)
                with open(arquivo, encoding=self.encoding) as file:
                    rows = list(csv.reader(file, delimiter=self.delimiter))
                    nrows = len(rows)
                    if self.ignore_last_row:
                        nrows -= 1
                    rows = rows[self.ini_row : nrows]
                    if rows:
                        ordenar_por = rows[0][0]
                        if hasattr(self, 'ordenar_por'):
                            ordenar_por = rows[0][self.get_indice(self.ordenar_por)]
                        conteudo_arquivos.append([ordenar_por, rows])
                    # conteudo_arquivos.append([rows])
            except Exception as error:
                self.stdout.write('-' * 79)
                self.stdout.write('\n')
                self.stdout.write(f'Erro ao tentar ler o arquivo {arquivo} = {error}')
                self.stdout.write('-' * 79)
                self.stdout.write('\n')
                capture_exception(error)

        if self.ordenar:
            conteudo_arquivos = sorted(conteudo_arquivos)

        rows = []
        for conteudo in conteudo_arquivos:
            rows.extend(conteudo[1])
            # rows.extend(conteudo[0])

        nrows = len(rows)

        if not self.arquivos:
            sys.stdout.write('-' * 79)
            sys.stdout.write(f'Numero de linhas     : {nrows}\n')
            sys.stdout.write('\n')
            sys.stdout.write('Nenhum arquivo encontrado.')
            return

        if isinstance(self.arquivos[0], str):
            nomes_arquivos = ', '.join(self.arquivos)
        else:
            nomes_arquivos = ', '.join([arquivo.path for arquivo in self.arquivos])

        self.stdout.write('-' * 79)
        self.stdout.write('\n')
        self.stdout.write(f'Iniciando o processando do(s) arquivo(s): {nomes_arquivos}\n')
        self.stdout.write('-' * 79)
        self.stdout.write('\n')
        self.stdout.write(f'Numero de linhas     : {nrows}\n')

        self.iterar(rows)

        if self.stdout is not sys.stdout:
            self.stdout.close()

        sys.stdout.write(f'Numero de linhas     : {nrows}\n')
        sys.stdout.write('\n')
        sys.stdout.write(f'Finalizado o processando do(s) arquivo(s): {nomes_arquivos}\n')

        return nrows

    def processar(self, row):
        raise NotImplementedError


class ImportadorNotaCredito(Importador):
    NC = 'NC'
    CONTA_CONTABIL = 'Conta Contábil'
    CONTA_CONTABIL_NOME = 'Conta Contábil Nome'
    DT_LANC = 'Emissão - Dia'
    DOC_OBS = 'Doc - Observação'
    UNIDADE_ORCAMENTARIA = 'Unidade Orçamentária'
    UNIDADE_ORCAMENTARIA_NOME = 'Unidade Orçamentária Nome'
    EMITENTE_GESTAO = 'Emitente - Gestão'
    EMITENTE_GESTAO_NOME = 'Emitente - Gestão Nome'
    EMITENTE_UG = 'Emitente - UG'
    EMITENTE_UG_NOME = 'Emitente - UG Nome'
    FAVORECIDO_DOC = 'Favorecido Doc.'
    FAVORECIDO_DOC_NOME = 'Favorecido Doc. Nome'
    ESFERA_ORCAMENTARIA = 'Esfera Orçamentária'
    ESFERA_ORCAMENTARIA_NOME = 'Esfera Orçamentária Nome'
    ACAO_GOVERNO = 'Ação Governo'
    ACAO_GOVERNO_NOME = 'Ação Governo Nome'
    RESPONSAVEL_UG = 'UG Responsável'
    RESPONSAVEL_UG_NOME = 'UG Responsável Nome'
    PTRES = 'PTRES'
    PI = 'PI'
    PI_NOME = 'PI Nome'
    FONTE_RECURSO = 'Fonte Recursos Detalhada'
    FONTE_RECURSO_NOME = 'Fonte Recursos Detalhada Nome'
    GRUPO_DESPESA = 'Grupo Despesa'
    GRUPO_DESPESA_NOME = 'Grupo Despesa Nome'
    NATUREZA_DESPESA = 'Natureza Despesa'
    NATUREZA_DESPESA_NOME = 'Natureza Despesa Nome'
    SUBITEM = 'Subitem'
    SUBITEM_NOME = 'Subitem Nome'
    SALDO_ATUAL = 'Movim. Líquido - R$ (Conta Contábil)'

    cabecalho_linhas = [2]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ini_row = 3
        self.ignore_last_row = True
        self.delimiter = '\t'

        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write('\n\n')
        self.stdout.write('ImportadorNotaCredito')

    def get_nota_credito(self, numero, row):
        self.log(f'Obtendo Nota de Crédito - {numero}...\n')
        nota_credito = self._cache.get_item('nota_credito', numero)
        if nota_credito is None:
            nota_credito, created = NotaCredito.objects.update_or_create(
                numero=numero,
                defaults={
                    'conta_contabil': self.get_conta_contabil(
                        self.get_texto(self.CONTA_CONTABIL, row), self.get_texto(self.CONTA_CONTABIL_NOME, row)
                    ),
                    'data_emissao': self.format_data(self.get_texto(self.DT_LANC, row)),
                    'observacao': self.get_texto(self.DOC_OBS, row),
                    'unidade_orcamentaria': self.get_classificacao_institucional(
                        self.get_texto(self.UNIDADE_ORCAMENTARIA, row), self.get_texto(self.UNIDADE_ORCAMENTARIA_NOME, row)
                    ),
                    'emitente_ci': self.get_classificacao_institucional(
                        self.get_texto(self.EMITENTE_GESTAO, row), self.get_texto(self.EMITENTE_GESTAO_NOME, row)
                    ),
                    'emitente_ug': self.get_unidade_gestora(self.get_texto(self.EMITENTE_UG, row), self.get_texto(self.EMITENTE_UG_NOME, row)),
                    'favorecido_ug': self.get_unidade_gestora(
                        self.get_texto(self.FAVORECIDO_DOC, row), self.get_texto(self.FAVORECIDO_DOC_NOME, row)
                    ),
                },
            )
            if created:
                self.log(f'Criando Nota de Crédito: {numero}\n')
            else:
                self.log(f'Atualizando Nota de Crédito: {numero}\n')

            self._cache.add_item('nota_credito', numero, nota_credito)

        return nota_credito

    def processar(self, row):
        self.set_row(row)
        numero = self.get_texto(self.NC)
        nota_credito = self.get_nota_credito(numero, row)
        natureza_despesa = self.get_natureza_despesa(self.get_texto(self.NATUREZA_DESPESA), self.get_texto(self.NATUREZA_DESPESA_NOME))
        _nota_item, created = NotaCreditoItem.objects.update_or_create(
            nota_credito=nota_credito,
            esfera_orcamentaria=self.get_esfera_orcamentaria(self.get_texto(self.ESFERA_ORCAMENTARIA), self.get_texto(self.ESFERA_ORCAMENTARIA_NOME)),
            acao_governo=self.get_acao_governo(self.get_texto(self.ACAO_GOVERNO), self.get_texto(self.ACAO_GOVERNO_NOME)),
            responsavel_ug=self.get_unidade_gestora(self.get_texto(self.RESPONSAVEL_UG), self.get_texto(self.RESPONSAVEL_UG_NOME)),
            ptres=self.get_ptres(codigo=self.get_texto(self.PTRES)),
            plano_interno=self.get_plano_interno(self.get_texto(self.PI), self.get_texto(self.PI_NOME)),
            fonte_recurso=self.get_fonte_recurso(self.get_texto(self.FONTE_RECURSO), self.get_texto(self.FONTE_RECURSO_NOME)),
            subitem=self.get_subitem_natureza_despesa(natureza_despesa, self.get_texto(self.SUBITEM), self.get_texto(self.SUBITEM_NOME)),
            defaults={
                'valor': self.get_valor(self.SALDO_ATUAL),
                'naturesa_despesa_original': self.get_texto(self.NATUREZA_DESPESA),
                'grupo_despesa_original': self.get_texto(self.GRUPO_DESPESA),
            },
        )
        if created:
            self.log(f'Criando item da Nota de Crédito: {nota_credito.numero}\n')
        else:
            self.log(f'Atualizando item da Nota de Crédito: {nota_credito.numero}\n')


class ImportadorExecNE(Importador):
    NE = 'NE CCor'
    DOCUMENTO = 'Documento'  # NE, NS, OB, DF, DR, GP, GR
    EVENTO = 'Evento'
    EVENTO_NOME = 'Evento Nome'
    DT_EMICAO = 'Emissão - Dia'
    UNIDADE_ORCAMENTARIA = 'Unidade Orçamentária'
    UNIDADE_ORCAMENTARIA_NOME = 'Unidade Orçamentária Nome'
    ANO_EMICAO = 'NE CCor - Ano Emissão'
    DOC_OBS = 'Doc - Observação'
    FAVORECIDO = 'NE CCor - Favorecido'
    FAVORECIDO_NOME = 'NE CCor - Favorecido Nome'
    ACAO_GOVERNO = 'Ação Governo'
    ACAO_GOVERNO_NOME = 'Ação Governo Nome'
    PTRES = 'PTRES'
    PI = 'PI'
    PI_NOME = 'PI Nome'
    FONTE_RECURSO = 'Fonte Recursos Detalhada'
    FONTE_RECURSO_NOME = 'Fonte Recursos Detalhada Nome'
    ESFERA_ORCAMENTARIA = 'Esfera Orçamentária'
    ESFERA_ORCAMENTARIA_NOME = 'Esfera Orçamentária Nome'
    NATUREZA_DESPESA = 'Natureza Despesa'
    NATUREZA_DESPESA_NOME = 'Natureza Despesa Nome'
    SUBITEM = 'Subitem'
    SUBITEM_NOME = 'Subitem Nome'
    GRUPO_DESPESA = 'Grupo Despesa'
    GRUPO_DESPESA_NOME = 'Grupo Despesa Nome'
    EXECUTORA_UG = 'UG Executora'
    EXECUTORA_UG_NOME = 'UG Executora Nome'
    RESPONSAVEL_UG = 'UG Responsável'
    RESPONSAVEL_UG_NOME = 'UG Responsável Nome'
    DESPESAS_EMPENHADAS = 'DESPESAS EMPENHADAS (CONTROLE EMPENHO)'  # NE
    DESPESAS_LIQUIDADAS = 'DESPESAS LIQUIDADAS (CONTROLE EMPENHO)'  # NS
    DESPESAS_PAGAS = 'DESPESAS PAGAS (CONTROLE EMPENHO)'  # Diferente de NE e NS

    cabecalho_linhas = [2, 3, 4]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ini_row = 5
        self.ordenar = True
        self.ordenar_por = self.DT_EMICAO
        self.delimiter = ','

        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write('\n\n')
        self.stdout.write('ImportadorExecNE')

    def get_tipo(self, numero_documento):
        return re.findall(r'\D+', numero_documento)[0]

    def get_documento_classe(self, tipo):
        ClasseDocumento = None
        if tipo in [DocumentoBase.TIPO_NE, DocumentoBase.TIPO_RO]:
            ClasseDocumento = DocumentoEmpenho
        elif tipo == DocumentoBase.TIPO_NS:
            ClasseDocumento = DocumentoLiquidacao
        elif tipo in [
            DocumentoBase.TIPO_OB,
            DocumentoBase.TIPO_DF,
            DocumentoBase.TIPO_DR,
            DocumentoBase.TIPO_GP,
            DocumentoBase.TIPO_GR,
            DocumentoBase.TIPO_GF,
            DocumentoBase.TIPO_NL,
        ]:
            ClasseDocumento = DocumentoPagamento

        return ClasseDocumento

    def processar_documento(self, row):
        self.set_row(row)
        numero_ne = self.get_texto(self.NE)
        numero_documento = self.get_texto(self.DOCUMENTO)
        self.log(f'Adicionando Documento {numero_documento} da Nota de Empenho: {numero_ne}\n')
        documento = self._cache.get_item('documento', numero_documento)
        tipo = self.get_tipo(numero_documento)
        if documento is None:
            ClasseDocumento = self.get_documento_classe(tipo)
            documento, created = ClasseDocumento.objects.update_or_create(
                numero=numero_documento,
                defaults={
                    'tipo': tipo,
                    'data_emissao': self.format_data(self.get_texto(self.DT_EMICAO)),
                    'unidade_orcamentaria': self.get_classificacao_institucional(
                        self.get_texto(self.UNIDADE_ORCAMENTARIA), self.get_texto(self.UNIDADE_ORCAMENTARIA_NOME)
                    ),
                    'observacao': self.get_texto(self.DOC_OBS),
                    'favorecido_codigo': self.get_texto(self.FAVORECIDO),
                    'favorecido_nome': self.get_texto(self.FAVORECIDO_NOME),
                    'acao_governo': self.get_acao_governo(self.get_texto(self.ACAO_GOVERNO), self.get_texto(self.ACAO_GOVERNO_NOME)),
                    'ptres': self.get_ptres(codigo=self.get_texto(self.PTRES)),
                    'plano_interno': self.get_plano_interno(self.get_texto(self.PI), self.get_texto(self.PI_NOME)),
                    'fonte_recurso': self.get_fonte_recurso(self.get_texto(self.FONTE_RECURSO), self.get_texto(self.FONTE_RECURSO_NOME)),
                    'esfera_orcamentaria': self.get_esfera_orcamentaria(
                        self.get_texto(self.ESFERA_ORCAMENTARIA), self.get_texto(self.ESFERA_ORCAMENTARIA_NOME)
                    ),
                    'emitente_ug': self.get_unidade_gestora(self.get_texto(self.EXECUTORA_UG), self.get_texto(self.EXECUTORA_UG_NOME)),
                    'responsavel_ug': self.get_unidade_gestora(self.get_texto(self.RESPONSAVEL_UG), self.get_texto(self.RESPONSAVEL_UG_NOME)),
                    'acao_governo_original': self.get_texto(self.ACAO_GOVERNO),
                    'fonte_recurso_original': self.get_texto(self.FONTE_RECURSO),
                    'naturesa_despesa_original': self.get_texto(self.NATUREZA_DESPESA),
                    'grupo_despesa_original': self.get_texto(self.GRUPO_DESPESA),
                },
            )
            documento.tipo = tipo
            if tipo in [DocumentoBase.TIPO_NE, DocumentoBase.TIPO_RO]:
                documento.documento_empenho_inicial = self._cache.get_item('documento', numero_ne)

            documento.save()
            if created:
                self.log(f'Criando Documento: {numero_documento}\n')
            else:
                self.log(f'Atualizando Documento: {numero_documento}\n')

            self._cache.add_item('documento', numero_documento, documento)

        return documento

    def processar_documento_item(self, row):
        self.set_row(row)
        numero_ne = self.get_texto(self.NE)
        numero_documento = self.get_texto(self.DOCUMENTO)
        natureza_despesa = self.get_natureza_despesa(self.get_texto(self.NATUREZA_DESPESA), self.get_texto(self.NATUREZA_DESPESA_NOME))
        subitem = self.get_subitem_natureza_despesa(natureza_despesa, self.get_texto(self.SUBITEM), self.get_texto(self.SUBITEM_NOME))

        self.log(f'Adicionando Documento {numero_documento} da Nota de Empenho: {numero_ne}\n')
        tipo = self.get_tipo(numero_documento)
        ClasseDocumento = self.get_documento_classe(tipo)
        documento = self._cache.get_item('documento', numero_documento)
        if documento is None:
            documento = ClasseDocumento.objects.get(numero=numero_documento)

        if tipo in [DocumentoBase.TIPO_NE, DocumentoBase.TIPO_RO]:
            evento = self.get_evento_nota_empenho(self.get_texto(self.EVENTO), self.get_texto(self.EVENTO_NOME))
            valor = self.get_valor(self.DESPESAS_EMPENHADAS)
            ClasseDocumentoItem = DocumentoEmpenhoItem
            kwargs = {'documento_empenho': documento, 'subitem': subitem, 'valor': valor}
        elif tipo == DocumentoBase.TIPO_NS:
            evento = self.get_evento_nota_empenho(self.get_texto(self.EVENTO), self.get_texto(self.EVENTO_NOME))
            valor = self.get_valor(self.DESPESAS_LIQUIDADAS)
            if valor == 0:
                return
            ClasseDocumentoItem = DocumentoLiquidacaoItem
            documento_empenho_inicial = self._cache.get_item('documento', numero_ne)
            kwargs = {'documento_liquidacao': documento, 'subitem': subitem, 'documento_empenho_inicial': documento_empenho_inicial, 'valor': valor}
        else:
            valor = self.get_valor(self.DESPESAS_PAGAS)
            ClasseDocumentoItem = DocumentoPagamentoItem
            documento_empenho_inicial = self._cache.get_item('documento', numero_ne)
            kwargs = {'documento_pagamento': documento, 'subitem': subitem, 'documento_empenho_inicial': documento_empenho_inicial}

        if tipo in [DocumentoBase.TIPO_NE, DocumentoBase.TIPO_RO, DocumentoBase.TIPO_NS]:
            documento_item = ClasseDocumentoItem.objects.filter(**kwargs).filter(valor=valor)
        else:
            documento_item = ClasseDocumentoItem.objects.filter(**kwargs)

        documento_item = documento_item.first()
        if documento_item:
            self.log(f'Atualizando item do Documento: {numero_documento}\n')
            documento_item.valor = valor
        else:
            self.log(f'Criando item do Documento: {numero_documento}\n')
            documento_item = ClasseDocumentoItem(**kwargs)
            documento_item.valor = valor

        if tipo in [DocumentoBase.TIPO_NE, DocumentoBase.TIPO_RO, DocumentoBase.TIPO_NS]:
            documento_item.evento = evento

        documento_item.subitem_original = self.get_texto(self.SUBITEM)
        documento_item.save()

    def iterar(self, rows):
        ne_ro = {}
        for row in rows:
            self.set_row(row)
            numero_ne = self.get_texto(self.NE)
            numero_documento = self.get_texto(self.DOCUMENTO)
            ano_emissao = self.get_texto(self.ANO_EMICAO)
            if ano_emissao < '2021':
                if numero_ne == numero_documento:
                    self.processar_documento(row)
            else:
                tipo = self.get_tipo(numero_documento)
                if tipo == DocumentoBase.TIPO_RO:
                    if numero_ne not in ne_ro:
                        ne_ro[numero_ne] = []
                    ne_ro[numero_ne].append(row)

        # Trata a primeira RO como Empenho inicial
        for ro_rows in ne_ro.values():
            ro_rows = sorted(ro_rows, key=lambda row: self.get_texto(self.DOCUMENTO, row))
            ro_rows = sorted(ro_rows, key=lambda row: self.get_texto(self.DT_EMICAO, row))
            empenho_row = ro_rows[0].copy()
            numero_ne = self.get_texto(self.NE, empenho_row)
            indice = self.get_indice(self.DOCUMENTO)
            empenho_row[indice] = numero_ne
            self.processar_documento(empenho_row)
            de = DocumentoEmpenho.objects.get(numero=numero_ne)
            de.itens.all().delete()

        for row in rows:
            self.set_row(row)
            numero_ne = self.get_texto(self.NE)
            numero_documento = self.get_texto(self.DOCUMENTO)
            if numero_ne != numero_documento:
                self.processar_documento(row)

        self.log('\nInserindo itens dos documentos\n')
        for row in rows:
            self.processar_documento_item(row)


class ImportadorRAP(Importador):
    EXECUTORA_UG = 'UG Executora'
    EXECUTORA_UG_NOME = 'UG Executora Nome'
    RESPONSAVEL_UG = 'UG Responsável'
    RESPONSAVEL_UG_NOME = 'UG Responsável Nome'
    UNIDADE_ORCAMENTARIA = 'Unidade Orçamentária'
    UNIDADE_ORCAMENTARIA_NOME = 'Unidade Orçamentária Nome'
    ACAO_GOVERNO = 'Ação Governo'
    ACAO_GOVERNO_NOME = 'Ação Governo Nome'
    PTRES = 'PTRES'
    PI = 'PI'
    PI_NOME = 'PI Nome'
    ANO_LANCAMENTO = 'Ano Lançamento'
    ANO_EMICAO = 'NE CCor - Ano Emissão'
    NE = 'NE CCor'
    NATUREZA_DESPESA = 'Natureza Despesa'
    NATUREZA_DESPESA_NOME = 'Natureza Despesa Nome'
    SUBITEM = 'Subitem'
    SUBITEM_NOME = 'Subitem Nome'
    GRUPO_DESPESA = 'Grupo Despesa'
    GRUPO_DESPESA_NOME = 'Grupo Despesa Nome'
    FONTE_RECURSO = 'Fonte Recursos Detalhada'
    FONTE_RECURSO_NOME = 'Fonte Recursos Detalhada Nome'
    RAP_PROC_INSCRITOS = 'RESTOS A PAGAR PROCESSADOS INSCRITOS'
    RAP_PROC_REINSCRITOS = 'RESTOS A PAGAR PROCESSADOS REINSCRITOS'
    RAP_PROC_CANCELADOS = 'RESTOS A PAGAR PROCESSADOS CANCELADOS'
    RAP_PROC_PAGOS = 'RESTOS A PAGAR PROCESSADOS PAGOS'
    RAP_N_PROC_INSCRITOS = 'RESTOS A PAGAR NAO PROCESSADOS INSCRITOS'
    RAP_N_PROC_REINSCRITOS = 'RESTOS A PAGAR NAO PROCESSADOS REINSCRITOS'
    RAP_N_PROC_CANCELADOS = 'RESTOS A PAGAR NAO PROCESSADOS CANCELADOS'
    RAP_N_PROC_LIQUIDADOS = 'RESTOS A PAGAR NAO PROCESSADOS LIQUIDADOS'
    RAP_N_PROC_PAGOS = 'RESTOS A PAGAR NAO PROCESSADOS PAGOS'

    cabecalho_linhas = [0, 1, 2, 3, 4]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ini_row = 5
        self.delimiter = '\t'

        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write('\n\n')
        self.stdout.write('ImportadorRAP')

    def processar(self, row):
        self.set_row(row)
        numero_ne = self.get_texto(self.NE)
        rap = self._cache.get_item('rap', numero_ne)
        if rap is None:
            rap, created = RAP.objects.update_or_create(
                numero=numero_ne,
                ano=self.get_texto(self.ANO_LANCAMENTO),
                defaults={
                    'unidade_orcamentaria': self.get_classificacao_institucional(
                        self.get_texto(self.UNIDADE_ORCAMENTARIA), self.get_texto(self.UNIDADE_ORCAMENTARIA_NOME)
                    ),
                    'acao_governo': self.get_acao_governo(self.get_texto(self.ACAO_GOVERNO), self.get_texto(self.ACAO_GOVERNO_NOME)),
                    'ptres': self.get_ptres(codigo=self.get_texto(self.PTRES)),
                    'plano_interno': self.get_plano_interno(self.get_texto(self.PI), self.get_texto(self.PI_NOME)),
                    'fonte_recurso': self.get_fonte_recurso(self.get_texto(self.FONTE_RECURSO), self.get_texto(self.FONTE_RECURSO_NOME)),
                    'emitente_ug': self.get_unidade_gestora(self.get_texto(self.EXECUTORA_UG), self.get_texto(self.EXECUTORA_UG_NOME)),
                    'responsavel_ug': self.get_unidade_gestora(self.get_texto(self.RESPONSAVEL_UG), self.get_texto(self.RESPONSAVEL_UG_NOME)),
                    'acao_governo_original': self.get_texto(self.ACAO_GOVERNO),
                    'fonte_recurso_original': self.get_texto(self.FONTE_RECURSO),
                    'naturesa_despesa_original': self.get_texto(self.NATUREZA_DESPESA),
                    'grupo_despesa_original': self.get_texto(self.GRUPO_DESPESA),
                },
            )
            if created:
                self.log(f'Criando RAP: {numero_ne}\n')
            else:
                self.log(f'Atualizando RAP: {numero_ne}\n')

            self._cache.add_item('rap', numero_ne, rap)

        natureza_despesa = self.get_natureza_despesa(self.get_texto(self.NATUREZA_DESPESA), self.get_texto(self.NATUREZA_DESPESA_NOME))
        subitem = self.get_subitem_natureza_despesa(natureza_despesa, self.get_texto(self.SUBITEM), self.get_texto(self.SUBITEM_NOME))
        _rap_item, created = RAPItem.objects.update_or_create(
            rap=rap,
            subitem=subitem,
            subitem_original=self.get_texto(self.SUBITEM),
            defaults={
                'valor_proc_inscrito': self.get_valor(self.RAP_PROC_INSCRITOS),
                'valor_proc_reinscrito': self.get_valor(self.RAP_PROC_REINSCRITOS),
                'valor_proc_cancelado': self.get_valor(self.RAP_PROC_CANCELADOS),
                'valor_proc_pago': self.get_valor(self.RAP_PROC_PAGOS),
                'valor_nao_proc_inscrito': self.get_valor(self.RAP_N_PROC_INSCRITOS),
                'valor_nao_proc_reinscrito': self.get_valor(self.RAP_N_PROC_REINSCRITOS),
                'valor_nao_proc_cancelado': self.get_valor(self.RAP_N_PROC_CANCELADOS),
                'valor_nao_proc_liquidado': self.get_valor(self.RAP_N_PROC_LIQUIDADOS),
                'valor_nao_proc_pago': self.get_valor(self.RAP_N_PROC_PAGOS),
            },
        )
        if created:
            self.log(f'Criando item do RAP: {numero_ne}\n')
        else:
            self.log(f'Atualizando item do RAP: {numero_ne}\n')


class ImportadorGRU(Importador):
    EXECUTORA_UG = 'UG Executora'
    EXECUTORA_UG_NOME = 'UG Executora Nome'
    GRU = 'Cód. Recolhimento GRU'
    GRU_NOME = 'Cód. Recolhimento GRU Nome'
    ANO_LANCAMENTO = 'Ano Lançamento'
    VALOR = 'RECEITA ARRECADADA POR GRU'

    cabecalho_linhas = [5, 6, 7]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ini_row = 8
        self.delimiter = '\t'

        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write('\n\n')
        self.stdout.write('ImportadorGRU')

    def processar(self, row):
        self.set_row(row)
        executora = self.get_texto(self.EXECUTORA_UG)
        gru = self.get_texto(self.GRU)
        identificador = f'{executora}-{gru}'
        receita_gru = self._cache.get_item('receita_gru', identificador)
        if receita_gru is None:
            receita_gru, created = ReceitaGRU.objects.update_or_create(
                emitente_ug=self.get_unidade_gestora(executora, self.get_texto(self.EXECUTORA_UG_NOME)),
                gru=self.get_gru(gru, self.get_texto(self.GRU_NOME)),
                ano=self.get_texto(self.ANO_LANCAMENTO),
                defaults={'valor': self.get_valor(self.VALOR)},
            )
            if created:
                self.log(f'Criando ReceitaGRU: {identificador}\n')
            else:
                self.log(f'Atualizando ReceitaGRU: {identificador}\n')

            self._cache.add_item('rap', identificador, receita_gru)


class ImportadorNotaDotacao(Importador):
    EXECUTORA_UG = 'UG Executora'
    EXECUTORA_UG_NOME = 'UG Executora Nome'
    NUMERO = 'ND'
    RESPONSAVEL_UG = 'ND - UG Responsável'
    RESPONSAVEL_UG_NOME = 'ND - UG Responsável Nome'
    DETALHAMENTO = 'ND - Detalhamento'
    DATA_EMISSAO = 'Emissão - Dia'
    OBSERVACAO = 'Doc - Observação'
    ESPECIE = 'ND - Espécie'
    EVENTO = 'Evento'
    EVENTO_NOME = 'Evento Nome'
    PI = 'ND - Plano Interno'
    PI_NOME = 'ND - Plano Interno Nome'
    PI_DESCRICAO = 'ND - Plano Interno Nome Nome'
    ACAO_GOVERNO = 'Ação Governo'
    ACAO_GOVERNO_NOME = 'Ação Governo Nome'
    PTRES = 'ND - PTRES'
    GRUPO_DESPESA = 'Grupo Despesa'
    GRUPO_DESPESA_NOME = 'Grupo Despesa Nome'
    FONTE_RECURSO = 'Fonte Recursos Detalhada'
    FONTE_RECURSO_NOME = 'Fonte Recursos Detalhada Nome'
    VALOR = 'ND - Valor Linha'
    VALOR_LIQUIDO = 'Movim. Líquido - R$ (Conta Contábil)'

    cabecalho_linhas = [2, 3, 4]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ini_row = 5
        self.ignore_last_row = True
        self.delimiter = '\t'

        self.stdout = open(self.log_nome_arquivo, 'a') if self.tipo_log == self.LOG_ARQUIVO else sys.stdout
        self.stdout.write('\n\n')
        self.stdout.write('ImportadorNotaDotacao')

    def get_nota_dotacao(self, numero, row):
        self.log(f'Obtendo Nota de Dotação - {numero}...\n')
        nota_dotacao = self._cache.get_item('nota_dotacao', numero)
        if nota_dotacao is None:
            nota_dotacao, created = NotaDotacao.objects.update_or_create(
                numero=numero,
                defaults={
                    'executora_ug': self.get_unidade_gestora(self.get_texto(self.EXECUTORA_UG), self.get_texto(self.EXECUTORA_UG_NOME)),
                    'data_emissao': self.format_data(self.get_texto(self.DATA_EMISSAO)),
                    'observacao': self.get_texto(self.OBSERVACAO),
                    'especie': self.get_texto(self.ESPECIE),
                    'acao_governo': self.get_acao_governo(self.get_texto(self.ACAO_GOVERNO), self.get_texto(self.ACAO_GOVERNO_NOME)),
                    'ptres': self.get_ptres(codigo=self.get_texto(self.PTRES)),
                    'grupo_despesa_original': self.get_texto(self.GRUPO_DESPESA),
                    'fonte_recurso': self.get_fonte_recurso(self.get_texto(self.FONTE_RECURSO), self.get_texto(self.FONTE_RECURSO_NOME)),
                },
            )
            if created:
                self.log(f'Criando Nota de Dotação: {numero}\n')
            else:
                self.log(f'Atualizando Nota de Dotação: {numero}\n')

            self._cache.add_item('nota_dotacao', numero, nota_dotacao)

        return nota_dotacao

    def processar(self, row):
        self.set_row(row)
        numero = self.get_texto(self.NUMERO)
        nota_dotacao = self.get_nota_dotacao(numero, row)
        _nota_item, created = NotaDotacaoItem.objects.update_or_create(
            nota_dotacao=nota_dotacao,
            responsavel_ug=self.get_unidade_gestora(self.get_texto(self.RESPONSAVEL_UG), self.get_texto(self.RESPONSAVEL_UG_NOME)),
            detalhamento=self.get_texto(self.DETALHAMENTO),
            evento=self.get_evento_nota_credito(self.get_texto(self.EVENTO), self.get_texto(self.EVENTO_NOME)),
            plano_interno=self.get_plano_interno(self.get_texto(self.PI), self.get_texto(self.PI_NOME), self.get_texto(self.PI_DESCRICAO)),
            valor=self.get_valor(self.VALOR),
            valor_liquido=self.get_valor(self.VALOR_LIQUIDO),
        )
        if created:
            self.log(f'Criando item da Nota de Dotação: {nota_dotacao.numero}\n')
        else:
            self.log(f'Atualizando item da Nota de Dotação: {nota_dotacao.numero}\n')
