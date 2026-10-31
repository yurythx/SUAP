"""Fluxo: importação dos relatórios do Tesouro Gerencial pela tela ``/tesouro_gerencial/importacao/``.

É a porta de entrada de todo dado do módulo: as variáveis financeiras, os alertas do gestor e o
empenho que o ``contratos`` vincula ao contrato só existem depois de importados. Cada opção do campo
"Relatório" escolhe um importador diferente (``ImportacaoTesouroGerencial.processar``), e cada
importador lê um layout de planilha diferente (``planilhas.py``). O que se afirma aqui:

* que cada um dos quatro relatórios, enviado pela tela, **persiste** o documento que descreve — com
  os valores convertidos do formato brasileiro e amarrados ao documento certo (a liquidação e o
  pagamento voltam ao empenho; o item vai para a nota de crédito). Regressão típica: trocar a ordem
  das opções do formulário ou renomear uma coluna lida por nome no importador — a tela continua
  dizendo "Dados importados com sucesso." e nada é gravado;
* que a receita importada **chega ao relatório** que a consome, pela UG executora do campus — o
  encaixe entre o que o importador grava e o que ``Variavel`` procura.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from random import randint
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from tesouro_gerencial.tests.e2e import planilhas
from tesouro_gerencial.tests.e2e.conftest import CODIGO_UG, CODIGO_UGR, NOME_CAMPUS

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

IMPORTACAO = '/tesouro_gerencial/importacao/'
CAMPI = '/tesouro_gerencial/campi/'

SUCESSO = 'Dados importados com sucesso.'

# UG das planilhas importadas que NÃO é a do campus `TGE`: o que estes testes gravam no ano corrente
# não pode aparecer nas variáveis que os outros arquivos afirmam.
UG_IMPORTACAO = '158909'

ANO = datetime.date.today().year
HOJE = datetime.date.today().strftime('%d/%m/%Y')


def _marca() -> str:
    """Seis dígitos únicos por execução. Só dígitos: o importador tira o tipo do documento do primeiro
    trecho não numérico do número (``ImportadorExecNE.get_tipo``), e uma letra a mais o corromperia."""
    return f'{uuid4().int % 10**6:06d}'


def _nota_de_credito(marca: str) -> tuple[planilhas.Planilha, Callable[[], None]]:
    numero = f'{ANO}NC{marca}'

    def conferir() -> None:
        from tesouro_gerencial.models import NotaCredito

        nota = NotaCredito.objects.filter(numero=numero).first()
        assert nota is not None, 'a UI disse que importou, mas a nota de crédito não persistiu'
        assert nota.get_valor() == Decimal('5000.00'), f'valor da nota de crédito: {nota.get_valor()}'
        assert nota.itens.filter(responsavel_ug__codigo=UG_IMPORTACAO, plano_interno__codigo='L20RLP0100N').exists()

    return planilhas.movimentacoes_de_credito(numero, UG_IMPORTACAO, HOJE, '5.000,00'), conferir


def _execucao_de_empenho(marca: str) -> tuple[planilhas.Planilha, Callable[[], None]]:
    numeros = {tipo: f'{ANO}{tipo.upper()}{marca}' for tipo in ('ne', 'ro', 'ns', 'ob')}
    numeros['empenho'] = numeros.pop('ne')

    def conferir() -> None:
        from tesouro_gerencial.models import DocumentoEmpenho

        empenho = DocumentoEmpenho.objects.filter(numero=numeros['empenho']).first()
        assert empenho is not None, 'a UI disse que importou, mas o empenho não persistiu'
        assert empenho.documentos_secundarios.filter(numero=numeros['ro'], tipo='RO').exists(), 'o RO não ficou pendurado no empenho'
        valores = (empenho.get_valor(), empenho.get_valor_liquidado(), empenho.get_valor_pago())
        assert valores == (Decimal('10000.00'), Decimal('4000.00'), Decimal('3500.00')), f'empenhado/liquidado/pago: {valores}'

    valores = {'empenhado': '10.000,00', 'liquidado': '4.000,00', 'pago': '3.500,00'}
    return planilhas.execucao_de_empenhos(numeros, UG_IMPORTACAO, HOJE, valores), conferir


def _restos_a_pagar(marca: str) -> tuple[planilhas.Planilha, Callable[[], None]]:
    numero = f'{ANO - 1}NE{marca}'

    def conferir() -> None:
        from tesouro_gerencial.models import RAP

        rap = RAP.objects.filter(numero=numero, ano=ANO).first()
        assert rap is not None, 'a UI disse que importou, mas o resto a pagar não persistiu'
        assert rap.get_valor() == Decimal('2500.00'), f'liquidado de não processados: {rap.get_valor()}'

    return planilhas.restos_a_pagar(numero, UG_IMPORTACAO, ANO, '2.500,00'), conferir


def _receita_de_gru(marca: str) -> tuple[planilhas.Planilha, Callable[[], None]]:
    # A receita é única por (UG, GRU, ano): o código de recolhimento é o que varia por execução.
    gru = f'9{marca[:4]}'

    def conferir() -> None:
        from tesouro_gerencial.models import ReceitaGRU

        receita = ReceitaGRU.objects.filter(gru__codigo=gru, emitente_ug__codigo=UG_IMPORTACAO, ano=ANO).first()
        assert receita is not None, 'a UI disse que importou, mas a receita não persistiu'
        assert receita.valor == Decimal('1234.56'), f'valor da receita: {receita.valor}'

    return planilhas.receitas_por_gru(UG_IMPORTACAO, gru, ANO, '1.234,56'), conferir


def _importar(tela: Tela, planilha: planilhas.Planilha, diretorio: Path) -> Tela:
    tela.ir(IMPORTACAO).ver_titulo('Importação dos dados do Tesouro Gerencial')
    tela.preencher('Relatório', 'lista', planilha.relatorio)
    tela.preencher('Arquivo', 'arquivo real', str(planilha.gravar(diretorio)))
    return tela.clicar_botao('Enviar')


@pytest.mark.parametrize(
    'montar',
    [_nota_de_credito, _execucao_de_empenho, _restos_a_pagar, _receita_de_gru],
    ids=['movimentacoes-de-credito', 'exec-ne', 'restos-a-pagar', 'arrecadacao-por-gru'],
)
def test_gestor_importa_relatorio_do_tesouro(logado_tesouro, tmp_path, montar):
    """Cada opção de "Relatório" persiste o documento da sua planilha, com os valores convertidos."""
    planilha, conferir = montar(_marca())

    tela = _importar(Tela(logado_tesouro('gestor')), planilha, tmp_path)

    tela.sucesso(SUCESSO)
    conferir()


def test_receita_importada_entra_no_relatorio_de_campi(logado_tesouro, tmp_path):
    """A receita de GRU importada aparece na variável RECCAPT do campus dono da UG executora.

    O valor muda a cada execução: a receita é ``update_or_create`` por (UG, GRU, ano), então o mesmo
    arquivo com outro valor prova que a importação **atualiza** — e que o relatório lê o valor novo.
    """
    from tesouro_gerencial.models import ReceitaGRU

    reais = randint(1000, 9999)
    valor = f'{reais // 1000}.{reais % 1000:03d},{randint(10, 99)}'
    planilha = planilhas.receitas_por_gru(CODIGO_UG, '28812', ANO, valor)

    tela = _importar(Tela(logado_tesouro('gestor')), planilha, tmp_path)
    tela.sucesso(SUCESSO)
    assert ReceitaGRU.objects.filter(emitente_ug__codigo=CODIGO_UG, gru__codigo='28812', ano=ANO).count() == 1

    tela.ir(CAMPI).ver_titulo('Relatório de Campi por Variável')
    tela.preencher_formulario([('Variável', 'lista', 'RECCAPT'), ('Ano', 'número', str(ANO))]).clicar_botao('Enviar')
    campus = f'{CODIGO_UGR} {NOME_CAMPUS}'
    tela.clicar_botao(campus)
    tela.quadro(campus).ver_texto(f'R$ {valor}')
