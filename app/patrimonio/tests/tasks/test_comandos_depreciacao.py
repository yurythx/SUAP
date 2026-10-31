"""Comandos de depreciação e reavaliação do acervo (rodam no cron mensal).

Depreciação é a regra contábil mais cara do módulo: linear, mensal, do valor de entrada
até o valor residual, a partir da data configurada. Nenhuma tela dispara isso — se o
comando parar de funcionar, o acervo simplesmente congela de valor e ninguém percebe até
o fechamento.
"""

import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from comum.models import Configuracao
from djtools.utils import cache
from patrimonio.models import HistoricoCatDepreciacao, Inventario, InventarioReavaliacao, InventarioStatus, InventarioValor
from patrimonio.tests.factories import CategoriaMaterialPermanenteFactory, EntradaPermanenteFactory
from rh.tests.factories import ServidorFactory


@pytest.fixture
def depreciacao_configurada(db):
    """``InventarioValor.depreciar`` lê a data de início da depreciação da configuração."""
    Configuracao.objects.update_or_create(app='patrimonio', chave='data_inicio_depreciacao', defaults={'valor': '2010-01-01'})
    cache.delete('_CONFIGURACAO_CACHED')


def bem_ativo(campus, *, entrada_em, categoria=None, valor=1200):
    """Um bem ativo (logo, depreciável) recebido na data informada."""
    entrada = EntradaPermanenteFactory(
        entrada__uo=campus, entrada__data=entrada_em, categoria=categoria or CategoriaMaterialPermanenteFactory(), qtd=1, valor=valor
    )
    inventario = entrada.inventario_set.get()
    Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.ATIVO())
    inventario.refresh_from_db()
    return inventario


@pytest.fixture
def campus(db, dados_referencia, sync_permissions):
    return ServidorFactory().setor.uo


class TestDepreciarInventarios:
    def test_deprecia_mes_a_mes_desde_a_entrada(self, depreciacao_configurada, campus):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_depreciar_inventarios')

        depreciacoes = InventarioValor.objects.filter(inventario=inventario).order_by('data')
        assert depreciacoes.count() > 1
        assert depreciacoes.first().data.day == 29, 'a parcela fecha no último dia do mês'
        inventario.refresh_from_db()
        assert inventario.valor < Decimal('1200')

    def test_nunca_deprecia_abaixo_do_valor_residual(self, depreciacao_configurada, campus):
        """Vida útil de 1 ano e entrada antiga: já passou do fim da vida útil."""
        categoria = CategoriaMaterialPermanenteFactory(vida_util_em_anos=1, percentual_residual=0.1)
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2015, 1, 15), categoria=categoria)

        call_command('patrimonio_depreciar_inventarios')

        inventario.refresh_from_db()
        assert inventario.valor >= Decimal('120.00'), '10% de R$ 1.200 é o piso contábil'

    def test_nao_deprecia_as_categorias_excluidas(self, depreciacao_configurada, campus):
        excluida = CategoriaMaterialPermanenteFactory(codigo='00')
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15), categoria=excluida)

        call_command('patrimonio_depreciar_inventarios')

        assert not InventarioValor.objects.filter(inventario=inventario).exists()

    def test_nao_deprecia_bem_baixado(self, depreciacao_configurada, campus):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))
        Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.BAIXADO())

        call_command('patrimonio_depreciar_inventarios')

        assert not InventarioValor.objects.filter(inventario=inventario).exists()

    def test_rodar_de_novo_no_mesmo_mes_nao_deprecia_duas_vezes(self, depreciacao_configurada, campus):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))
        call_command('patrimonio_depreciar_inventarios')
        parcelas = InventarioValor.objects.filter(inventario=inventario).count()
        valor = Inventario.objects.get(pk=inventario.pk).valor

        call_command('patrimonio_depreciar_inventarios')

        assert InventarioValor.objects.filter(inventario=inventario).count() == parcelas
        assert Inventario.objects.get(pk=inventario.pk).valor == valor

    def test_registra_o_historico_de_depreciacao_do_campus(self, depreciacao_configurada, campus):
        bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_depreciar_inventarios')

        assert HistoricoCatDepreciacao.objects.filter(campus=campus).exists()


class TestElementoSemVidaUtil:
    """Vida útil 0 e residual 0 marcam o elemento de despesa como não depreciável.

    Já estourou com ``decimal.DivisionByZero``: a parcela mensal dividia pela vida útil em
    meses, e o primeiro bem desse elemento derrubava o comando no meio do acervo.
    """

    @pytest.fixture
    def nao_depreciavel(self, db):
        return CategoriaMaterialPermanenteFactory(vida_util_em_anos=0, percentual_residual=0)

    def test_depreciar_mantem_o_valor_de_entrada(self, depreciacao_configurada, campus, nao_depreciavel):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15), categoria=nao_depreciavel)
        depreciavel = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_depreciar_inventarios')

        assert not InventarioValor.objects.filter(inventario=inventario).exists()
        assert Inventario.objects.get(pk=inventario.pk).valor == Decimal('1200')
        assert InventarioValor.objects.filter(inventario=depreciavel).exists(), 'os demais bens seguem depreciando'

    def test_redepreciar_tudo_volta_ao_valor_de_entrada(self, depreciacao_configurada, campus, nao_depreciavel):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15), categoria=nao_depreciavel)
        depreciavel = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_redepreciar_tudo')

        assert not InventarioValor.objects.filter(inventario=inventario).exists()
        assert Inventario.objects.get(pk=inventario.pk).valor == Decimal('1200')
        assert InventarioValor.objects.filter(inventario=depreciavel).exists()

    def test_reavaliar_ignora_o_elemento(self, depreciacao_configurada, campus, nao_depreciavel):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2008, 1, 15), categoria=nao_depreciavel)

        call_command('patrimonio_reavaliar_inventarios')

        assert not InventarioReavaliacao.objects.filter(inventario=inventario).exists()

    def test_residual_zero_com_vida_util_deprecia_ate_zerar(self, depreciacao_configurada, campus):
        categoria = CategoriaMaterialPermanenteFactory(vida_util_em_anos=1, percentual_residual=0)
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2015, 1, 15), categoria=categoria)

        call_command('patrimonio_depreciar_inventarios')

        assert InventarioValor.objects.filter(inventario=inventario).count() == 12
        assert Inventario.objects.get(pk=inventario.pk).valor == Decimal('0')


class TestReavaliarInventarios:
    def test_reavalia_bem_anterior_ao_inicio_da_depreciacao(self, depreciacao_configurada, campus):
        """Antes de 2010 não havia depreciação: o comando recompõe o histórico por reavaliação.

        Já estourou com ``TypeError: unsupported operand type(s) for -: 'Decimal' and
        'float'``: a parcela mensal era calculada em ``float`` e subtraída de um ``Decimal``.
        Como o comando percorre o acervo inteiro, o primeiro bem antigo derrubava tudo.
        """
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2008, 1, 15))

        call_command('patrimonio_reavaliar_inventarios')

        assert InventarioReavaliacao.objects.filter(inventario=inventario).exists()

    def test_bem_recente_nao_e_reavaliado(self, depreciacao_configurada, campus):
        inventario = bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_reavaliar_inventarios')

        assert not InventarioReavaliacao.objects.filter(inventario=inventario).exists()


class TestAtualizarHistoricoDeDepreciacao:
    def test_cria_o_historico_do_mes_anterior(self, depreciacao_configurada, campus):
        bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))

        call_command('patrimonio_atualizar_catdepreciacao')

        hoje = datetime.date.today()
        mes, ano = (12, hoje.year - 1) if hoje.month == 1 else (hoje.month - 1, hoje.year)
        assert HistoricoCatDepreciacao.objects.filter(campus=campus, mes=mes, ano=ano).exists()

    def test_nao_reescreve_historico_ja_existente(self, depreciacao_configurada, campus):
        bem_ativo(campus, entrada_em=datetime.datetime(2020, 1, 15))
        call_command('patrimonio_atualizar_catdepreciacao')
        antes = HistoricoCatDepreciacao.objects.count()

        call_command('patrimonio_atualizar_catdepreciacao')

        assert HistoricoCatDepreciacao.objects.count() == antes
