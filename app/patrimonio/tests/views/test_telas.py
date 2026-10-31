"""As telas do patrimônio respondem para quem tem papel e recusam quem não tem.

Cobertura de fumaça deliberada: cada teste faz um GET e confere status e um dado do
contexto. Não substitui teste de fluxo — serve para que um erro de template, de queryset
ou de decorator apareça aqui em vez de em produção, que é como as telas deste módulo
costumam quebrar.
"""

import pytest

from comum.tests.factories import SalaFactory
from patrimonio.models import Inventario, InventarioStatus
from patrimonio.tests.factories import (
    BaixaFactory,
    CautelaFactory,
    CautelaInventarioFactory,
    ConferenciaItemFactory,
    ConferenciaSalaFactory,
)

COORDENADOR = 'Coordenador de Patrimônio'


@pytest.fixture
def tela(patrimonio_context):
    """Coordenador de patrimônio logado, com um bem ativo sob sua carga."""
    contexto = patrimonio_context
    contexto.login(contexto.servidor, COORDENADOR)
    inventario = contexto.item_a.inventario_set.order_by('numero').first()
    Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.ATIVO(), responsavel_vinculo=contexto.servidor.get_vinculo())
    contexto.inventario = inventario.__class__.objects.get(pk=inventario.pk)
    return contexto


class TestTelasDeInventario:
    def test_busca_de_inventarios_abre_vazia(self, tela):
        resposta = tela.client.get('/patrimonio/inventario_busca/')
        assert resposta.status_code == 200

    def test_busca_de_inventarios_lista_o_resultado_do_filtro(self, tela):
        resposta = tela.client.get('/patrimonio/inventario_busca/', {'numero': tela.inventario.numero, 'opcoes_visualizacao': 50})
        assert resposta.status_code == 200
        assert list(resposta.context['inventarios']) == [tela.inventario]

    def test_servidor_comum_entra_na_busca_para_ver_a_propria_carga(self, tela):
        """O grupo ``Servidor`` dá ``pode_ver_propria_carga``: a tela abre para qualquer um,
        e é o filtro que limita o que ele vê."""
        tela.login(tela.servidor_outro_campus)
        assert tela.client.get('/patrimonio/inventario_busca/').status_code == 200

    def test_busca_de_inventarios_recusa_quem_nao_tem_nenhuma_das_permissoes(self, tela):
        tela.login(tela.servidor_outro_campus)
        # Os grupos são sincronizados a partir do vínculo no login: limpar antes não adianta.
        tela.servidor_outro_campus.get_user().groups.clear()
        assert tela.client.get('/patrimonio/inventario_busca/').status_code == 403

    def test_detalhe_do_inventario_e_acessado_pelo_numero(self, tela):
        resposta = tela.client.get(f'/patrimonio/inventario/{tela.inventario.numero}/')
        assert resposta.status_code == 200
        assert resposta.context['inventario'] == tela.inventario

    def test_detalhe_de_numero_inexistente_responde_404(self, tela):
        assert tela.client.get('/patrimonio/inventario/999999999/').status_code == 404

    def test_historico_de_movimentacao_abre(self, tela):
        resposta = tela.client.get(f'/patrimonio/historico_movimentacao_inventario/{tela.inventario.numero}/')
        assert resposta.status_code == 200
        assert resposta.context['inventario'] == tela.inventario

    def test_edicao_de_inventario_do_proprio_campus_abre(self, tela):
        resposta = tela.client.get(f'/patrimonio/inventario_editar/{tela.inventario.pk}/')
        assert resposta.status_code == 200

    def test_edicao_de_inventario_de_outro_campus_e_recusada(self, tela):
        """``editar_do_meu_campus`` é a permissão do coordenador: a carga em outro campus
        não é dele, ainda que ele enxergue o bem na busca."""
        Inventario.objects.filter(pk=tela.inventario.pk).update(responsavel_vinculo=tela.servidor_outro_campus.get_vinculo())
        assert tela.client.get(f'/patrimonio/inventario_editar/{tela.inventario.pk}/').status_code == 403

    def test_listagem_de_cargas_abre(self, tela):
        assert tela.client.get('/patrimonio/inventarios_cargas/').status_code == 200

    def test_carga_de_pendentes_lista_os_bens_sem_responsavel(self, tela):
        resposta = tela.client.get('/patrimonio/carga/')
        assert resposta.status_code == 200
        assert list(resposta.context['inventarios']) == list(Inventario.get_pendentes(uo=tela.campus))

    def test_atalho_de_pendentes_redireciona_para_a_carga_do_campus(self, tela):
        resposta = tela.client.get('/patrimonio/inventarios_pendentes/')
        assert resposta.status_code == 302
        assert resposta.url == f'/patrimonio/carga/?descricao=&campus={tela.campus.id}'


class TestTelasDeCargaEServidores:
    def test_servidores_com_carga_agrupa_por_campus(self, tela):
        resposta = tela.client.get('/patrimonio/servidores_com_carga/')
        assert resposta.status_code == 200
        assert [c['nome_campus'] for c in resposta.context['lista_campus']] == [str(tela.campus)]

    def test_servidores_com_carga_exige_papel_no_patrimonio(self, tela):
        tela.login(tela.servidor_outro_campus)
        assert tela.client.get('/patrimonio/servidores_com_carga/').status_code == 403

    def test_carga_contabil_inconsistente_abre_sem_inconsistencias(self, tela):
        resposta = tela.client.get('/patrimonio/listar_inventarios_carga_contabil_inconsistentes/')
        assert resposta.status_code == 200
        assert list(resposta.context['inventarios_inconsistentes']) == []

    def test_carga_contabil_inconsistente_acusa_bem_com_carga_em_outro_campus(self, tela):
        """Carga contábil num campus e responsável em outro: é a inconsistência que a tela existe
        para achar."""
        Inventario.objects.filter(pk=tela.inventario.pk).update(responsavel_vinculo=tela.servidor.get_vinculo())
        tela.inventario.carga_contabil.campus = tela.outro_campus
        tela.inventario.carga_contabil.save()

        resposta = tela.client.get('/patrimonio/listar_inventarios_carga_contabil_inconsistentes/')

        assert list(resposta.context['inventarios_inconsistentes']) == [tela.inventario]

    def test_carga_contabil_inconsistente_recusa_quem_nao_pode_alterar(self, tela):
        tela.login(tela.servidor_outro_campus)
        assert tela.client.get('/patrimonio/listar_inventarios_carga_contabil_inconsistentes/').status_code == 403


class TestTelasDeBaixa:
    def test_tela_da_baixa_mostra_os_totais(self, tela):
        baixa = BaixaFactory(uo=tela.campus)
        resposta = tela.client.get(f'/patrimonio/baixa/{baixa.pk}/')
        assert resposta.status_code == 200
        assert resposta.context['baixa'] == baixa
        assert resposta.context['valor_total'] == 0

    def test_edicao_de_baixa_do_proprio_campus_abre(self, tela):
        baixa = BaixaFactory(uo=tela.campus)
        assert tela.client.get(f'/patrimonio/baixa/editar/{baixa.pk}/').status_code == 200

    def test_edicao_de_baixa_de_outro_campus_e_recusada(self, tela):
        baixa = BaixaFactory(uo=tela.outro_campus)
        resposta = tela.client.get(f'/patrimonio/baixa/editar/{baixa.pk}/')
        assert resposta.status_code == 302
        assert resposta.url == '/admin/patrimonio/baixa/'

    def test_baixa_inexistente_responde_404(self, tela):
        assert tela.client.get('/patrimonio/baixa/999999/').status_code == 404


class TestTelasDeCautela:
    def test_tela_da_cautela_abre_com_o_formulario_de_item(self, tela):
        cautela = CautelaFactory()
        resposta = tela.client.get(f'/patrimonio/cautela/{cautela.pk}/')
        assert resposta.status_code == 200
        assert resposta.context['cautela'] == cautela

    def test_detalhe_da_cautela_lista_os_itens(self, tela):
        cautela = CautelaFactory()
        CautelaInventarioFactory(cautela=cautela, inventario=tela.inventario)

        resposta = tela.client.get(f'/patrimonio/tela_cautela_detalhe/{cautela.pk}/')

        assert [item['numero'] for item in resposta.context['resposta']] == [tela.inventario.numero]


class TestTelasDeConferencia:
    @pytest.fixture
    def conferencia(self, tela):
        sala = SalaFactory(predio__uo=tela.campus)
        Inventario.objects.filter(pk=tela.inventario.pk).update(sala=sala)
        return ConferenciaSalaFactory(sala=sala, responsavel=tela.servidor, observacao='Conferência anual')

    def test_tela_da_conferencia_separa_coletados_de_nao_coletados(self, tela, conferencia):
        resposta = tela.client.get(f'/patrimonio/conferenciasala/{conferencia.pk}/')
        assert resposta.status_code == 200
        assert list(resposta.context['inventarios_nao_coletados']) == [tela.inventario]

    def test_bem_coletado_sai_da_lista_de_nao_coletados(self, tela, conferencia):
        ConferenciaItemFactory(conferencia=conferencia, inventario=tela.inventario)

        resposta = tela.client.get(f'/patrimonio/conferenciasala/{conferencia.pk}/')

        assert list(resposta.context['inventarios_nao_coletados']) == []
        assert resposta.context['conferencia_total']['qtd'] == 1

    def test_busca_dentro_da_conferencia_filtra_os_nao_coletados(self, tela, conferencia):
        resposta = tela.client.get(f'/patrimonio/conferenciasala/{conferencia.pk}/', {'q_inventarios_nao_coletados': 'INEXISTENTE'})
        assert list(resposta.context['inventarios_nao_coletados']) == []

    def test_impressao_da_conferencia_abre(self, tela, conferencia):
        assert tela.client.get(f'/patrimonio/imprimir_conferencia/{conferencia.pk}/').status_code == 200

    def test_autorizacao_do_coletor_abre(self, tela, conferencia):
        resposta = tela.client.get(f'/patrimonio/autorizar_coletor/{conferencia.pk}/')
        assert resposta.status_code == 200
        assert resposta.context['conferencia'] == conferencia

    def test_qrcode_da_conferencia_e_servido_como_imagem(self, tela, conferencia):
        resposta = tela.client.get(f'/patrimonio/conferencia_visualizar_qrcode/{conferencia.pk}/')
        assert resposta.status_code == 200
        assert resposta['Content-Type'] == 'image/png'

    def test_download_do_app_avisa_quando_nao_ha_apk_cadastrado(self, tela):
        resposta = tela.client.get('/patrimonio/baixar_app_conferencia')
        assert resposta.status_code == 302


class TestTelasDeRequisicaoERelatorio:
    def test_requisitar_transferencia_abre_para_quem_pode_requisitar(self, tela):
        assert tela.client.get('/patrimonio/requisitar_transferencia/').status_code == 200

    def test_requisitar_transferencia_recusa_quem_nao_pode(self, tela):
        """Sem ``change_requisicao`` a tela não nega acesso: redireciona com aviso."""
        tela.login(tela.servidor_outro_campus)
        tela.servidor_outro_campus.get_user().groups.clear()
        resposta = tela.client.get('/patrimonio/requisitar_transferencia/')
        assert resposta.status_code == 302

    def test_listagem_de_requisicoes_de_uso_pessoal_abre_vazia(self, tela):
        resposta = tela.client.get('/patrimonio/requisicao_inventario_uso_pessoal_listar/')
        assert resposta.status_code == 200
        assert list(resposta.context['requisicoes']) == []

    def test_inventarios_nao_conferidos_lista_os_depreciaveis_sem_conferencia(self, tela):
        resposta = tela.client.get('/patrimonio/relatorios/inventarios_nao_conferidos/', {'resultados_por_pagina': 50})
        assert resposta.status_code == 200
        assert tela.inventario in list(resposta.context['inventarios'])

    def test_totalizacao_por_elemento_de_despesa_abre_o_formulario(self, tela):
        assert tela.client.get('/patrimonio/total_ed_periodo/').status_code == 200

    def test_totalizacao_por_plano_de_contas_abre_o_formulario(self, tela):
        assert tela.client.get('/patrimonio/total_ed_periodo_planocontas/').status_code == 200


class TestReavaliacaoEAjuste:
    def test_tela_de_reavaliacao_abre(self, tela):
        resposta = tela.client.get(f'/patrimonio/inventario_reavaliar/{tela.inventario.pk}/')
        assert resposta.status_code == 200
        assert resposta.context['inventario'] == tela.inventario

    def test_tela_de_ajuste_de_valor_recuperavel_abre(self, tela):
        resposta = tela.client.get(f'/patrimonio/inventario_ajustar_valor/{tela.inventario.pk}/')
        assert resposta.status_code == 200
        assert resposta.context['inventario'] == tela.inventario

    def test_reavaliacao_exige_coordenacao(self, tela):
        tela.login(tela.servidor_outro_campus, 'Operador de Patrimônio')
        assert tela.client.get(f'/patrimonio/inventario_reavaliar/{tela.inventario.pk}/').status_code == 403
