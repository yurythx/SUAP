"""Filtros da busca de inventários (``patrimonio.views.filtrar_inventarios`` e auxiliares).

É a tela mais usada do módulo e a única que interpreta sintaxe digitada pelo operador:
``1-5`` é faixa, ``1,3`` é lista, ``<100`` e ``>=100`` comparam valor. Um erro de
interpretação aqui devolve o inventário errado sem dar nenhum sinal de erro.
"""

import pytest

from comum.tests.factories import SalaFactory
from patrimonio.models import Inventario, InventarioStatus
from patrimonio.tests.factories import EntradaPermanenteFactory, InventarioRotuloFactory
from patrimonio.views import filtrar_inventarios
from rh.tests.factories import ServidorFactory, SetorFactory


@pytest.fixture
def acervo(db, dados_referencia, sync_permissions):
    """Cinco tombamentos sequenciais de mesma descrição, valor 100, num único campus."""
    servidor = ServidorFactory()
    entrada = EntradaPermanenteFactory(entrada__uo=servidor.setor.uo, descricao='Cadeira giratória', qtd=5, valor=100)
    inventarios = list(entrada.inventario_set.order_by('numero'))
    return {'servidor': servidor, 'entrada': entrada, 'inventarios': inventarios, 'numeros': [i.numero for i in inventarios]}


def numeros(queryset):
    return list(queryset.values_list('numero', flat=True))


class TestFiltroPorNumero:
    def test_numero_isolado_traz_um_tombamento(self, acervo):
        alvo = acervo['numeros'][2]
        assert numeros(filtrar_inventarios({'numero': str(alvo)})) == [alvo]

    def test_faixa_traz_o_intervalo_fechado(self, acervo):
        inicio, fim = acervo['numeros'][1], acervo['numeros'][3]
        assert numeros(filtrar_inventarios({'numero': f'{inicio}-{fim}'})) == [inicio, inicio + 1, fim]

    def test_faixa_invertida_e_normalizada(self, acervo):
        """``5-1`` é o mesmo intervalo de ``1-5``: o operador não precisa ordenar."""
        inicio, fim = acervo['numeros'][1], acervo['numeros'][3]
        assert numeros(filtrar_inventarios({'numero': f'{fim}-{inicio}'})) == [inicio, inicio + 1, fim]

    def test_lista_separada_por_virgula_traz_apenas_os_citados(self, acervo):
        primeiro, ultimo = acervo['numeros'][0], acervo['numeros'][-1]
        assert numeros(filtrar_inventarios({'numero': f'{primeiro},{ultimo}'})) == [primeiro, ultimo]


class TestFiltroPorValor:
    @pytest.fixture(autouse=True)
    def _valores_distintos(self, acervo):
        """Dois bens reavaliados para baixo e um para cima, em torno dos 100 da entrada."""
        barato, caro = acervo['inventarios'][0], acervo['inventarios'][-1]
        Inventario.objects.filter(pk=barato.pk).update(valor=50)
        Inventario.objects.filter(pk=caro.pk).update(valor=150)
        self.barato, self.caro = barato.numero, caro.numero

    def test_menor_que_exclui_o_limite(self, acervo):
        assert numeros(filtrar_inventarios({'valor': '<100'})) == [self.barato]

    def test_menor_ou_igual_inclui_o_limite(self, acervo):
        assert numeros(filtrar_inventarios({'valor': '<=100'})) == [n for n in acervo['numeros'] if n != self.caro]

    def test_maior_que_exclui_o_limite(self, acervo):
        assert numeros(filtrar_inventarios({'valor': '>100'})) == [self.caro]

    def test_maior_ou_igual_inclui_o_limite(self, acervo):
        assert numeros(filtrar_inventarios({'valor': '>=100'})) == [n for n in acervo['numeros'] if n != self.barato]

    def test_valor_exato_aceita_virgula_decimal(self, acervo):
        assert numeros(filtrar_inventarios({'valor': '50,00'})) == [self.barato]

    def test_valor_ilegivel_nao_filtra_nada(self, acervo):
        """Digitação inválida devolve a busca inteira em vez de estourar a tela."""
        assert numeros(filtrar_inventarios({'valor': 'cem reais'})) == acervo['numeros']


class TestFiltroPorDescricaoEObservacao:
    def test_cada_palavra_da_descricao_restringe_o_resultado(self, acervo):
        assert numeros(filtrar_inventarios({'descricao': 'cadeira giratoria'})) == acervo['numeros']

    def test_a_busca_por_descricao_ocorre_sem_acento(self, acervo):
        """``campo_busca`` é gravado em ASCII maiúsculo, mas o filtro é ``icontains`` cru:
        quem digita o acento não encontra o bem. Documentado para que a mudança desse
        comportamento seja deliberada."""
        assert numeros(filtrar_inventarios({'descricao': 'giratória'})) == []

    def test_palavra_ausente_zera_o_resultado(self, acervo):
        assert numeros(filtrar_inventarios({'descricao': 'cadeira mesa'})) == []

    def test_observacao_e_busca_parcial(self, acervo):
        alvo = acervo['inventarios'][0]
        Inventario.objects.filter(pk=alvo.pk).update(observacao='Pé quebrado')
        assert numeros(filtrar_inventarios({'observacao': 'quebrado'})) == [alvo.numero]


class TestFiltrosPorRelacionamento:
    def test_status_restringe_ao_estado_informado(self, acervo):
        alvo = acervo['inventarios'][0]
        Inventario.objects.filter(pk=alvo.pk).update(status=InventarioStatus.ATIVO())
        assert numeros(filtrar_inventarios({'status': InventarioStatus.ATIVO()})) == [alvo.numero]

    def test_rotulo_restringe_aos_marcados(self, acervo):
        rotulo = InventarioRotuloFactory(unidade_organizacional=acervo['servidor'].setor.uo)
        alvo = acervo['inventarios'][1]
        alvo.rotulos.add(rotulo)
        assert numeros(filtrar_inventarios({'rotulos': rotulo})) == [alvo.numero]

    def test_sala_restringe_aos_alocados(self, acervo):
        sala = SalaFactory(predio__uo=acervo['servidor'].setor.uo)
        alvo = acervo['inventarios'][2]
        Inventario.objects.filter(pk=alvo.pk).update(sala=sala)
        assert numeros(filtrar_inventarios({'sala': sala})) == [alvo.numero]

    def test_responsavel_restringe_a_carga_do_servidor(self, acervo):
        alvo = acervo['inventarios'][3]
        Inventario.objects.filter(pk=alvo.pk).update(responsavel_vinculo=acervo['servidor'].get_vinculo())
        assert numeros(filtrar_inventarios({'responsavel': acervo['servidor']})) == [alvo.numero]

    def test_elemento_de_despesa_restringe_a_categoria_da_entrada(self, acervo):
        outro = EntradaPermanenteFactory(qtd=1)
        assert numeros(filtrar_inventarios({'elemento_despesa': outro.categoria})) == [outro.inventario_set.get().numero]

    def test_numero_de_serie_e_busca_parcial(self, acervo):
        alvo = acervo['inventarios'][4]
        Inventario.objects.filter(pk=alvo.pk).update(numero_serie='ABC-12345')
        assert numeros(filtrar_inventarios({'numero_serie': '12345'})) == [alvo.numero]


class TestFiltroPorSetor:
    def test_sem_recursao_traz_apenas_a_carga_do_proprio_setor(self, acervo):
        setor_pai = acervo['servidor'].setor
        subordinado = ServidorFactory(setor=SetorFactory(superior=setor_pai, campus=False))
        do_pai, do_filho = acervo['inventarios'][0], acervo['inventarios'][1]
        Inventario.objects.filter(pk=do_pai.pk).update(responsavel_vinculo=acervo['servidor'].get_vinculo())
        Inventario.objects.filter(pk=do_filho.pk).update(responsavel_vinculo=subordinado.get_vinculo())

        assert numeros(filtrar_inventarios({'setor_responsavel': setor_pai, 'recursivo': False})) == [do_pai.numero]

    def test_com_recursao_inclui_a_carga_dos_setores_descendentes(self, acervo):
        setor_pai = acervo['servidor'].setor
        subordinado = ServidorFactory(setor=SetorFactory(superior=setor_pai, campus=False))
        do_pai, do_filho = acervo['inventarios'][0], acervo['inventarios'][1]
        Inventario.objects.filter(pk=do_pai.pk).update(responsavel_vinculo=acervo['servidor'].get_vinculo())
        Inventario.objects.filter(pk=do_filho.pk).update(responsavel_vinculo=subordinado.get_vinculo())

        encontrados = numeros(filtrar_inventarios({'setor_responsavel': setor_pai, 'recursivo': True}))

        assert encontrados == sorted([do_pai.numero, do_filho.numero])


class TestCombinacaoDeFiltros:
    def test_filtros_se_acumulam(self, acervo):
        alvo = acervo['inventarios'][2]
        Inventario.objects.filter(pk=alvo.pk).update(numero_serie='SN-999')
        encontrados = filtrar_inventarios({'descricao': 'cadeira', 'numero_serie': 'SN-999'})
        assert numeros(encontrados) == [alvo.numero]

    def test_sem_criterio_devolve_todo_o_acervo(self, acervo):
        assert numeros(filtrar_inventarios({})) == acervo['numeros']
