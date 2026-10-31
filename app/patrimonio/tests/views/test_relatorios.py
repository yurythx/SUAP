"""Telas e PDFs de ``patrimonio.relatorio``.

São documentos assinados: termo de responsabilidade, nada consta, termo de transferência,
relatório de baixa e as totalizações contábeis. Aqui a pergunta é se cada um abre com os
dados do cenário e se quem não tem ``pode_ver_relatorios`` é barrado — quebra de template
ou de queryset nesses relatórios só aparece na hora de imprimir.
"""

import datetime

import pytest

from patrimonio.models import Inventario, InventarioStatus, MovimentoPatrim, MovimentoPatrimTipo, Requisicao, RequisicaoHistorico
from comum.models import Configuracao
from djtools.utils import cache
from patrimonio.tests.factories import (
    BaixaFactory,
    CautelaFactory,
    CautelaInventarioFactory,
    InventarioValorFactory,
    RequisicaoFactory,
    RequisicaoItemFactory,
)

COORDENADOR = 'Coordenador de Patrimônio'
ENTRADA = datetime.datetime(2020, 3, 5, 9, 0)


@pytest.fixture
def relatorio(patrimonio_context):
    """Coordenador logado com um bem ativo sob sua carga, já movimentado."""
    contexto = patrimonio_context
    contexto.login(contexto.servidor, COORDENADOR)
    inventario = contexto.item_a.inventario_set.order_by('numero').first()
    Inventario.objects.filter(pk=inventario.pk).update(status=InventarioStatus.ATIVO(), responsavel_vinculo=contexto.servidor.get_vinculo())
    inventario.refresh_from_db()
    MovimentoPatrim.objects.create(
        inventario=inventario, tipo=MovimentoPatrimTipo.TRANSFERENCIA(), vinculo=contexto.servidor.get_vinculo(), data=ENTRADA
    )
    contexto.inventario = inventario
    return contexto


class TestTermos:
    def test_tela_de_termos_abre_com_o_formulario(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/termos/')
        assert resposta.status_code == 200

    def test_termo_de_responsabilidade_lista_a_carga_do_servidor(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/termos/', {'servidor': relatorio.servidor.pk, 'tipo': 'responsabilidade'})
        assert resposta.status_code == 200
        assert str(relatorio.inventario.numero) in resposta.content.decode()

    def test_termo_anual_exige_o_ano(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/termos/', {'servidor': relatorio.servidor.pk, 'tipo': 'anual'})
        assert resposta.status_code == 200
        assert 'Obrigatório' in resposta.content.decode()

    def test_termo_de_recebimento_exige_o_periodo(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/termos/', {'servidor': relatorio.servidor.pk, 'tipo': 'recebimento'})
        assert resposta.status_code == 200
        assert 'Obrigatório' in resposta.content.decode()

    def test_termos_recusa_quem_nao_ve_relatorios(self, relatorio):
        relatorio.login(relatorio.servidor_outro_campus)
        relatorio.servidor_outro_campus.get_user().groups.clear()
        resposta = relatorio.client.get('/patrimonio/termos/')
        assert resposta.status_code == 302

    def test_nada_consta_de_desligamento_sai_em_pdf(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/relatorio/termos_pdf/', {'servidor': relatorio.servidor.pk, 'tipo': 'nada_consta_desligamento'})
        assert resposta.status_code == 200
        assert resposta['Content-Type'] == 'application/pdf'

    def test_termo_de_responsabilidade_em_pdf_roda_como_tarefa(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/relatorio/termos_pdf/', {'servidor': relatorio.servidor.pk, 'tipo': 'responsabilidade'})
        assert resposta.status_code == 302
        assert resposta.url.startswith('/djtools/process/')


class TestTotalizacoes:
    def test_totalizacao_por_periodo_abre_o_formulario(self, relatorio):
        assert relatorio.client.get('/patrimonio/total_periodo/').status_code == 200

    def test_totalizacao_por_periodo_lista_os_meses_do_ano(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/total_periodo/', {'ano': 2020})
        assert resposta.status_code == 200
        assert len(resposta.context['meses']) == 12

    def test_totalizacao_por_periodo_recusa_ano_futuro(self, relatorio):
        futuro = datetime.date.today().year + 1
        resposta = relatorio.client.get('/patrimonio/total_periodo/', {'ano': futuro})
        assert resposta.status_code == 200
        assert 'escolha um anterior' in resposta.content.decode()

    def test_totalizacao_por_campus_abre_o_formulario(self, relatorio):
        assert relatorio.client.get('/patrimonio/total_campus/').status_code == 200

    def test_totalizacao_por_campus_roda_como_tarefa(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/total_campus/', {'campus': relatorio.campus.pk, 'mes': 3, 'ano': 2020})
        assert resposta.status_code == 302
        assert resposta.url.startswith('/djtools/process/')

    def test_acumulado_por_elemento_de_despesa_ate_o_mes(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/total_ed_acumulado_ateh_periodo/3/2020/')
        assert resposta.status_code == 200
        assert 'Março/2020' in resposta.content.decode()

    def test_acumulado_por_elemento_de_despesa_sai_em_pdf_apos_a_consulta(self, relatorio):
        """O PDF lê mês e ano da sessão: sem consultar antes, a requisição é inválida."""
        relatorio.client.get('/patrimonio/total_ed_acumulado_ateh_periodo/3/2020/')

        resposta = relatorio.client.get('/patrimonio/total_ed_acumulado_ateh_periodo_pdf/')

        assert resposta['Content-Type'] == 'application/pdf'

    def test_pdf_do_acumulado_sem_consulta_previa_e_recusado(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/total_ed_acumulado_ateh_periodo_pdf/')
        assert resposta.status_code == 302

    def test_totalizacao_por_elemento_de_despesa_do_mes(self, relatorio):
        resposta = relatorio.client.get('/patrimonio/total_ed_periodo/', {'mes': 3, 'ano': 2020, 'doacoes': 'on'})
        assert resposta.status_code == 200
        assert resposta.context['mes'] == 'Março'

    def test_detalhamento_da_categoria_no_campus(self, relatorio):
        url = f'/patrimonio/detalhamento_categoria/{relatorio.categoria.pk}/{relatorio.campus.pk}/2020-12-31/'
        resposta = relatorio.client.get(url)
        assert resposta.status_code == 200


@pytest.fixture
def instituicao_configurada(db):
    """Nome da instituição, que os termos imprimem no corpo do PDF.

    ``Configuracao.get_valor_por_chave`` lê de um cache de processo, então criar a linha
    não basta: sem invalidar, o PDF sai com ``None`` e o relatório estoura.
    """
    Configuracao.objects.update_or_create(app='comum', chave='instituicao', defaults={'valor': 'IFRN'})
    cache.delete('_CONFIGURACAO_CACHED')


class TestDocumentosEmPdf:
    def test_relatorio_de_baixa(self, relatorio):
        baixa = BaixaFactory(uo=relatorio.campus)
        resposta = relatorio.client.get(f'/patrimonio/relatorioBaixaPDF/{baixa.pk}/')
        assert resposta['Content-Type'] == 'application/pdf'

    def test_termo_de_cautela(self, relatorio, instituicao_configurada):
        cautela = CautelaFactory()
        CautelaInventarioFactory(cautela=cautela, inventario=relatorio.inventario)

        resposta = relatorio.client.get(f'/patrimonio/relatorio/termo_cautela_PDF/{cautela.pk}/')

        assert resposta['Content-Type'] == 'application/pdf'

    def test_termo_de_transferencia(self, relatorio):
        requisicao = RequisicaoFactory(
            vinculo_origem=relatorio.servidor.get_vinculo(),
            vinculo_destino=relatorio.servidor_outro_campus.get_vinculo(),
            status=Requisicao.STATUS_DEFERIDA,
            campus_origem=relatorio.campus,
            campus_destino=relatorio.outro_campus,
        )
        RequisicaoItemFactory(requisicao=requisicao, inventario=relatorio.inventario)
        RequisicaoHistorico.objects.create(requisicao=requisicao, status=Requisicao.STATUS_DEFERIDA, alterado_em=datetime.datetime.now())

        resposta = relatorio.client.get(f'/patrimonio/relatorio/transferencia/{requisicao.pk}/')

        assert resposta['Content-Type'] == 'application/pdf'


class TestDepreciacao:
    def test_relatorio_por_item_abre_o_formulario(self, relatorio):
        assert relatorio.client.get('/patrimonio/inventario_depreciacao/').status_code == 200

    def test_relatorio_por_contas_contabeis_abre_o_formulario(self, relatorio):
        assert relatorio.client.get('/patrimonio/inventario_depreciacao_planocontabil_novo/').status_code == 200

    def test_relatorio_por_contas_contabeis_recusa_mes_sem_depreciacao(self, relatorio):
        resposta = relatorio.client.get(
            '/patrimonio/inventario_depreciacao_planocontabil_novo/', {'mes': 3, 'ano': 2020, 'campus': relatorio.campus.pk}
        )
        assert resposta.status_code == 200
        assert 'Não existe depreciação para este mês/ano informado.' in resposta.content.decode()

    def test_relatorio_por_contas_contabeis_roda_como_tarefa_quando_ha_depreciacao(self, relatorio):
        InventarioValorFactory(inventario=relatorio.inventario, uo=relatorio.campus, data=datetime.date(2020, 3, 31))

        resposta = relatorio.client.get(
            '/patrimonio/inventario_depreciacao_planocontabil_novo/', {'mes': 3, 'ano': 2020, 'campus': relatorio.campus.pk}
        )

        assert resposta.status_code == 302
        assert resposta.url.startswith('/djtools/process/')
