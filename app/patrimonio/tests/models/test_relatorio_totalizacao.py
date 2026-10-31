"""Totalizações contábeis do patrimônio (``RelatorioPatrim`` e ``patrimonio.relatorio``).

São os números que vão para o relatório entregue à contabilidade: entrada do período,
saída por baixa e o acumulado (entrada menos saída). Bens imóveis e intangíveis (códigos 90 e
94) ficam de fora por decisão contábil, e é justamente o tipo de regra que some numa
refatoração sem que nenhuma tela reclame.
"""

import datetime
from decimal import Decimal

import pytest

from patrimonio.models import Inventario, InventarioStatus, RelatorioPatrim
from patrimonio.relatorio import (
    total_ed_acumulado_ateh_periodo,
    totalizacaoCategoriaPeriodo,
    totalizacaoPeriodo,
    totalizacaoPlanoContasPeriodo,
)
from patrimonio.tests.factories import (
    BaixaFactory,
    CategoriaMaterialPermanenteFactory,
    EntradaPermanenteFactory,
)
from rh.tests.factories import SetorFactory

JANEIRO = datetime.datetime(2020, 1, 15, 10, 0)
FEVEREIRO = datetime.datetime(2020, 2, 10, 10, 0)


@pytest.fixture
def campus(db):
    return SetorFactory().uo


@pytest.fixture
def entrada_de_janeiro(db, dados_referencia, campus):
    """Dois itens de R$ 100 recebidos em janeiro/2020, no mesmo elemento de despesa.

    Dois itens de ``qtd=1``, e não um de ``qtd=2``, para o cenário continuar distinguindo
    "duas linhas de entrada" de "duas unidades da mesma linha"; a soma por unidade tem teste
    próprio em ``test_soma_por_unidade_e_nao_por_item_de_entrada``.
    """
    categoria = CategoriaMaterialPermanenteFactory()
    primeiro = EntradaPermanenteFactory(entrada__uo=campus, entrada__data=JANEIRO, categoria=categoria, qtd=1, valor=100)
    EntradaPermanenteFactory(entrada=primeiro.entrada, categoria=categoria, qtd=1, valor=100)
    return primeiro


class TestValorEntrada:
    def test_soma_valor_vezes_quantidade_do_periodo(self, entrada_de_janeiro):
        assert RelatorioPatrim.valor_entrada([JANEIRO.date(), JANEIRO.date()]) == Decimal('200')

    def test_periodo_sem_entrada_soma_zero(self, entrada_de_janeiro):
        assert RelatorioPatrim.valor_entrada([FEVEREIRO.date(), FEVEREIRO.date()]) == Decimal('0.0')

    def test_uma_data_significa_tudo_ate_ela(self, entrada_de_janeiro):
        assert RelatorioPatrim.valor_entrada([FEVEREIRO.date()]) == Decimal('200')

    def test_ignora_bens_imoveis_e_intangiveis(self, db, dados_referencia, campus):
        """Códigos 90 e 94 ficam fora de toda totalização (``CATEGORIAS_EXCLUIDAS``)."""
        imovel = CategoriaMaterialPermanenteFactory(codigo='90', nome='Bens Imóveis')
        EntradaPermanenteFactory(entrada__uo=campus, entrada__data=JANEIRO, categoria=imovel, qtd=1, valor=5000)

        assert RelatorioPatrim.valor_entrada([JANEIRO.date()]) == Decimal('0.0')

    def test_soma_por_unidade_e_nao_por_item_de_entrada(self, db, dados_referencia, campus):
        """Um item de quantidade 3 a R$ 100 totaliza R$ 300: cada unidade vira um tombamento.

        Já valeu R$ 100 — o ``field='valor*qtd'`` passado ao ``Sum`` é sintaxe do Django 1.x e
        virou um kwarg sem efeito, deixando de fora tudo o que a quantidade gerava.
        """
        EntradaPermanenteFactory(entrada__uo=campus, entrada__data=JANEIRO, qtd=3, valor=100)

        assert RelatorioPatrim.valor_entrada([JANEIRO.date()]) == Decimal('300')

    def test_restringe_ao_elemento_de_despesa_informado(self, entrada_de_janeiro, campus):
        outra = CategoriaMaterialPermanenteFactory()
        EntradaPermanenteFactory(entrada__uo=campus, entrada__data=JANEIRO, categoria=outra, qtd=1, valor=70)

        assert RelatorioPatrim.valor_entrada([JANEIRO.date()], categoria_id=outra.pk) == Decimal('70')


class TestValorSaidaEAcumulado:
    @pytest.fixture
    def com_uma_baixa(self, entrada_de_janeiro, campus):
        """Um dos dois bens é baixado: a saída contábil é o valor de entrada dele."""
        inventario = entrada_de_janeiro.inventario_set.get()
        Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.ATIVO())
        inventario.refresh_from_db()
        Inventario.efetuar_baixa(inventarios=inventario, baixa=BaixaFactory(uo=campus))
        return inventario

    def test_saida_soma_o_valor_de_entrada_dos_baixados(self, com_uma_baixa):
        assert RelatorioPatrim.valor_saida([datetime.date.today()]) == Decimal('100')

    def test_saida_antes_da_baixa_e_zero(self, com_uma_baixa):
        assert RelatorioPatrim.valor_saida([JANEIRO.date()]) == Decimal('0.0')

    def test_acumulado_e_entrada_menos_saida(self, com_uma_baixa):
        hoje = datetime.date.today()
        acumulado = RelatorioPatrim.valor_acumulado(hoje)
        assert acumulado == RelatorioPatrim.valor_entrada([hoje]) - RelatorioPatrim.valor_saida([hoje])
        assert acumulado == Decimal('100')


class TestTotalizacoesDoRelatorio:
    def test_totalizacao_por_elemento_de_despesa_soma_o_mes(self, entrada_de_janeiro):
        resposta, total = totalizacaoCategoriaPeriodo(2020, 1, incluir_doacao=True)
        assert [linha['codigo'] for linha in resposta] == [entrada_de_janeiro.categoria.codigo]
        assert total == '200,00'

    def test_totalizacao_por_elemento_de_despesa_conta_cada_unidade(self, db, dados_referencia, campus):
        """Mesma correção do ``Sum`` por unidade, agora no relatório por elemento de despesa."""
        EntradaPermanenteFactory(entrada__uo=campus, entrada__data=JANEIRO, qtd=3, valor=100)

        _, total = totalizacaoCategoriaPeriodo(2020, 1, incluir_doacao=True)

        assert total == '300,00'

    def test_totalizacao_exclui_doacoes_quando_pedido(self, entrada_de_janeiro):
        """A entrada do cenário é doação (``tipoentrada_id`` 2); sem doações, o mês zera."""
        resposta, total = totalizacaoCategoriaPeriodo(2020, 1, incluir_doacao=False)
        assert resposta == []
        assert total == '0,00'

    def test_totalizacao_ignora_mes_sem_movimento(self, entrada_de_janeiro):
        resposta, total = totalizacaoCategoriaPeriodo(2020, 2, incluir_doacao=True)
        assert resposta == []
        assert total == '0,00'

    def test_totalizacao_por_plano_de_contas_agrupa_pelo_plano(self, entrada_de_janeiro):
        resposta, total = totalizacaoPlanoContasPeriodo(2020, 1, incluir_doacao=True)
        assert [linha['codigo'] for linha in resposta] == [entrada_de_janeiro.categoria.plano_contas.codigo]
        assert total == '200,00'

    def test_acumulado_ate_o_periodo_lista_uma_linha_por_elemento_de_despesa(self, entrada_de_janeiro):
        categorias, acumulado, periodo = total_ed_acumulado_ateh_periodo(1, 2020)
        assert periodo == 'Janeiro/2020'
        assert acumulado == '200,00'
        assert [c['codigo'] for c in categorias] == [entrada_de_janeiro.categoria.codigo]

    def test_acumulado_omite_elementos_marcados_para_omitir(self, entrada_de_janeiro):
        entrada_de_janeiro.categoria.omitir = True
        entrada_de_janeiro.categoria.save()

        categorias, acumulado, _ = total_ed_acumulado_ateh_periodo(1, 2020)

        assert categorias == []
        assert acumulado == '200,00', 'o acumulado geral não depende do "omitir", que é só da listagem'

    def test_totalizacao_do_ano_abre_os_doze_meses(self, entrada_de_janeiro):
        meses, ano = totalizacaoPeriodo(2020)
        assert len(meses) == 12
        assert meses[0]['nome'] == 'Janeiro'
        assert meses[0]['entrada'] == '200,00'
        assert meses[1]['entrada'] == '0,00'
        assert ano['acumulado'] == '200,00'
