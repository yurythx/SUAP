"""Exportação do resultado da busca de inventários (``tasks.inventario_dados_exportacao``).

É a planilha que o setor de patrimônio manda para a contabilidade e para o inventário
anual. Sob pytest a task roda em processo (``running_tests``) e o navegador recebe o
redirecionamento para a tela do processo, então o que dá para afirmar de fora é que a
exportação foi executada sem erro; o conteúdo de cada coluna é verificado nas funções que
montam as células.
"""

import datetime

import pytest

from comum.tests.factories import SalaFactory
from djtools.models import Task
from patrimonio.models import Inventario, InventarioStatus, Requisicao
from patrimonio.tasks import (
    anotacoes_ultima_conferencia,
    anotacoes_ultima_requisicao,
    truncate,
    ultima_conferencia_exportacao,
    ultima_requisicao_exportacao,
)
from patrimonio.tests.factories import (
    ConferenciaItemFactory,
    ConferenciaSalaFactory,
    EntradaPermanenteFactory,
    RequisicaoFactory,
    RequisicaoItemFactory,
)
from rh.tests.factories import ServidorFactory

COORDENADOR = 'Coordenador de Patrimônio'


@pytest.fixture
def bem_ativo(db, dados_referencia, sync_permissions):
    """Um bem ativo com carga — o caso normal de uma linha da planilha."""
    servidor = ServidorFactory()
    entrada = EntradaPermanenteFactory(
        entrada__uo=servidor.setor.uo, entrada__data=datetime.datetime(2020, 3, 5), descricao='Cadeira', qtd=1, valor=100
    )
    inventario = entrada.inventario_set.get()
    Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.ATIVO(), responsavel_vinculo=servidor.get_vinculo())
    inventario.refresh_from_db()
    return {'servidor': servidor, 'inventario': inventario}


class TestTruncate:
    def test_texto_curto_passa_inteiro(self):
        assert truncate('cadeira', 20) == 'cadeira'

    def test_texto_longo_e_cortado_com_reticencias(self):
        assert truncate('cadeira giratória de escritório', 10) == 'cadeira...'


class TestCelulaDeUltimaRequisicao:
    def anotar(self, inventario):
        return Inventario.objects.annotate(**anotacoes_ultima_requisicao()).get(pk=inventario.pk)

    def test_sem_requisicao_a_celula_e_traco(self, bem_ativo):
        assert ultima_requisicao_exportacao(self.anotar(bem_ativo['inventario'])) == '-'

    def test_com_requisicao_traz_numero_destinatario_e_situacao(self, bem_ativo):
        destino = ServidorFactory()
        requisicao = RequisicaoFactory(
            vinculo_origem=bem_ativo['servidor'].get_vinculo(),
            vinculo_destino=destino.get_vinculo(),
            status=Requisicao.STATUS_DEFERIDA,
            campus_origem=bem_ativo['servidor'].setor.uo,
            campus_destino=destino.setor.uo,
        )
        RequisicaoItemFactory(requisicao=requisicao, inventario=bem_ativo['inventario'])

        celula = ultima_requisicao_exportacao(self.anotar(bem_ativo['inventario']))

        assert celula == f'Requisição #{requisicao.pk} - Destinatário: {destino.nome} - Situação: Deferida'


class TestCelulaDeUltimaConferencia:
    def anotar(self, inventario):
        return Inventario.objects.annotate(**anotacoes_ultima_conferencia()).get(pk=inventario.pk)

    def test_sem_conferencia_a_celula_e_traco(self, bem_ativo):
        assert ultima_conferencia_exportacao(self.anotar(bem_ativo['inventario'])) == '-'

    def test_com_conferencia_traz_o_numero_da_conferencia(self, bem_ativo):
        sala = SalaFactory(predio__uo=bem_ativo['servidor'].setor.uo)
        conferencia = ConferenciaSalaFactory(sala=sala, responsavel=bem_ativo['servidor'])
        ConferenciaItemFactory(conferencia=conferencia, inventario=bem_ativo['inventario'])

        celula = ultima_conferencia_exportacao(self.anotar(bem_ativo['inventario']))

        assert celula.startswith(f'Conferência {conferencia.pk} - ')

    def test_vale_a_coleta_mais_recente(self, bem_ativo):
        sala = SalaFactory(predio__uo=bem_ativo['servidor'].setor.uo)
        antiga = ConferenciaSalaFactory(sala=sala, responsavel=bem_ativo['servidor'])
        recente = ConferenciaSalaFactory(sala=sala, responsavel=bem_ativo['servidor'])
        ConferenciaItemFactory(conferencia=antiga, inventario=bem_ativo['inventario'], dh_coleta=datetime.datetime(2020, 1, 1))
        ConferenciaItemFactory(conferencia=recente, inventario=bem_ativo['inventario'], dh_coleta=datetime.datetime(2024, 1, 1))

        celula = ultima_conferencia_exportacao(self.anotar(bem_ativo['inventario']))

        assert celula.startswith(f'Conferência {recente.pk} - ')


class TestExportacaoPelaBusca:
    @pytest.fixture
    def cliente(self, patrimonio_context, bem_ativo):
        patrimonio_context.login(bem_ativo['servidor'], COORDENADOR)
        return patrimonio_context.client

    @pytest.mark.parametrize('formato', ['csv', 'xls'])
    def test_exportar_a_busca_dispara_a_task_e_leva_para_o_processo(self, cliente, bem_ativo, formato):
        resposta = cliente.get('/patrimonio/inventario_busca/', {'numero': bem_ativo['inventario'].numero, 'format': formato})

        assert resposta.status_code == 302
        assert resposta.url.startswith('/djtools/process/')
        assert Task.objects.filter(type='Exportar Relatório de Busca').exists()
