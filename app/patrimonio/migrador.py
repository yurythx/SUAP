"""
Migrador de inventários do patrimônio a partir de planilha, uma linha por bem tombado::

    Empenho → EmpenhoPermanente → Entrada → EntradaPermanente
        → Inventario (+ InventarioCargaContabil + MovimentoPatrim de pendência)
        → Requisicao já deferida (+ MovimentoPatrim de transferência)

Regras de negócio: sem número de empenho o bem entra como doação (fornecedor continua exigido,
é ele que identifica o doador); sem responsável, para no movimento de pendência, sem requisição;
o tombo é gerado pelo SUAP, e o número do sistema antigo fica em ``Inventario.observacao``.

A leitura (:func:`conferir`) é separada da escrita (:func:`executar`) para que planilha com erro
não deixe meia migração no banco. Entre os dois passos a planilha não é gravada: fica no
navegador e volta com a confirmação, seguindo como bytes para a task (:func:`como_arquivo`).
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from pycpfcnpj import cpfcnpj

from almoxarifado.models import Empenho, Entrada, EntradaTipo, MaterialTipo
from djtools.utils.masks import mask_cnpj, mask_cpf
from patrimonio.models import (
    CategoriaMaterialPermanente,
    EmpenhoPermanente,
    EntradaPermanente,
    Inventario,
    InventarioRotulo,
    Requisicao,
    RequisicaoHistorico,
    RequisicaoItem,
)
from rh.models import PessoaExterna, PessoaFisica, PessoaJuridica, Servidor, UnidadeOrganizacional

if TYPE_CHECKING:
    from comum.models import User, Vinculo


@dataclass(frozen=True)
class Coluna:
    """
    Uma coluna do layout canônico da planilha de migração.

    ``obrigatoria`` é sobre o cabeçalho; ``condicional`` diz quando a *célula* pode ficar vazia
    (é o caso do empenho, cuja ausência define a entrada como doação).

    ``limite`` é o ``max_length`` do campo que vai receber a célula. Conferi-lo na leitura é o
    que sustenta a promessa da tela: sem ele o texto passa na conferência e só estoura como
    ``DataError`` no meio da task, sem dizer qual linha da planilha causou.
    """

    nome: str
    rotulo: str
    obrigatoria: bool
    ajuda: str
    exemplo: str
    condicional: str = ''
    limite: int = 0

    @property
    def instrucao(self) -> str:
        """Ajuda como ela aparece na aba de instruções do modelo, já com o limite de tamanho."""
        return f'{self.ajuda} Até {self.limite} caracteres.' if self.limite else self.ajuda


COLUNAS: tuple[Coluna, ...] = (
    Coluna('campus_sigla', 'Campus', True, 'Sigla da unidade que recebeu o bem (UG emitente do empenho).', 'CNAT'),
    Coluna(
        'empenho_numero',
        'Nº do Empenho',
        True,
        'Número do empenho, único por campus. Deixe a célula VAZIA para o bem entrar como doação.',
        '2024NE800123',
        condicional='vazio migra o bem como doação',
        # `Empenho.numero` é varchar(14), e o exemplo já gasta 12: é o campo mais apertado da planilha.
        limite=14,
    ),
    Coluna(
        'fornecedor_documento',
        'CPF/CNPJ do Fornecedor',
        True,
        'CNPJ (pessoa jurídica) ou CPF (pessoa física), com ou sem máscara. Exigido também na doação, onde identifica o doador.',
        '33.000.167/0001-01',
    ),
    Coluna(
        'fornecedor_nome',
        'Nome/Razão Social do Fornecedor',
        True,
        'Usado apenas quando o documento ainda não existe no SUAP.',
        'MOVEIS BRASIL LTDA',
        limite=200,
    ),
    Coluna('nota_fiscal_numero', 'Nº da Nota Fiscal', False, 'Agrupa os bens em entradas distintas.', '4567', limite=25),
    Coluna('nota_fiscal_data', 'Data da Nota Fiscal', False, 'Formato dd/mm/aaaa.', '15/03/2024'),
    Coluna('entrada_data', 'Data da Entrada', True, 'Data em que o bem entrou no patrimônio. Formato dd/mm/aaaa.', '20/03/2024'),
    Coluna('elemento_despesa_codigo', 'Código do Elemento de Despesa', True, 'Precisa existir no cadastro de Elementos de Despesa.', '449052'),
    Coluna(
        'descricao',
        'Descrição do Bem',
        True,
        'Bens de mesma descrição, valor e elemento de despesa são agrupados no mesmo item.',
        'Cadeira giratória',
    ),
    Coluna('valor', 'Valor Unitário', True, 'Valor de aquisição do bem. Aceita 1.234,56 ou 1234.56.', '389,90'),
    Coluna('numero_serie', 'Nº de Série', False, 'Número de série do fabricante.', 'SN-99120', limite=50),
    Coluna(
        'estado_conservacao', 'Estado de Conservação', False, 'bom, ocioso, recuperavel, antieconomico ou irreversivel. Vazio assume "bom".', 'bom'
    ),
    Coluna('responsavel_matricula', 'Matrícula do Responsável', False, 'Deixe VAZIO para o bem entrar como pendente, sem carga.', '1234567'),
    Coluna(
        'sala_nome',
        'Sala',
        False,
        'Nome da sala onde o bem está no sistema antigo. Vira um rótulo do inventário, criado se ainda não existir.',
        'Sala 12',
        limite=100,
    ),
    Coluna('observação', 'Observação', False, 'É aqui que vai o TOMBO ANTIGO do sistema anterior.', 'Tombo antigo: 004521'),
)

COLUNAS_POR_NOME: dict[str, Coluna] = {coluna.nome: coluna for coluna in COLUNAS}
COLUNAS_OBRIGATORIAS: tuple[str, ...] = tuple(coluna.nome for coluna in COLUNAS if coluna.obrigatoria)

ESTADOS_CONSERVACAO: dict[str, str] = {valor: rotulo for valor, rotulo in Inventario.CHOICES_CONSERVACAO if valor}

LIMITE_EXEMPLOS = 30
"""Exemplos de erro (ou aviso) por coluna; o teto é por coluna, não por linha da planilha."""

LIMITE_ATENCAO = 20
"""Cadastros com atenção detalhados na tela; o resto vira contagem."""

LIMITE_VALOR = Decimal(10) ** 9
"""`EntradaPermanente.valor` é ``numeric(15, 6)``: nove dígitos inteiros, e o décimo estoura no banco."""


def marcador_de_origem() -> str:
    """
    Texto gravado em ``Empenho.observacao`` e ``Requisicao.descricao`` para rastrear a origem.

    Auto-contido de propósito: substitui um registro de migração, que não existe.
    """
    return f'Migração de inventários por planilha em {date.today():%d/%m/%Y}'


@dataclass
class Ocorrencia:
    """Um problema encontrado na planilha, sempre ancorado na linha do arquivo."""

    linha: int
    coluna: str
    mensagem: str

    def __str__(self) -> str:
        if self.linha:
            return f'Linha {self.linha}: {self.mensagem}'
        return self.mensagem


@dataclass
class LinhaBem:
    """Uma linha da planilha já convertida em objetos do SUAP."""

    numero: int
    campus: UnidadeOrganizacional
    empenho_numero: str
    fornecedor_documento: str
    fornecedor_nome: str
    nota_fiscal_numero: str
    nota_fiscal_data: date | None
    entrada_data: date
    categoria: CategoriaMaterialPermanente
    descricao: str
    valor: Decimal
    numero_serie: str
    estado_conservacao: str
    observacao: str
    servidor: Servidor | None
    rotulo_nome: str

    @property
    def eh_doacao(self) -> bool:
        """Sem número de empenho o bem não foi comprado: entra como doação do fornecedor informado."""
        return not self.empenho_numero

    @property
    def chave_empenho(self) -> tuple[int, str] | None:
        """``None`` na doação, que não abre empenho — é o que a tira dos agrupamentos por empenho."""
        if self.eh_doacao:
            return None
        return (self.campus.pk, self.empenho_numero)

    @property
    def chave_entrada(self) -> tuple[Any, ...]:
        """
        Agrupa os bens que entram pela mesma ``Entrada``: na compra separa o empenho; na doação,
        o fornecedor, senão dois doadores do mesmo dia cairiam na mesma entrada, que guarda um
        fornecedor só.
        """
        agrupador = self.empenho_numero or f'doacao:{self.fornecedor_documento}'
        return (self.campus.pk, agrupador, self.nota_fiscal_numero, self.entrada_data)

    @property
    def chave_item(self) -> tuple[Any, ...]:
        return (*self.chave_entrada, self.categoria.pk, self.descricao, self.valor)


EXISTENTE = 'existente'
SERA_CRIADO = 'sera_criado'
ATENCAO = 'atencao'


@dataclass
class Cadastro:
    """
    Um cadastro do SUAP referenciado pela planilha e o que a migração fará com ele.

    Responde "o que já existe aqui?" antes de qualquer gravação.
    """

    tipo: str
    identificacao: str
    descricao: str
    situacao: str
    detalhe: str = ''
    url: str = ''
    linhas: int = 0

    @property
    def existente(self) -> bool:
        return self.situacao in (EXISTENTE, ATENCAO)


@dataclass
class ResumoOcorrencias:
    """Quantas vezes uma coluna deu problema, com alguns exemplos para orientar a correção."""

    coluna: str
    total: int
    exemplos: list[str]


@dataclass
class ResumoCadastros:
    """Quantos cadastros de um tipo a planilha referencia, separados pelo que a migração fará."""

    tipo: str
    total: int
    existentes: int
    a_criar: int
    com_atencao: int


def resumir_ocorrencias(ocorrencias: list[Ocorrencia]) -> list[ResumoOcorrencias]:
    """
    Agrupa as ocorrências por coluna, com exemplos distintos.

    Por coluna a tela tem tamanho constante; uma linha por ocorrência cresceria com a planilha.
    """
    por_coluna: dict[str, list[Ocorrencia]] = defaultdict(list)
    for ocorrencia in ocorrencias:
        por_coluna[ocorrencia.coluna].append(ocorrencia)

    resumos = []
    for coluna, achadas in por_coluna.items():
        exemplos: list[str] = []
        vistas: set[str] = set()
        for ocorrencia in achadas:
            # Exemplos de problemas *diferentes*: mensagem repetida não ensina nada na segunda vez.
            if ocorrencia.mensagem in vistas:
                continue
            vistas.add(ocorrencia.mensagem)
            exemplos.append(str(ocorrencia))
            if len(exemplos) == LIMITE_EXEMPLOS:
                break
        resumos.append(ResumoOcorrencias(coluna, len(achadas), exemplos))
    return sorted(resumos, key=lambda resumo: (-resumo.total, resumo.coluna))


@dataclass
class Conferencia:
    """Resultado da leitura da planilha, antes de qualquer escrita no banco."""

    linhas: list[LinhaBem] = field(default_factory=list)
    erros: list[Ocorrencia] = field(default_factory=list)
    avisos: list[Ocorrencia] = field(default_factory=list)
    cadastros: list[Cadastro] = field(default_factory=list)

    @property
    def valida(self) -> bool:
        return not self.erros and bool(self.linhas)

    @property
    def cadastros_a_criar(self) -> list[Cadastro]:
        return [cadastro for cadastro in self.cadastros if cadastro.situacao == SERA_CRIADO]

    @property
    def cadastros_com_atencao(self) -> list[Cadastro]:
        return [cadastro for cadastro in self.cadastros if cadastro.situacao == ATENCAO]

    @property
    def erros_por_coluna(self) -> list[ResumoOcorrencias]:
        return resumir_ocorrencias(self.erros)

    @property
    def avisos_por_coluna(self) -> list[ResumoOcorrencias]:
        return resumir_ocorrencias(self.avisos)

    @property
    def cadastros_por_tipo(self) -> list[ResumoCadastros]:
        """
        Contagem por tipo de cadastro, que é o que a tela mostra — a lista crua tem um item por
        fornecedor, rótulo, responsável e nota fiscal citados, milhares numa planilha grande.
        """
        por_tipo: dict[str, list[Cadastro]] = defaultdict(list)
        for cadastro in self.cadastros:
            por_tipo[cadastro.tipo].append(cadastro)
        return [
            ResumoCadastros(
                tipo=tipo,
                total=len(achados),
                existentes=sum(1 for cadastro in achados if cadastro.situacao == EXISTENTE),
                a_criar=sum(1 for cadastro in achados if cadastro.situacao == SERA_CRIADO),
                com_atencao=sum(1 for cadastro in achados if cadastro.situacao == ATENCAO),
            )
            for tipo, achados in sorted(por_tipo.items())
        ]

    @property
    def atencao_em_destaque(self) -> list[Cadastro]:
        """Os cadastros com atenção que cabem na tela — são os únicos que pedem leitura caso a caso."""
        return self.cadastros_com_atencao[:LIMITE_ATENCAO]

    @property
    def total_bens(self) -> int:
        return len(self.linhas)

    @property
    def total_com_responsavel(self) -> int:
        return sum(1 for linha in self.linhas if linha.servidor)

    @property
    def total_pendentes(self) -> int:
        return self.total_bens - self.total_com_responsavel

    @property
    def total_empenhos(self) -> int:
        return len({chave for chave in (linha.chave_empenho for linha in self.linhas) if chave})

    @property
    def total_doacoes(self) -> int:
        """Bens sem empenho na planilha, que entram como doação."""
        return sum(1 for linha in self.linhas if linha.eh_doacao)

    @property
    def total_compras(self) -> int:
        return self.total_bens - self.total_doacoes

    @property
    def total_entradas(self) -> int:
        return len({linha.chave_entrada for linha in self.linhas})

    @property
    def total_itens(self) -> int:
        return len({linha.chave_item for linha in self.linhas})

    @property
    def total_requisicoes(self) -> int:
        return len({chave for chave in (chave_de_carga(linha) for linha in self.linhas) if chave})

    @property
    def valor_total(self) -> Decimal:
        return sum((linha.valor for linha in self.linhas), Decimal('0'))

    @property
    def campi(self) -> list[str]:
        """Siglas dos campi atingidos. A migração não tem campus próprio: quem manda é a planilha."""
        return sorted({linha.campus.sigla for linha in self.linhas})

    def resumo(self) -> dict[str, Any]:
        """Números exibidos no passo de confirmação e guardados no histórico da migração."""
        return {
            'campi': self.campi,
            'bens': self.total_bens,
            'compras': self.total_compras,
            'doacoes': self.total_doacoes,
            'empenhos': self.total_empenhos,
            'entradas': self.total_entradas,
            'itens': self.total_itens,
            'requisicoes': self.total_requisicoes,
            'com_responsavel': self.total_com_responsavel,
            'pendentes': self.total_pendentes,
            'valor_total': str(self.valor_total),
        }


def chave_de_rotulo(linha: LinhaBem) -> tuple[int, str] | None:
    """Agrupa as linhas que apontam para o mesmo rótulo: mesmo campus, mesmo nome normalizado."""
    if not linha.rotulo_nome:
        return None
    return (linha.campus.pk, chave_de_nome(linha.rotulo_nome))


def chave_de_carga(linha: LinhaBem) -> tuple[int, int] | None:
    """Agrupa os bens que vão para a mesma requisição de carga (mesmo servidor, mesmo campus)."""
    if not linha.servidor:
        return None
    return (linha.servidor.pk, linha.campus.pk)


def chave_de_fornecedor(linha: LinhaBem) -> str | None:
    """Agrupa as linhas do mesmo fornecedor. Documento vazio já é erro de leitura, e sai do levantamento."""
    return linha.fornecedor_documento or None


def chave_de_servidor(linha: LinhaBem) -> int | None:
    """Agrupa as linhas do mesmo responsável; a linha sem responsável fica de fora."""
    if not linha.servidor:
        return None
    return linha.servidor.pk


def chave_de_nota_fiscal(linha: LinhaBem) -> tuple[Any, ...] | None:
    """Agrupa as linhas da mesma nota fiscal; sem número de nota a linha sai do levantamento."""
    if not linha.nota_fiscal_numero:
        return None
    return linha.chave_entrada


def texto_da_celula(valor: Any) -> str:
    """Normaliza uma célula em texto, tratando os vazios que o pandas produz."""
    if valor is None:
        return ''
    if isinstance(valor, float) and pd.isna(valor):
        return ''
    texto = str(valor).strip()
    if texto.lower() in ('nan', 'nat', 'none'):
        return ''
    return ' '.join(texto.split())


def chave_de_nome(valor: str) -> str:
    """Chave de comparação de nome livre: sem acento, sem caixa e sem espaço sobrando."""
    sem_acento = unicodedata.normalize('NFKD', valor).encode('ascii', 'ignore').decode()
    return ' '.join(sem_acento.split()).casefold()


def so_digitos(valor: Any) -> str:
    """Só os dígitos da célula, que é como CPF e CNPJ são comparados daqui para frente."""
    return ''.join(caractere for caractere in texto_da_celula(valor) if caractere.isdigit())


def para_decimal(valor: Any) -> Decimal:
    """Converte um valor monetário aceitando tanto ``1.234,56`` quanto ``1234.56``."""
    bruto = texto_da_celula(valor).replace('R$', '').replace(' ', '')
    if not bruto:
        raise InvalidOperation
    if ',' in bruto:
        bruto = bruto.replace('.', '').replace(',', '.')
    return Decimal(bruto)


FORMATOS_DATA = ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%Y')


def para_data(valor: Any) -> date:
    """Converte a célula em data, aceitando os formatos usuais de planilha."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    bruto = texto_da_celula(valor)
    if not bruto:
        raise ValueError('data vazia')
    # O Excel entrega datas como "2024-03-20 00:00:00" quando a célula é do tipo data.
    bruto = bruto.split(' ')[0]
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(bruto, formato).date()
        except ValueError:
            continue
    raise ValueError(bruto)


def eh_cnpj(documento: str) -> bool:
    """Distingue CNPJ (14 dígitos) de CPF (11 dígitos) pelo tamanho."""
    return len(so_digitos(documento)) == 14


def detectar_separador(amostra: str) -> str:
    """Separador do CSV deduzido da amostra; ponto e vírgula quando não dá para saber, que é o que o Excel em pt-BR gera."""
    try:
        return csv.Sniffer().sniff(amostra, delimiters=';,\t').delimiter
    except csv.Error:
        return ';'


def ler_csv(conteudo: bytes) -> pd.DataFrame:
    """
    Lê o CSV tentando as codificações usuais, da mais estrita para a mais tolerante.

    ``latin-1`` fica por último porque aceita qualquer byte: viesse antes, um UTF-8 passaria por
    ele com os acentos trocados em vez de falhar e tentar a codificação certa.
    """
    texto = None
    for codificacao in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValidationError('Não foi possível ler o arquivo. Salve-o como CSV UTF-8 e tente novamente.')
    return pd.read_csv(io.StringIO(texto), sep=detectar_separador(texto[:4096]), dtype=str)


def ler_planilha(arquivo: Any) -> pd.DataFrame:
    """
    Lê o arquivo enviado (``.xlsx``, ``.xls`` ou ``.csv``) em um ``DataFrame`` de texto, com os
    cabeçalhos normalizados. Levanta ``ValidationError`` se ele não puder ser lido ou for vazio.
    """
    nome = (getattr(arquivo, 'name', '') or '').lower()
    arquivo.seek(0)
    conteudo = arquivo.read()
    if not conteudo:
        raise ValidationError('O arquivo enviado está vazio.')

    try:
        if nome.endswith(('.xlsx', '.xlsm', '.xls')):
            planilha = pd.read_excel(io.BytesIO(conteudo), dtype=str)
        else:
            planilha = ler_csv(conteudo)
    except ValidationError:
        raise
    except Exception as erro:
        raise ValidationError(f'Não foi possível interpretar a planilha: {erro}')

    planilha.columns = [texto_da_celula(coluna).replace('﻿', '').lower().replace(' ', '_') for coluna in planilha.columns]
    return planilha


def como_arquivo(conteudo: bytes, nome: str) -> io.BytesIO:
    """
    Reconstrói um arquivo a partir do conteúdo recebido pela task.

    A planilha viaja como bytes, e não como caminho, para que nada precise ser gravado; o nome
    vem junto porque dele sai a extensão que decide entre CSV e Excel.
    """
    arquivo = io.BytesIO(conteudo)
    arquivo.name = nome
    return arquivo


def validar_cabecalho(planilha: pd.DataFrame) -> None:
    """Recusa a planilha sem as colunas obrigatórias — é um defeito do arquivo, não das linhas."""
    faltando = [nome for nome in COLUNAS_OBRIGATORIAS if nome not in planilha.columns]
    if faltando:
        rotulos = ', '.join(COLUNAS_POR_NOME[nome].rotulo for nome in faltando)
        raise ValidationError(f'A planilha está sem as colunas obrigatórias: {rotulos}. Baixe a planilha modelo e use o mesmo cabeçalho.')


class Catalogo:
    """
    Resolve os cadastros referenciados pela planilha, memorizando cada busca: a mesma sigla de
    campus se repete em milhares de linhas e sem cache haveria uma consulta por célula.
    """

    def __init__(self) -> None:
        self.campi: dict[str, UnidadeOrganizacional | None] = {}
        self.categorias: dict[str, CategoriaMaterialPermanente | None] = {}
        self.servidores: dict[str, Servidor | None] = {}
        self.rotulos: dict[int, dict[str, InventarioRotulo]] = {}
        self.pessoas_fisicas: dict[str, PessoaFisica | None] = {}

    def campus(self, sigla: str) -> UnidadeOrganizacional | None:
        chave = sigla.upper()
        if chave not in self.campi:
            self.campi[chave] = UnidadeOrganizacional.objects.suap().filter(sigla__iexact=chave).first()
        return self.campi[chave]

    def categoria(self, codigo: str) -> CategoriaMaterialPermanente | None:
        if codigo not in self.categorias:
            self.categorias[codigo] = CategoriaMaterialPermanente.objects.filter(codigo=codigo).first()
        return self.categorias[codigo]

    def servidor(self, matricula: str) -> Servidor | None:
        if matricula not in self.servidores:
            self.servidores[matricula] = Servidor.objects.filter(matricula=matricula).first()
        return self.servidores[matricula]

    def pessoa_fisica(self, cpf: str) -> PessoaFisica | None:
        """
        Fornecedor PF; o CPF é gravado com máscara na base, daí o ``mask_cpf``.

        A base não tem ``UNIQUE`` em ``cpf`` e acumula duplicatas. Sem ordenação explícita quem
        decide é o ``Meta.ordering`` de ``Pessoa`` (``nome``), que empata entre homônimos e troca de
        vencedor a cada renomeação — e a conferência monta seu próprio :class:`Catalogo`, então ela
        poderia mostrar uma pessoa e a gravação pendurar o bem na outra. Vence a mais antiga, como
        no importador do RH (``rh/importador_ws.py``).
        """
        if cpf not in self.pessoas_fisicas:
            self.pessoas_fisicas[cpf] = PessoaFisica.objects.filter(Q(cpf=mask_cpf(cpf)) | Q(cpf=cpf)).order_by('pk').first()
        return self.pessoas_fisicas[cpf]

    def rotulo(self, campus: UnidadeOrganizacional, nome: str) -> InventarioRotulo | None:
        """Rótulo do campus com esse nome, ou ``None`` quando ainda não existe."""
        return self.indice_de_rotulos(campus).get(chave_de_nome(nome))

    def guardar_rotulo(self, campus: UnidadeOrganizacional, rotulo: InventarioRotulo) -> None:
        """Registra no índice um rótulo recém-criado, para a próxima linha reaproveitá-lo."""
        self.indice_de_rotulos(campus)[chave_de_nome(rotulo.nome)] = rotulo

    def indice_de_rotulos(self, campus: UnidadeOrganizacional) -> dict[str, InventarioRotulo]:
        """
        Rótulos do campus indexados pelo nome normalizado.

        A comparação é em Python, e não no banco, porque nome de rótulo é texto livre: espaço e
        acento inconsistentes fariam um ``iexact`` criar um duplicado a cada migração. Havendo
        homônimos no campus, a ordem por ``pk`` faz valer o mais antigo, sempre o mesmo.
        """
        if campus.pk not in self.rotulos:
            indice: dict[str, InventarioRotulo] = {}
            for rotulo in InventarioRotulo.objects.filter(unidade_organizacional=campus).order_by('pk'):
                indice.setdefault(chave_de_nome(rotulo.nome), rotulo)
            self.rotulos[campus.pk] = indice
        return self.rotulos[campus.pk]


class LeitorLinha:
    """Converte uma linha crua da planilha em :class:`LinhaBem`, acumulando os erros achados."""

    def __init__(self, dados: dict[str, Any], numero: int, catalogo: Catalogo) -> None:
        self.dados = dados
        self.numero = numero
        self.catalogo = catalogo
        self.erros: list[Ocorrencia] = []
        self.avisos: list[Ocorrencia] = []

    def registrar_erro(self, coluna: str, mensagem: str) -> None:
        self.erros.append(Ocorrencia(self.numero, coluna, mensagem))

    def registrar_aviso(self, coluna: str, mensagem: str) -> None:
        self.avisos.append(Ocorrencia(self.numero, coluna, mensagem))

    def rotulo_da_coluna(self, coluna: str) -> str:
        return COLUNAS_POR_NOME[coluna].rotulo

    def celula(self, coluna: str) -> str:
        """
        Texto da célula, com erro registrado quando não cabe no campo que vai recebê-lo.

        O valor volta inteiro mesmo assim: a linha com erro é descartada por :meth:`ler`, e
        devolver vazio faria :meth:`exigir` acusar a mesma célula duas vezes.
        """
        valor = texto_da_celula(self.dados.get(coluna))
        limite = COLUNAS_POR_NOME[coluna].limite
        if limite and len(valor) > limite:
            self.registrar_erro(coluna, f'{self.rotulo_da_coluna(coluna)} tem {len(valor)} caracteres; o limite é {limite}.')
        return valor

    def exigir(self, coluna: str) -> str:
        valor = self.celula(coluna)
        if not valor:
            self.registrar_erro(coluna, f'{self.rotulo_da_coluna(coluna)} é obrigatório.')
        return valor

    def campus(self) -> UnidadeOrganizacional | None:
        sigla = self.exigir('campus_sigla')
        if not sigla:
            return None
        campus = self.catalogo.campus(sigla)
        if not campus:
            self.registrar_erro('campus_sigla', f'Campus "{sigla}" não encontrado.')
        return campus

    def categoria(self) -> CategoriaMaterialPermanente | None:
        codigo = self.exigir('elemento_despesa_codigo')
        if not codigo:
            return None
        categoria = self.catalogo.categoria(codigo)
        if not categoria:
            self.registrar_erro('elemento_despesa_codigo', f'Elemento de despesa "{codigo}" não cadastrado.')
        return categoria

    def empenho_numero(self) -> str:
        """
        Número do empenho, que pode vir vazio: a coluna é obrigatória no cabeçalho, e a célula em
        branco é o que marca o bem como doação. O fornecedor sustenta a linha nos dois casos.
        """
        return self.celula('empenho_numero').upper()

    def fornecedor_documento(self) -> str:
        """
        CPF ou CNPJ do fornecedor, obrigatório sempre — na doação é ele que diz de onde o bem veio.

        Ausente da base, a pessoa é criada na migração (a física como pessoa externa, ver
        :meth:`Executor.vinculo_pessoa_fisica`); daí a validação aqui, porque um CPF errado
        viraria uma pessoa fantasma permanente no cadastro global.
        """
        documento = so_digitos(self.exigir('fornecedor_documento'))
        if not documento:
            return ''
        if not cpfcnpj.validate(documento):
            self.registrar_erro('fornecedor_documento', f'CPF/CNPJ "{documento}" é inválido.')
            return ''
        return documento

    def valor(self) -> Decimal | None:
        bruto = self.exigir('valor')
        if not bruto:
            return None
        try:
            valor = para_decimal(bruto)
        except InvalidOperation, ValueError:
            self.registrar_erro('valor', f'Valor Unitário "{bruto}" não é um número válido.')
            return None
        if valor <= 0:
            self.registrar_erro('valor', 'Valor Unitário deve ser maior que zero.')
            return None
        if valor >= LIMITE_VALOR:
            self.registrar_erro('valor', f'Valor Unitário "{bruto}" é grande demais; o máximo é R$ 999.999.999,99.')
            return None
        return valor

    def data(self, coluna: str, *, obrigatoria: bool) -> date | None:
        bruto = self.exigir(coluna) if obrigatoria else self.celula(coluna)
        if not bruto:
            return None
        try:
            return para_data(bruto)
        except ValueError:
            self.registrar_erro(coluna, f'{self.rotulo_da_coluna(coluna)} "{bruto}" não é uma data válida (use dd/mm/aaaa).')
            return None

    def estado_conservacao(self) -> str:
        bruto = self.celula('estado_conservacao').lower()
        if not bruto:
            return Inventario.CONSERVACAO_BOM
        if bruto not in ESTADOS_CONSERVACAO:
            self.registrar_erro('estado_conservacao', f'Estado de Conservação "{bruto}" é inválido. Use: {", ".join(ESTADOS_CONSERVACAO)}.')
            return Inventario.CONSERVACAO_BOM
        return bruto

    def servidor(self, campus: UnidadeOrganizacional | None) -> Servidor | None:
        """Responsável pela carga. Vazio é o caso legítimo do bem que entra pendente."""
        matricula = self.celula('responsavel_matricula')
        if not matricula:
            return None
        servidor = self.catalogo.servidor(matricula)
        if not servidor:
            self.registrar_erro('responsavel_matricula', f'Servidor de matrícula "{matricula}" não encontrado.')
            return None
        if not servidor.setor:
            self.registrar_erro('responsavel_matricula', f'O servidor {servidor.matricula} não tem setor e por isso não pode receber carga.')
            return None
        if campus and servidor.setor.uo_id != campus.pk:
            self.registrar_aviso(
                'responsavel_matricula', f'O servidor {servidor.matricula} é lotado em {servidor.setor.uo} — a carga sairá do campus da entrada.'
            )
        return servidor

    def rotulo_nome(self) -> str:
        """
        A sala da planilha vira rótulo, não sala do inventário: o nome vem do sistema antigo e não
        casa com o cadastro de salas do SUAP. Como rótulo o texto entra como veio — só o tamanho
        é conferido —, e o campo Sala fica vazio para receber depois o cadastro certo.
        """
        return self.celula('sala_nome')

    def ler(self) -> LinhaBem | None:
        """
        Devolve a linha convertida, ou ``None`` quando ela tem qualquer erro.

        A linha inteira é lida antes de ser descartada, e não até o primeiro problema, para o
        usuário corrigir de uma vez tudo o que está errado nela.
        """
        campus = self.campus()
        categoria = self.categoria()
        valor = self.valor()
        entrada_data = self.data('entrada_data', obrigatoria=True)
        empenho_numero = self.empenho_numero()
        fornecedor_documento = self.fornecedor_documento()
        fornecedor_nome = self.exigir('fornecedor_nome')
        nota_fiscal_numero = self.celula('nota_fiscal_numero')
        nota_fiscal_data = self.data('nota_fiscal_data', obrigatoria=False)
        descricao = self.exigir('descricao')
        numero_serie = self.celula('numero_serie')
        estado_conservacao = self.estado_conservacao()
        observacao = self.celula('observação')
        servidor = self.servidor(campus)
        rotulo_nome = self.rotulo_nome()

        # Os quatro campos indispensáveis só voltam vazios tendo registrado erro; conferi-los aqui
        # dispensa marcar cada um como exceção de tipagem na montagem.
        if self.erros or not (campus and categoria and valor and entrada_data):
            return None

        return LinhaBem(
            numero=self.numero,
            campus=campus,
            empenho_numero=empenho_numero,
            fornecedor_documento=fornecedor_documento,
            fornecedor_nome=fornecedor_nome,
            nota_fiscal_numero=nota_fiscal_numero,
            nota_fiscal_data=nota_fiscal_data,
            entrada_data=entrada_data,
            categoria=categoria,
            descricao=descricao,
            valor=valor,
            numero_serie=numero_serie,
            estado_conservacao=estado_conservacao,
            observacao=observacao,
            servidor=servidor,
            rotulo_nome=rotulo_nome,
        )


def linha_vazia(dados: dict[str, Any]) -> bool:
    """Linha em branco no meio da planilha, que é pulada em vez de virar uma enxurrada de erros."""
    return not any(texto_da_celula(valor) for valor in dados.values())


def agrupar_por(linhas: list[LinhaBem], chave: Callable[[LinhaBem], Any]) -> dict[Any, list[LinhaBem]]:
    """
    Agrupa as linhas pela chave dada, descartando as que devolvem ``None`` — é o que tira a doação
    do agrupamento por empenho e o bem sem responsável do de carga, sem filtrar a lista antes.
    """
    grupos: dict[Any, list[LinhaBem]] = defaultdict(list)
    for linha in linhas:
        valor = chave(linha)
        if valor is not None:
            grupos[valor].append(linha)
    return grupos


def cadastros_campi(linhas: list[LinhaBem]) -> list[Cadastro]:
    """Campi atingidos. Não há o que criar: campus que não existe já é erro na leitura da linha."""
    grupos = agrupar_por(linhas, lambda linha: linha.campus.pk)
    return [Cadastro('Campus', grupo[0].campus.sigla, str(grupo[0].campus), EXISTENTE, linhas=len(grupo)) for grupo in grupos.values()]


def cadastros_elementos_despesa(linhas: list[LinhaBem]) -> list[Cadastro]:
    """
    Elementos de despesa referenciados.

    Um elemento sem plano de contas passa na importação e só quebra depois, nos relatórios
    contábeis e na baixa, que leem ``categoria.plano_contas.codigo`` sem checar nulo.
    """
    cadastros = []
    for grupo in agrupar_por(linhas, lambda linha: linha.categoria.pk).values():
        categoria = grupo[0].categoria
        ressalvas = []
        if not categoria.plano_contas_id:
            ressalvas.append('sem plano de contas — vai faltar nos relatórios contábeis')
        elif not categoria.plano_contas.ativo:
            ressalvas.append(f'plano de contas {categoria.plano_contas.codigo} está inativo')
        if categoria.omitir:
            ressalvas.append('marcado como omitido')
        cadastros.append(
            Cadastro(
                tipo='Elemento de Despesa',
                identificacao=categoria.codigo,
                descricao=categoria.nome,
                situacao=ATENCAO if ressalvas else EXISTENTE,
                detalhe='; '.join(ressalvas),
                url=f'/admin/patrimonio/categoriamaterialpermanente/{categoria.pk}/change/',
                linhas=len(grupo),
            )
        )
    return cadastros


def documento_do_vinculo(vinculo: Any) -> str:
    """CPF ou CNPJ por trás de um vínculo de fornecedor, somente dígitos."""
    pessoa = getattr(vinculo, 'pessoa', None)
    if not pessoa:
        return ''
    if hasattr(pessoa, 'pessoajuridica'):
        return so_digitos(pessoa.pessoajuridica.cnpj)
    if hasattr(pessoa, 'pessoafisica'):
        return so_digitos(pessoa.pessoafisica.cpf)
    return ''


def conflito_de_empenho(empenho: Empenho, linha: LinhaBem) -> tuple[str, bool]:
    """
    Divergências entre o empenho já cadastrado e o que a planilha descreve: a mensagem (vazia se
    não houver) e se ela impede a migração.
    """
    if empenho.tipo_material != MaterialTipo.PERMANENTE():
        return f'já existe e é de material de {empenho.tipo_material} — anexar bens permanentes a ele corromperia o empenho', True
    documento_atual = documento_do_vinculo(empenho.vinculo_fornecedor)
    if documento_atual and documento_atual != linha.fornecedor_documento:
        return f'já existe com outro fornecedor ({empenho.vinculo_fornecedor})', False
    return '', False


def divergencia_de_fornecedor(grupo: list[LinhaBem]) -> Ocorrencia | None:
    """
    Fornecedores distintos entre as linhas de um mesmo empenho — sempre defeito da planilha.

    ``Empenho.vinculo_fornecedor`` é um só, e sem esta checagem a migração gravaria o da primeira
    linha do grupo em silêncio. O mesmo valeria para a ``Entrada``, que na compra agrupa por
    empenho, nota e data, sem o fornecedor na chave.

    Bloquear aqui também é o que torna correta a comparação contra o cadastro do SUAP feita em
    :func:`conflito_de_empenho`, que olha só a primeira linha: sem divergência interna, o grupo é
    homogêneo e a primeira linha representa todas.
    """
    documentos = sorted({linha.fornecedor_documento for linha in grupo})
    if len(documentos) < 2:
        return None
    # Ancorada na primeira linha que destoa, e não na do grupo: é essa que o usuário precisa abrir.
    destoante = next(linha for linha in grupo if linha.fornecedor_documento != grupo[0].fornecedor_documento)
    return Ocorrencia(
        destoante.numero,
        'fornecedor_documento',
        f'O empenho {grupo[0].empenho_numero} aparece na planilha com {len(documentos)} fornecedores diferentes '
        f'({", ".join(documentos)}); um empenho tem um fornecedor só.',
    )


def cadastros_empenhos(linhas: list[LinhaBem], erros: list[Ocorrencia]) -> list[Cadastro]:
    """
    Empenhos referenciados: quais já existem no SUAP e quais a migração vai abrir.

    Reaproveitar um empenho existente costuma ser o desejado, mas colidir com um de consumo não:
    ``Empenho`` é único por campus + número, e pendurar permanente nele o corromperia — vira erro
    bloqueante.
    """
    cadastros = []
    for grupo in agrupar_por(linhas, lambda linha: linha.chave_empenho).values():
        primeira = grupo[0]
        divergencia = divergencia_de_fornecedor(grupo)
        if divergencia:
            erros.append(divergencia)
        empenho = Empenho.objects.filter(uo=primeira.campus, numero=primeira.empenho_numero).select_related('vinculo_fornecedor').first()
        if not empenho:
            cadastros.append(
                Cadastro('Empenho', primeira.empenho_numero, f'{primeira.campus.sigla} — será aberto pela migração', SERA_CRIADO, linhas=len(grupo))
            )
            continue

        conflito, bloqueante = conflito_de_empenho(empenho, primeira)
        if bloqueante:
            erros.append(Ocorrencia(primeira.numero, 'empenho_numero', f'O empenho {primeira.empenho_numero} {conflito}.'))
        itens = empenho.empenhopermanente_set.count()
        cadastros.append(
            Cadastro(
                tipo='Empenho',
                identificacao=primeira.empenho_numero,
                descricao=f'{primeira.campus.sigla} — {itens} item(ns) já cadastrado(s)',
                situacao=ATENCAO if conflito else EXISTENTE,
                detalhe=conflito or 'a migração vai acrescentar itens a este empenho',
                url=empenho.get_absolute_url(),
                linhas=len(grupo),
            )
        )
    return cadastros


def cadastros_fornecedores(linhas: list[LinhaBem], catalogo: Catalogo) -> list[Cadastro]:
    """
    Fornecedores citados, procurados pelo CNPJ (PJ) ou pelo CPF (PF).

    Quem falta a migração cadastra. Nome divergente não bloqueia — o cadastro do SUAP prevalece —,
    mas vira atenção: pode ser a planilha apontando para outra empresa.
    """
    cadastros = []
    for grupo in agrupar_por(linhas, chave_de_fornecedor).values():
        documento = grupo[0].fornecedor_documento
        nome = grupo[0].fornecedor_nome
        if eh_cnpj(documento):
            pessoa = PessoaJuridica.objects.filter(Q(cnpj=documento) | Q(matricula=documento)).first()
            rotulo, tipo = 'CNPJ', 'Fornecedor (PJ)'
        else:
            pessoa = catalogo.pessoa_fisica(documento)
            rotulo, tipo = 'CPF', 'Fornecedor (PF)'
        if not pessoa:
            # A pessoa física entra como pessoa externa, cadastro que o RH passa a enxergar.
            detalhe = '' if eh_cnpj(documento) else 'será cadastrado como pessoa externa, sem acesso ao SUAP'
            cadastros.append(Cadastro(tipo, f'{rotulo} {documento}', f'{nome} — será cadastrado', SERA_CRIADO, detalhe=detalhe, linhas=len(grupo)))
            continue
        divergente = texto_da_celula(pessoa.nome).upper() != nome.upper()
        cadastros.append(
            Cadastro(
                tipo=tipo,
                identificacao=f'{rotulo} {documento}',
                descricao=pessoa.nome,
                situacao=ATENCAO if divergente else EXISTENTE,
                detalhe=f'a planilha traz "{nome}"; o cadastro do SUAP prevalece' if divergente else '',
                url=pessoa.get_absolute_url(),
                linhas=len(grupo),
            )
        )
    return cadastros


def cadastros_responsaveis(linhas: list[LinhaBem]) -> list[Cadastro]:
    """
    Servidores que receberão carga.

    Inativo ou em situação que não admite transferência não impede a migração (o SUAP já convive
    com isso), mas é o que a coordenação vai querer regularizar depois.
    """
    aptos = set(Inventario.get_servidores_disponivel_transferencia().values_list('pk', flat=True))
    cadastros = []
    for grupo in agrupar_por(linhas, chave_de_servidor).values():
        servidor = grupo[0].servidor
        ressalvas = []
        if not servidor.ativo:
            ressalvas.append('servidor inativo')
        elif servidor.pk not in aptos:
            ressalvas.append(f'situação "{servidor.situacao}" não consta entre as que admitem transferência de carga')
        cadastros.append(
            Cadastro(
                tipo='Responsável',
                identificacao=servidor.matricula,
                descricao=f'{servidor} ({servidor.setor})',
                situacao=ATENCAO if ressalvas else EXISTENTE,
                detalhe='; '.join(ressalvas),
                url=servidor.get_absolute_url(),
                linhas=len(grupo),
            )
        )
    return cadastros


def cadastros_rotulos(linhas: list[LinhaBem], catalogo: Catalogo) -> list[Cadastro]:
    """
    Rótulos que a planilha cria ou reaproveita, um por sala citada.

    A migração cria o que faltar; o levantamento mostra quantos rótulos novos vão nascer — mil
    grafias diferentes da mesma sala viram mil rótulos, e é melhor descobrir na conferência.
    """
    cadastros = []
    for grupo in agrupar_por(linhas, chave_de_rotulo).values():
        primeira = grupo[0]
        existente = catalogo.rotulo(primeira.campus, primeira.rotulo_nome)
        cadastros.append(
            Cadastro(
                tipo='Rótulo',
                identificacao=primeira.rotulo_nome,
                descricao=(f'{primeira.campus.sigla} — {existente.nome}' if existente else f'{primeira.campus.sigla} — será criado pela migração'),
                situacao=EXISTENTE if existente else SERA_CRIADO,
                linhas=len(grupo),
            )
        )
    return cadastros


def cadastros_notas_fiscais(linhas: list[LinhaBem], avisos: list[Ocorrencia]) -> list[Cadastro]:
    """
    Notas fiscais que já entraram no SUAP — o sinal mais confiável de reimportação acidental.

    Avisa, e não bloqueia: a migração legítima pode trazer de novo uma nota que já deu entrada,
    e a nota ganha então uma entrada nova. Mas uma reimportação acidental duplica o acervo em
    tombos novos, com carga contábil e movimento, e desfazer isso é desmontar o livro patrimonial
    à mão — por isso a conferência mostra a entrada existente antes de o operador confirmar.
    """
    cadastros = []
    for grupo in agrupar_por(linhas, chave_de_nota_fiscal).values():
        primeira = grupo[0]
        existente = Entrada.objects.filter(
            uo=primeira.campus, numero_nota_fiscal=primeira.nota_fiscal_numero, tipo_material=MaterialTipo.PERMANENTE()
        ).first()
        if not existente:
            continue
        avisos.append(
            Ocorrencia(
                primeira.numero,
                'nota_fiscal_numero',
                f'A nota fiscal {primeira.nota_fiscal_numero} já deu entrada em {primeira.campus.sigla} '
                f'(entrada #{existente.pk}, de {existente.data:%d/%m/%Y}); se for reimportação, os bens serão duplicados.',
            )
        )
        cadastros.append(
            Cadastro(
                tipo='Nota Fiscal',
                identificacao=primeira.nota_fiscal_numero,
                descricao=f'{primeira.campus.sigla} — entrada #{existente.pk} de {existente.data:%d/%m/%Y}',
                situacao=ATENCAO,
                detalhe='esta nota já deu entrada neste campus; se for reimportação, os bens serão duplicados',
                url=existente.get_absolute_url(),
                linhas=len(grupo),
            )
        )
    return cadastros


def inventariar_cadastros(linhas: list[LinhaBem], catalogo: Catalogo, erros: list[Ocorrencia], avisos: list[Ocorrencia]) -> list[Cadastro]:
    """Levanta todos os cadastros que a planilha referencia e o que será feito com cada um."""
    return [
        *cadastros_campi(linhas),
        *cadastros_elementos_despesa(linhas),
        *cadastros_empenhos(linhas, erros),
        *cadastros_fornecedores(linhas, catalogo),
        *cadastros_responsaveis(linhas),
        *cadastros_rotulos(linhas, catalogo),
        *cadastros_notas_fiscais(linhas, avisos),
    ]


def conferir(arquivo: Any) -> Conferencia:
    """
    Lê e valida a planilha inteira sem gravar nada, devolvendo a :class:`Conferencia` com as
    linhas válidas, os erros, os avisos e os cadastros referenciados.

    Levanta ``ValidationError`` quando o defeito é do arquivo como um todo (ilegível ou sem as
    colunas obrigatórias), que não faz sentido reportar por linha.
    """
    planilha = ler_planilha(arquivo)
    validar_cabecalho(planilha)
    conferencia = Conferencia()
    catalogo = Catalogo()
    for indice, dados in enumerate(planilha.to_dict('records')):
        if linha_vazia(dados):
            continue
        # +2 porque a planilha tem cabeçalho e o usuário conta a partir de 1.
        leitor = LeitorLinha(dados, indice + 2, catalogo)
        linha = leitor.ler()
        conferencia.erros.extend(leitor.erros)
        conferencia.avisos.extend(leitor.avisos)
        if linha:
            conferencia.linhas.append(linha)

    if not conferencia.linhas and not conferencia.erros:
        raise ValidationError('A planilha não tem nenhuma linha preenchida.')

    # Uma consulta por cadastro distinto, não por linha; pode acrescentar erros bloqueantes e avisos.
    conferencia.cadastros = inventariar_cadastros(conferencia.linhas, catalogo, conferencia.erros, conferencia.avisos)
    return conferencia


def vinculo_de_fornecedor(pessoa: PessoaFisica) -> Vinculo:
    """
    Vínculo pelo qual a pessoa física figura como fornecedora: o existente mais relevante (ativo
    primeiro) ou um de pessoa externa recém-criado.

    A consulta é direto na relação com ``Vinculo``, e não por ``PessoaFisica.get_vinculo()``,
    porque aquele método estoura ``AttributeError`` no caso que interessa aqui — pessoa sem papel
    algum, em que ele cai no ramo ``self.user``, atributo que ``PessoaFisica`` não tem.
    """
    return pessoa.vinculo_set.order_by('-ativo', 'pk').first() or criar_pessoa_externa(pessoa=pessoa)


def espelhar_pessoa_fisica(externa: PessoaExterna, pessoa: PessoaFisica) -> None:
    """
    Copia para a pessoa externa os dados que a pessoa física já tem.

    ``PessoaExterna.save()`` empurra o próprio ``__dict__`` para dentro da ``PessoaFisica`` com um
    ``update()``: anexar uma externa recém-instanciada a quem já está na base apagaria RG, nome da
    mãe, nascimento e dados bancários. Espelhar antes torna esse ``update()`` inócuo.
    """
    campos_da_pessoa = {campo.attname for campo in pessoa._meta.concrete_fields}
    for campo in externa._meta.concrete_fields:
        if campo.attname in campos_da_pessoa and campo.attname != 'id':
            setattr(externa, campo.attname, getattr(pessoa, campo.attname))


def criar_pessoa_externa(pessoa: PessoaFisica | None = None, cpf: str = '', nome: str = '') -> Vinculo:
    """
    Cria o vínculo de pessoa externa do fornecedor (``cpf`` e ``nome`` só valem quando a pessoa
    ainda não existe).

    ``PessoaExterna`` é o papel de quem se relaciona com a instituição sem ser dela, o mesmo
    caminho que ``frota``, ``ae`` e ``pesquisa`` usam. O ``save()`` dela cria a ``PessoaFisica``
    quando não há uma, cria o ``Vinculo`` com ``ativo=False`` e **não cria conta de usuário** —
    ao contrário de ``PrestadorServico``: migrar patrimônio não distribui acesso ao SUAP.
    """
    externa = PessoaExterna(cpf=cpf, nome=nome)
    if pessoa:
        espelhar_pessoa_fisica(externa, pessoa)
        externa.pessoa_fisica = pessoa
    externa.save()

    vinculo = externa.get_vinculo()
    if not vinculo:
        raise ValidationError(f'Não foi possível criar o vínculo do fornecedor {externa.nome} (CPF {externa.cpf}).')
    return vinculo


PESO_ITENS = 70
"""Fatia da barra de progresso gasta criando os itens — a fase que gera um inventário por bem."""

PESO_CARGAS = 25
"""Fatia gasta nas requisições de carga; o que sobra cobre a atualização dos empenhos no fim."""


class Executor:
    """
    Grava a cadeia patrimonial a partir de uma conferência válida.

    É classe para que os cadastros criados (empenhos, entradas, fornecedores) sejam reaproveitados
    entre as linhas sem passar meia dúzia de dicionários adiante.
    """

    def __init__(self, conferencia: Conferencia, user: User, processo: Any = None, task: Any = None) -> None:
        self.conferencia = conferencia
        self.user = user
        self.processo = processo
        self.task = task
        self.catalogo = Catalogo()
        self.fornecedores: dict[str, Vinculo | None] = {}
        self.empenhos: dict[tuple[int, str], Empenho] = {}
        self.entradas: dict[tuple[Any, ...], Entrada] = {}
        self.inventarios_por_linha: dict[int, Inventario] = {}

    def fornecedor(self, documento: str, nome: str) -> Vinculo | None:
        """
        Vínculo do fornecedor (``documento`` só com dígitos), criando a pessoa ausente da base.

        Devolve ``None`` quando a pessoa não tem vínculo no SUAP.
        """
        if documento in self.fornecedores:
            return self.fornecedores[documento]

        if eh_cnpj(documento):
            vinculo = self.pessoa_juridica(documento, nome).get_vinculo()
        else:
            vinculo = self.vinculo_pessoa_fisica(documento, nome)
        self.fornecedores[documento] = vinculo
        return vinculo

    @staticmethod
    def pessoa_juridica(cnpj: str, nome: str) -> PessoaJuridica:
        """
        Fornecedor PJ, criado quando o CNPJ ainda não está na base.

        A busca cobre o CNPJ com e sem máscara e a ``matricula``, que ``PessoaJuridica.save()``
        grava só com dígitos.
        """
        pessoa_juridica = PessoaJuridica.objects.filter(Q(cnpj=cnpj) | Q(cnpj=mask_cnpj(cnpj)) | Q(matricula=cnpj)).first()
        if pessoa_juridica:
            return pessoa_juridica
        # PessoaJuridica.save() valida o CNPJ, deriva a matrícula e cria o Vinculo.
        return PessoaJuridica.objects.create(cnpj=cnpj, nome=nome, nome_registro=nome, nome_fantasia=nome)

    def vinculo_pessoa_fisica(self, cpf: str, nome: str) -> Vinculo:
        """
        Vínculo do fornecedor PF (``cpf`` só com dígitos), cadastrando-a quando ela não existe.

        Diferente da PJ, a pessoa física sozinha não serve de fornecedor: o empenho aponta para um
        ``Vinculo``, e ``PessoaFisica`` só tem vínculo através de um papel — daí a pessoa externa.
        """
        pessoa = self.catalogo.pessoa_fisica(cpf)
        if pessoa:
            return vinculo_de_fornecedor(pessoa)
        # O CPF é gravado com máscara na base, como no cadastro normal de pessoas.
        return criar_pessoa_externa(cpf=mask_cpf(cpf), nome=nome)

    def empenho(self, linha: LinhaBem) -> Empenho:
        """Empenho da linha, reaproveitando o que já existir no SUAP (único por campus + número)."""
        chave = linha.chave_empenho
        if chave in self.empenhos:
            return self.empenhos[chave]

        fornecedor = self.fornecedor(linha.fornecedor_documento, linha.fornecedor_nome)
        empenho, _ = Empenho.objects.get_or_create(
            uo=linha.campus,
            numero=linha.empenho_numero,
            defaults={
                'vinculo_fornecedor': fornecedor,
                'tipo_material': MaterialTipo.PERMANENTE(),
                'processo': self.processo,
                'observacao': marcador_de_origem(),
            },
        )
        self.empenhos[chave] = empenho
        return empenho

    def entrada(self, linha: LinhaBem) -> Entrada:
        """
        Entrada da linha — uma por nota fiscal (ou por data, quando a nota não veio).

        O tipo sai do empenho, e a distinção não é cosmética: ``Inventario.save()`` só busca a UO
        pelo empenho quando a entrada é de compra, então doação marcada como compra estouraria.
        """
        chave = linha.chave_entrada
        if chave in self.entradas:
            return self.entradas[chave]

        entrada = Entrada.objects.create(
            uo=linha.campus,
            data=linha.entrada_data,
            tipo_entrada=EntradaTipo.DOACAO() if linha.eh_doacao else EntradaTipo.COMPRA(),
            tipo_material=MaterialTipo.PERMANENTE(),
            numero_nota_fiscal=linha.nota_fiscal_numero or None,
            data_nota_fiscal=linha.nota_fiscal_data,
            vinculo_fornecedor=self.fornecedor(linha.fornecedor_documento, linha.fornecedor_nome),
            processo=self.processo,
        )
        self.entradas[chave] = entrada
        return entrada

    def rotulo(self, linha: LinhaBem) -> InventarioRotulo:
        """
        Rótulo do campus com o nome que veio na coluna Sala, criado se ainda não existir.

        A ``unidade_organizacional`` é informada na mão porque o ``default=get_uo`` lê o
        thread-local da requisição: no worker está vazio, e o campus certo é o da linha.
        """
        existente = self.catalogo.rotulo(linha.campus, linha.rotulo_nome)
        if existente:
            return existente
        criado = InventarioRotulo.objects.create(
            nome=linha.rotulo_nome,
            descricao=marcador_de_origem(),
            unidade_organizacional=linha.campus,
        )
        # Sem guardar no catálogo, a próxima linha com a mesma sala criaria um rótulo repetido.
        self.catalogo.guardar_rotulo(linha.campus, criado)
        return criado

    def item_empenhado(self, referencia: LinhaBem, quantidade: int) -> EmpenhoPermanente | None:
        """
        Item de empenho do grupo (``referencia`` é a primeira linha), ou ``None`` na doação.

        Doação não tem empenho a que se pendurar, e ``EntradaPermanente.empenho_permanente`` é
        nulo justamente para isso — é o que a tela de Entrada de Doação também grava.
        """
        if referencia.eh_doacao:
            return None
        return EmpenhoPermanente.objects.create(
            empenho=self.empenho(referencia),
            categoria=referencia.categoria,
            descricao=referencia.descricao,
            # A migração registra bens já recebidos: empenhado e adquirido nascem iguais.
            qtd_empenhada=quantidade,
            qtd_adquirida=quantidade,
            valor=referencia.valor,
        )

    def criar_item(self, linhas: list[LinhaBem]) -> None:
        """
        Cria o item de empenho (quando há) e o item de entrada de um grupo de bens idênticos.

        Bens de mesma entrada, elemento, descrição e valor formam um item de quantidade N; o
        ``EntradaPermanente.save()`` gera os N inventários, já com carga contábil e movimento de
        pendência, e aqui só emparelhamos cada um com a sua linha.
        """
        referencia = linhas[0]
        quantidade = len(linhas)
        empenho_permanente = self.item_empenhado(referencia, quantidade)
        entrada_permanente = EntradaPermanente(
            entrada=self.entrada(referencia),
            empenho_permanente=empenho_permanente,
            categoria=referencia.categoria,
            descricao=referencia.descricao,
            # `int` porque EntradaPermanente.save() usa a quantidade em range().
            qtd=quantidade,
            valor=referencia.valor,
        )
        entrada_permanente.save(user=self.user)

        gerados = list(entrada_permanente.inventario_set.order_by('numero'))
        por_rotulo: dict[InventarioRotulo, list[Inventario]] = defaultdict(list)
        for linha, inventario in zip(linhas, gerados, strict=True):
            inventario.observacao = linha.observacao
            inventario.numero_serie = linha.numero_serie
            inventario.estado_conservacao = linha.estado_conservacao
            self.inventarios_por_linha[linha.numero] = inventario
            if linha.rotulo_nome:
                por_rotulo[self.rotulo(linha)].append(inventario)
        # A sala fica de fora de propósito: a localização que veio na planilha virou rótulo.
        Inventario.objects.bulk_update(gerados, ['observacao', 'numero_serie', 'estado_conservacao'])

        for rotulo, inventarios in por_rotulo.items():
            # Um `add` por rótulo, e não por bem: cada chamada vira um único insert na tabela M2M.
            rotulo.inventario_set.add(*inventarios)

    def efetuar_carga(self, servidor: Servidor, campus: UnidadeOrganizacional, linhas: list[LinhaBem]) -> Requisicao:
        """
        Cria a requisição de carga do servidor e já a efetiva.

        Nasce deferida porque a migração registra uma carga que **já existe** no mundo real:
        exigir aceite de cada servidor deixaria todo o acervo pendente. Pelo mesmo motivo não
        passa pelo fluxo de informação de PA, que é para transferência nova entre campi.
        """
        vinculo_operador = self.user.get_vinculo()
        # A conferência recusa servidor sem setor, justamente porque a carga precisa de campus.
        campus_destino = servidor.setor.uo
        requisicao = Requisicao(
            # Primeira carga: não havia responsável anterior de quem o bem saísse.
            vinculo_origem=None,
            campus_origem=campus,
            vinculo_destino=servidor.get_vinculo(),
            campus_destino=campus_destino,
            status=Requisicao.STATUS_DEFERIDA,
            tipo=Requisicao.TIPO_MESMO_CAMPI if campus_destino == campus else Requisicao.TIPO_DIFERENTES_CAMPI,
            vinculo_coordenador=vinculo_operador,
            requisitante=vinculo_operador,
            descricao=marcador_de_origem(),
        )
        # Migração é carga em lote: um e-mail por servidor viraria uma avalanche.
        requisicao.notificar_destino = False
        requisicao.save()
        RequisicaoHistorico.objects.create(requisicao=requisicao, status=requisicao.status, alterado_em=datetime.now(), alterado_por=self.user)

        itens = RequisicaoItem.objects.bulk_create(
            [
                RequisicaoItem(
                    requisicao=requisicao,
                    inventario=self.inventarios_por_linha[linha.numero],
                    situacao=RequisicaoItem.APROVADO,
                    avaliador=self.user,
                    valor=linha.valor,
                )
                for linha in linhas
            ]
        )
        for item in itens:
            # Gera o movimento de transferência, ativa o inventário e ajusta a carga contábil.
            item.inventario.efetuar_transferencia(self.user, requisicao, item)
        return requisicao

    def agrupar_linhas(self) -> tuple[dict[Any, list[LinhaBem]], dict[Any, list[LinhaBem]]]:
        """
        Reparte as linhas nas duas fases da gravação — itens a criar e cargas a efetuar — numa
        passada só, já que as duas chaves saem da mesma linha.
        """
        itens: dict[Any, list[LinhaBem]] = defaultdict(list)
        cargas: dict[Any, list[LinhaBem]] = defaultdict(list)
        for linha in self.conferencia.linhas:
            itens[linha.chave_item].append(linha)
            chave = chave_de_carga(linha)
            if chave:
                cargas[chave].append(linha)
        return itens, cargas

    def reportar_progresso(self, valor: int) -> None:
        if self.task:
            self.task.update_progress(valor)

    def executar(self) -> dict[str, Any]:
        """Grava tudo e devolve o resumo do que foi criado."""
        itens, cargas = self.agrupar_linhas()
        if self.task:
            self.task.start_progress(100)

        for indice, linhas in enumerate(itens.values(), start=1):
            self.criar_item(linhas)
            self.reportar_progresso(int(PESO_ITENS * indice / len(itens)))

        requisicoes = []
        for indice, linhas in enumerate(cargas.values(), start=1):
            # `chave_de_carga` só agrupa linhas com responsável, então o servidor está garantido.
            requisicoes.append(self.efetuar_carga(linhas[0].servidor, linhas[0].campus, linhas))  # type: ignore[arg-type]
            self.reportar_progresso(PESO_ITENS + int(PESO_CARGAS * indice / len(cargas)))

        for empenho in self.empenhos.values():
            empenho.atualizar_informacoes()
        self.reportar_progresso(100)

        resumo = self.conferencia.resumo()
        resumo['entradas_criadas'] = sorted(entrada.pk for entrada in self.entradas.values())
        resumo['requisicoes_criadas'] = sorted(requisicao.pk for requisicao in requisicoes)
        return resumo


@transaction.atomic
def executar(conferencia: Conferencia, user: User | None, processo: Any = None, task: Any = None) -> dict[str, Any]:
    """
    Grava a cadeia patrimonial de uma conferência já validada e devolve o resumo do que foi criado.

    Tudo em uma única transação: se qualquer linha falhar, nada sobrevive — migração pela metade é
    pior do que migração nenhuma. ``user`` vira o autor dos movimentos e das cargas contábeis;
    ``processo`` é registrado nos empenhos e entradas; ``task`` reporta progresso.
    """
    if not conferencia.valida:
        raise ValidationError('A planilha tem erros e não pode ser migrada.')
    # Sem usuário não há autor dos movimentos nem operador das cargas; falhar aqui é mais claro
    # do que estourar um AttributeError no meio da gravação.
    if user is None:
        raise ValidationError('Não foi possível identificar o usuário que está executando a migração.')
    return Executor(conferencia, user, processo, task).executar()


EXEMPLO_COMPRA: dict[str, str] = {
    'campus_sigla': 'CNAT',
    'empenho_numero': '2024NE800123',
    'fornecedor_documento': '33.000.167/0001-01',
    'fornecedor_nome': 'MOVEIS BRASIL LTDA',
    'nota_fiscal_numero': '4567',
    'nota_fiscal_data': '15/03/2024',
    'entrada_data': '20/03/2024',
    'elemento_despesa_codigo': '449052',
    'descricao': 'Cadeira giratória com braços',
    'valor': '389,90',
    'numero_serie': '',
    'estado_conservacao': 'bom',
    'responsavel_matricula': '1234567',
    'sala_nome': 'Sala 12',
    'observação': 'Tombo antigo: 004521',
}
"""Linha completa: bem comprado por empenho e já entregue a um responsável."""

EXEMPLOS_MODELO: tuple[dict[str, str], ...] = (
    EXEMPLO_COMPRA,
    # Sem responsável: o bem entra pendente, e a carga é feita depois pela tela normal.
    EXEMPLO_COMPRA
    | {
        'responsavel_matricula': '',
        'sala_nome': '',
        'observação': 'Tombo antigo: 004522 - sem responsável, entra pendente',
    },
    # Sem empenho: o bem entra como doação, e o fornecedor da linha passa a ser o doador.
    EXEMPLO_COMPRA
    | {
        'empenho_numero': '',
        'nota_fiscal_numero': '',
        'nota_fiscal_data': '',
        'descricao': 'Mesa de reunião doada',
        'valor': '1.250,00',
        'observação': 'Tombo antigo: 004523 - sem empenho, entra como doação',
    },
)
"""
Uma linha de exemplo por caso que a migração trata de forma diferente; todas partem da mesma e
mudam só o que caracteriza o caso, para o usuário ver qual célula esvaziar ou preencher.
"""


def gerar_planilha_modelo() -> bytes:
    """Monta o ``.xlsx`` modelo: uma aba de exemplo e outra explicando cada coluna."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    planilha = Workbook()
    aba = planilha.worksheets[0]
    aba.title = 'Bens'
    aba.append([coluna.nome for coluna in COLUNAS])
    for exemplo in EXEMPLOS_MODELO:
        aba.append([exemplo[coluna.nome] for coluna in COLUNAS])
    for indice, coluna in enumerate(COLUNAS, start=1):
        aba.cell(row=1, column=indice).font = Font(bold=True)
        aba.column_dimensions[get_column_letter(indice)].width = max(len(coluna.nome) + 4, 18)
    aba.freeze_panes = 'A2'

    dicionario = planilha.create_sheet('Instruções')
    dicionario.append(['Coluna', 'Nome', 'Obrigatória', 'O que informar', 'Exemplo'])
    for coluna in COLUNAS:
        # Coluna condicional é obrigatória na planilha; o que varia é o preenchimento da célula.
        obrigatoriedade = f'Sim ({coluna.condicional})' if coluna.condicional else ('Sim' if coluna.obrigatoria else 'Não')
        dicionario.append([coluna.nome, coluna.rotulo, obrigatoriedade, coluna.instrucao, coluna.exemplo])
    for indice, largura in enumerate((26, 32, 34, 72, 24), start=1):
        dicionario.cell(row=1, column=indice).font = Font(bold=True)
        dicionario.column_dimensions[get_column_letter(indice)].width = largura
    for linha in dicionario.iter_rows(min_row=2, min_col=4, max_col=4):
        linha[0].alignment = Alignment(wrap_text=True, vertical='top')
    dicionario.freeze_panes = 'A2'

    buffer = io.BytesIO()
    planilha.save(buffer)
    return buffer.getvalue()
