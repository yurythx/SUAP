"""Planilhas mínimas no layout em que o Tesouro Gerencial exporta cada relatório importável.

``tesouro_gerencial/importador.py`` lê o arquivo em UTF-16-LE (``ImportacaoTesouroGerencial.processar``)
e acha cada coluna pelo **nome do cabeçalho** (``Importador.get_indice``), não pela posição. Quando a
célula do cabeçalho vem vazia, a coluna herda o nome da anterior com o sufixo `` Nome``
(``Importador.montar_cabecalho``) — é assim que o Tesouro exporta código e descrição lado a lado, e é
assim que estas planilhas o fazem (``_codigo_e_nome``).

O que muda de um relatório para outro, e que cada função aqui reproduz, é o **layout de linhas**: em
que linhas está o cabeçalho (``cabecalho_linhas``), onde começam os dados (``ini_row``), o delimitador
e se a última linha — o total — é descartada (``ignore_last_row``). Cada planilha tem só as linhas de
dados que o teste afirma.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

Colunas = list[tuple[str, str]]

NOME_UG = 'UG DO TESTE E2E'


@dataclass(frozen=True)
class Planilha:
    """Um relatório exportado: a opção do campo "Relatório" da tela e o conteúdo do arquivo."""

    relatorio: str
    nome_arquivo: str
    linhas: list[list[str]]
    delimitador: str = '\t'

    def gravar(self, diretorio: Path) -> Path:
        """Grava em UTF-16-LE **sem BOM**: o importador abre com ``encoding='utf-16-le'``, que não o descarta."""
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=self.delimitador, lineterminator='\n').writerows(self.linhas)
        caminho = diretorio / self.nome_arquivo
        caminho.write_bytes(buffer.getvalue().encode('utf-16-le'))
        return caminho


def _codigo_e_nome(titulo: str, codigo: str, nome: str) -> Colunas:
    """Coluna de código seguida da descrição com cabeçalho vazio — vira ``'<titulo> Nome'`` na leitura."""
    return [(titulo, codigo), ('', nome)]


def _classificacao() -> Colunas:
    """Ação, PTRES, PI, fonte, natureza, subitem e grupo: a classificação comum aos relatórios de execução."""
    return [
        *_codigo_e_nome('Ação Governo', '20RL', 'FUNCIONAMENTO DE INSTITUICOES FEDERAIS'),
        ('PTRES', '231796'),
        *_codigo_e_nome('PI', 'L20RLP0100N', 'FUNCIONAMENTO'),
        *_codigo_e_nome('Fonte Recursos Detalhada', '1000000000', 'RECURSOS ORDINARIOS'),
        *_codigo_e_nome('Natureza Despesa', '339039', 'OUTROS SERVICOS DE TERCEIROS PJ'),
        *_codigo_e_nome('Subitem', '17', 'MANUTENCAO E CONSERV. DE MAQUINAS'),
        *_codigo_e_nome('Grupo Despesa', '3', 'OUTRAS DESPESAS CORRENTES'),
    ]


def _cabecalho(colunas: Colunas) -> list[str]:
    return [titulo for titulo, _ in colunas]


def _valores(colunas: Colunas) -> list[str]:
    return [valor for _, valor in colunas]


def receitas_por_gru(ug: str, gru: str, ano: int, valor: str) -> Planilha:
    """ARRECADAÇÃO POR GRU (``ImportadorGRU``): cabeçalho nas linhas 5 a 7, dados da 8 em diante, tabulação."""
    colunas = [
        *_codigo_e_nome('UG Executora', ug, NOME_UG),
        *_codigo_e_nome('Cód. Recolhimento GRU', gru, 'SERVICOS EDUCACIONAIS'),
        ('Ano Lançamento', str(ano)),
        ('RECEITA ARRECADADA POR GRU', valor),
    ]
    linhas = [['ARRECADAÇÃO POR GRU'], [], [], [], [], _cabecalho(colunas), [], [], _valores(colunas)]
    return Planilha('ARRECADAÇÃO POR GRU', 'receitas_gru.csv', linhas)


def movimentacoes_de_credito(numero: str, ug: str, data: str, valor: str) -> Planilha:
    """Movimentações de crédito (``ImportadorNotaCredito``): cabeçalho na linha 2, dados da 3 em diante, e a
    última linha — o total do relatório — descartada."""
    colunas = [
        ('NC', numero),
        *_codigo_e_nome('Conta Contábil', '622220100', 'CREDITO DISPONIVEL'),
        ('Emissão - Dia', data),
        ('Doc - Observação', 'Descentralização de crédito para funcionamento (e2e)'),
        *_codigo_e_nome('Unidade Orçamentária', '26435', 'INSTITUTO FEDERAL DO RN'),
        *_codigo_e_nome('Emitente - Gestão', '26435', 'INSTITUTO FEDERAL DO RN'),
        *_codigo_e_nome('Emitente - UG', ug, NOME_UG),
        *_codigo_e_nome('Favorecido Doc.', ug, NOME_UG),
        *_codigo_e_nome('Esfera Orçamentária', '1', 'ORCAMENTO FISCAL'),
        *_codigo_e_nome('UG Responsável', ug, NOME_UG),
        *_classificacao(),
        ('Movim. Líquido - R$ (Conta Contábil)', valor),
    ]
    linhas = [['Movimentações de crédito'], [], _cabecalho(colunas), _valores(colunas), ['Total']]
    return Planilha('Movimentações de crédito', 'movimentacoes_credito.csv', linhas)


def restos_a_pagar(numero: str, ug: str, ano: int, liquidado: str) -> Planilha:
    """RAP PROC N PROC INSCRITOS (``ImportadorRAP``): cabeçalho nas linhas 0 a 4, dados da 5 em diante.

    Só o liquidado de "não processados" importa às variáveis (``RAP.get_valor``); os outros valores vão
    zerados, menos o inscrito, para o item não nascer vazio.
    """
    valores_rap = [
        ('RESTOS A PAGAR PROCESSADOS INSCRITOS', '0,00'),
        ('RESTOS A PAGAR PROCESSADOS REINSCRITOS', '0,00'),
        ('RESTOS A PAGAR PROCESSADOS CANCELADOS', '0,00'),
        ('RESTOS A PAGAR PROCESSADOS PAGOS', '0,00'),
        ('RESTOS A PAGAR NAO PROCESSADOS INSCRITOS', '9.000,00'),
        ('RESTOS A PAGAR NAO PROCESSADOS REINSCRITOS', '0,00'),
        ('RESTOS A PAGAR NAO PROCESSADOS CANCELADOS', '0,00'),
        ('RESTOS A PAGAR NAO PROCESSADOS LIQUIDADOS', liquidado),
        ('RESTOS A PAGAR NAO PROCESSADOS PAGOS', liquidado),
    ]
    colunas = [
        *_codigo_e_nome('UG Executora', ug, NOME_UG),
        *_codigo_e_nome('UG Responsável', ug, NOME_UG),
        *_codigo_e_nome('Unidade Orçamentária', '26435', 'INSTITUTO FEDERAL DO RN'),
        ('Ano Lançamento', str(ano)),
        ('NE CCor - Ano Emissão', str(ano - 1)),
        ('NE CCor', numero),
        *_classificacao(),
        *valores_rap,
    ]
    linhas = [_cabecalho(colunas), [], [], [], [], _valores(colunas)]
    return Planilha('RAP PROC N PROC INSCRITOS', 'restos_a_pagar.csv', linhas)


def _linha_de_execucao(empenho: str, documento: str, evento: tuple[str, str], data: str, ug: str, valores: tuple[str, str, str]) -> Colunas:
    """Uma linha do "Exec NE": o documento (RO, NS, OB...) e o empenho a que ele pertence."""
    empenhado, liquidado, pago = valores
    return [
        ('NE CCor', empenho),
        ('NE CCor - Ano Emissão', data[-4:]),
        ('Documento', documento),
        *_codigo_e_nome('Evento', *evento),
        ('Emissão - Dia', data),
        *_codigo_e_nome('Unidade Orçamentária', '26435', 'INSTITUTO FEDERAL DO RN'),
        ('Doc - Observação', 'Manutenção predial, conforme contrato (e2e)'),
        *_codigo_e_nome('NE CCor - Favorecido', '12345678000190', 'EMPRESA DE MANUTENCAO E2E'),
        *_classificacao(),
        *_codigo_e_nome('Esfera Orçamentária', '1', 'ORCAMENTO FISCAL'),
        *_codigo_e_nome('UG Executora', ug, NOME_UG),
        *_codigo_e_nome('UG Responsável', ug, NOME_UG),
        ('DESPESAS EMPENHADAS (CONTROLE EMPENHO)', empenhado),
        ('DESPESAS LIQUIDADAS (CONTROLE EMPENHO)', liquidado),
        ('DESPESAS PAGAS (CONTROLE EMPENHO)', pago),
    ]


def execucao_de_empenhos(numeros: dict[str, str], ug: str, data: str, valores: dict[str, str]) -> Planilha:
    """Exec NE Emitido, Liquidado e Pago (``ImportadorExecNE``): cabeçalho nas linhas 2 a 4, dados da 5 em
    diante, separado por **vírgula** (único dos quatro), daí os valores com vírgula decimal irem entre aspas.

    Desde 2021 o empenho chega pelos registros orçamentários (RO): o importador cria o empenho a partir do
    primeiro RO dele e pendura nele a liquidação (NS) e o pagamento (OB). ``numeros`` traz as chaves
    ``empenho``, ``ro``, ``ns`` e ``ob``; ``valores``, ``empenhado``, ``liquidado`` e ``pago``.
    """
    linhas = [
        _linha_de_execucao(numeros['empenho'], numeros['ro'], ('401091', 'EMPENHO DE DESPESA'), data, ug, (valores['empenhado'], '0,00', '0,00')),
        _linha_de_execucao(numeros['empenho'], numeros['ns'], ('511200', 'LIQUIDACAO DE DESPESA'), data, ug, ('0,00', valores['liquidado'], '0,00')),
        _linha_de_execucao(numeros['empenho'], numeros['ob'], ('', ''), data, ug, ('0,00', '0,00', valores['pago'])),
    ]
    conteudo = [['Exec NE Emitido, Liquidado e Pago'], [], _cabecalho(linhas[0]), [], [], *(_valores(linha) for linha in linhas)]
    return Planilha('Exec NE Emitido, Liquidado e Pago', 'execucao_empenhos.csv', conteudo, delimitador=',')
