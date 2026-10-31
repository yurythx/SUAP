"""Managers de ``Inventario`` e o filtro de salas com observação.

Os managers são o vocabulário que views e relatórios usam para falar de "ativo",
"pendente", "baixado" e "depreciável"; um filtro errado aqui vaza silenciosamente para
todas as telas.
"""

import pytest

from comum.tests.factories import SalaFactory
from djtools.middleware import threadlocals
from patrimonio.models import ConferenciaItem, Inventario, InventarioStatus
from patrimonio.templatetags.patrimonio_templatetags import salas_com_observacoes
from patrimonio.tests.factories import (
    ConferenciaItemFactory,
    ConferenciaSalaFactory,
    EntradaPermanenteFactory,
)
from rh.tests.factories import ServidorFactory


@pytest.fixture
def inventarios(db, dados_referencia, sync_permissions):
    """Um tombamento em cada estado: ativo (com carga), baixado e pendente."""
    servidor = ServidorFactory()
    entrada = EntradaPermanenteFactory(entrada__uo=servidor.setor.uo, qtd=3)
    ativo, baixado, pendente = entrada.inventario_set.order_by('numero')
    Inventario.objects.filter(pk=ativo.pk).update(status=InventarioStatus.ATIVO(), responsavel_vinculo=servidor.get_vinculo())
    Inventario.objects.filter(pk=baixado.pk).update(status=InventarioStatus.BAIXADO())
    return {'servidor': servidor, 'ativo': ativo, 'baixado': baixado, 'pendente': pendente}


class TestManagersDeInventario:
    def test_ativos_traz_apenas_o_de_status_ativo(self, inventarios):
        assert list(Inventario.ativos.all()) == [inventarios['ativo']]

    def test_pendentes_traz_apenas_o_de_status_pendente(self, inventarios):
        assert list(Inventario.pendentes.all()) == [inventarios['pendente']]

    def test_baixados_traz_apenas_o_de_status_baixado(self, inventarios):
        assert list(Inventario.baixados.all()) == [inventarios['baixado']]

    def test_depreciaveis_reune_ativos_e_pendentes_e_exclui_baixados(self, inventarios):
        depreciaveis = set(Inventario.depreciaveis.all())
        assert depreciaveis == {inventarios['ativo'], inventarios['pendente']}

    def test_ativos_gerenciaveis_traz_o_ativo_com_carga_no_campus_do_usuario(self, inventarios):
        threadlocals.context.user = inventarios['servidor'].get_user()
        assert list(Inventario.ativos_gerenciaveis.all()) == [inventarios['ativo']]

    def test_ativos_gerenciaveis_ignora_ativo_com_carga_em_outro_campus(self, inventarios):
        de_outro_campus = ServidorFactory()
        Inventario.objects.filter(pk=inventarios['ativo'].pk).update(responsavel_vinculo=de_outro_campus.get_vinculo())
        threadlocals.context.user = inventarios['servidor'].get_user()
        assert list(Inventario.ativos_gerenciaveis.all()) == []

    def test_ativos_gerenciaveis_inclui_ativo_sem_responsavel(self, inventarios):
        """Sem responsável (logo, sem campus) o bem fica visível para qualquer operador —
        senão ninguém conseguiria regularizá-lo."""
        Inventario.objects.filter(pk=inventarios['ativo'].pk).update(responsavel_vinculo=None)
        threadlocals.context.user = inventarios['servidor'].get_user()
        assert list(Inventario.ativos_gerenciaveis.all()) == [inventarios['ativo']]


class TestSalasComObservacoes:
    def test_retorna_apenas_as_conferencias_cuja_sala_teve_observacao(self, db, dados_referencia, sync_permissions):
        responsavel = ServidorFactory()
        entrada = EntradaPermanenteFactory(qtd=2)
        item_a, item_b = entrada.inventario_set.order_by('numero')

        com_observacao = ConferenciaSalaFactory(
            responsavel=responsavel, sala=SalaFactory(predio__uo=responsavel.setor.uo), observacao='Faltou conferir a bancada'
        )
        sem_observacao = ConferenciaSalaFactory(responsavel=responsavel, sala=SalaFactory(predio__uo=responsavel.setor.uo), observacao='')
        ConferenciaItemFactory(conferencia=com_observacao, inventario=item_a)
        ConferenciaItemFactory(conferencia=sem_observacao, inventario=item_b)

        salas = salas_com_observacoes(ConferenciaItem.objects.all())

        assert list(salas) == [com_observacao]

    def test_conferencia_sem_itens_nao_entra_no_resultado(self, db, dados_referencia, sync_permissions):
        responsavel = ServidorFactory()
        ConferenciaSalaFactory(responsavel=responsavel, sala=SalaFactory(predio__uo=responsavel.setor.uo), observacao='Sala trancada')

        assert list(salas_com_observacoes(ConferenciaItem.objects.all())) == []
