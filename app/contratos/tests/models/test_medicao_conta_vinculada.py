from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import SimpleTestCase

from contratos.models import ContaVinculadaCalculo, Medicao, MedicaoTipoDocumentoComprobatorio


class FakeDocumentosQuerySet:
    def __init__(self, itens):
        self.itens = list(itens)

    def exists(self):
        return bool(self.itens)

    def filter(self, *args, **kwargs):
        if 'recebido_gerente__isnull' in kwargs:
            valor = kwargs['recebido_gerente__isnull']
            return FakeDocumentosQuerySet([item for item in self.itens if (item.recebido_gerente is None) is valor])
        if 'recebido_gerente' in kwargs:
            valor = kwargs['recebido_gerente']
            return FakeDocumentosQuerySet([item for item in self.itens if item.recebido_gerente == valor])
        return FakeDocumentosQuerySet(
            [item for item in self.itens if item.recebido_gerente in (None, '', MedicaoTipoDocumentoComprobatorio.PENDENTE)]
        )


class MedicaoContaVinculadaHelpersTest(SimpleTestCase):
    @staticmethod
    def _documento_provisorio_emitido() -> SimpleNamespace:
        return SimpleNamespace(estah_assinado=True, estah_finalizado=False)

    def test_termo_definitivo_permite_atualizacao_quando_documento_editavel(self):
        dummy = SimpleNamespace(
            termo_definitivo_documentotexto=SimpleNamespace(
                estah_aguardando_assinatura=False,
                estah_assinado=False,
                estah_finalizado=False,
            )
        )

        assert Medicao.termo_definitivo_permite_atualizacao(dummy) is True

    def test_termo_definitivo_permite_atualizacao_quando_documento_assinado_retorna_false(self):
        dummy = SimpleNamespace(
            termo_definitivo_documentotexto=SimpleNamespace(
                estah_aguardando_assinatura=False,
                estah_assinado=True,
                estah_finalizado=False,
            )
        )

        assert Medicao.termo_definitivo_permite_atualizacao(dummy) is False

    def test_pode_ser_recebida_definitivamente_respeita_trava_do_termo(self):
        documentos_para_recebimento = FakeDocumentosQuerySet([SimpleNamespace(recebido_gerente=None)])
        dummy = SimpleNamespace(
            recebimento_provisorio_emitido=lambda: True,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: True,
            get_documentos_comprobatorios_para_recebimento_definitivo=lambda: documentos_para_recebimento,
            termo_definitivo_permite_atualizacao=lambda: False,
        )

        assert Medicao.pode_ser_recebida_definitivamente(dummy) is False

    def test_foi_recebida_definitivamente_exige_avaliacao_do_gerente(self):
        documentos = FakeDocumentosQuerySet([SimpleNamespace(recebido_gerente=MedicaoTipoDocumentoComprobatorio.PENDENTE)])
        dummy = SimpleNamespace(
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: True,
            get_documentos_comprobatorios_para_recebimento_definitivo=lambda: documentos,
        )

        assert Medicao.foi_recebida_definitivamente(dummy) is False

    def test_foi_recebida_definitivamente_aceita_nao_se_aplica_do_gerente(self):
        documentos = FakeDocumentosQuerySet([SimpleNamespace(recebido_gerente=MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA_GERENTE)])
        dummy = SimpleNamespace(
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: True,
            get_documentos_comprobatorios_para_recebimento_definitivo=lambda: documentos,
        )

        assert Medicao.foi_recebida_definitivamente(dummy) is True

    def test_pode_gerar_termo_definitivo_depende_do_recebimento_e_do_status_do_documento(self):
        dummy = SimpleNamespace(
            recebimento_provisorio_emitido=lambda: True,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: True,
            foi_recebida_definitivamente=lambda: True,
            termo_definitivo_permite_atualizacao=lambda: True,
        )

        assert Medicao.pode_gerar_termo_definitivo(dummy) is True

    def test_pode_ser_recebida_definitivamente_sem_fluxo_de_documentos_nao_exibe_etapa_separada(self):
        dummy = SimpleNamespace(
            recebimento_provisorio_emitido=lambda: True,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: False,
        )

        assert Medicao.pode_ser_recebida_definitivamente(dummy) is False

    def test_pode_gerar_termo_definitivo_sem_mao_de_obra_depende_so_do_termo(self):
        dummy = SimpleNamespace(
            recebimento_provisorio_emitido=lambda: True,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: False,
            termo_definitivo_permite_atualizacao=lambda: True,
        )

        assert Medicao.pode_gerar_termo_definitivo(dummy) is True

    def test_recebimento_definitivo_exige_relatorio_provisorio_emitido(self) -> None:
        dummy = SimpleNamespace(
            recebimento_provisorio_emitido=lambda: False,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: False,
        )

        assert Medicao.pode_ser_recebida_definitivamente(dummy) is False
        assert Medicao.pode_gerar_termo_definitivo(dummy) is False

    def test_relatorio_provisorio_assinado_eh_considerado_emitido(self) -> None:
        dummy = SimpleNamespace(despacho_documentotexto=self._documento_provisorio_emitido())

        assert Medicao.recebimento_provisorio_emitido(dummy) is True

    def test_get_documentos_para_recebimento_sincroniza_documentos_faltantes_do_contrato(self):
        documentos = MagicMock()
        documentos.values_list.return_value = []
        documentos.all.return_value = ['doc-1']
        contrato = SimpleNamespace(mao_obra_exclusiva=True)
        dummy = SimpleNamespace(
            parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)),
            documentos_comprobatorios=documentos,
            usa_fluxo_recebimento_definitivo_com_documentos=lambda: True,
        )

        with (
            patch('contratos.models.ContratoTipoDocumentoComprobatorio.objects.filter') as filter_tipos,
            patch('contratos.models.MedicaoTipoDocumentoComprobatorio.objects.get_or_create') as get_or_create,
        ):
            filter_tipos.return_value.values_list.return_value = [10]

            resultado = Medicao.get_documentos_comprobatorios_para_recebimento_definitivo(dummy)

        assert resultado == ['doc-1']
        get_or_create.assert_called_once_with(
            medicao=dummy,
            tipo_documento_comprobatorio_id=10,
            defaults={'confirmacao_fiscal': MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA},
        )

    def test_usa_fluxo_documentos_retorna_false_sem_tipos_configurados_e_sem_documentos(self):
        documentos = MagicMock()
        documentos.exists.return_value = False
        contrato = SimpleNamespace(mao_obra_exclusiva=True)
        dummy = SimpleNamespace(
            parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)),
            documentos_comprobatorios=documentos,
        )

        with patch('contratos.models.ContratoTipoDocumentoComprobatorio.objects.filter') as filter_tipos:
            filter_tipos.return_value.exists.return_value = False

            resultado = Medicao.usa_fluxo_recebimento_definitivo_com_documentos(dummy)

        assert resultado is False

    def test_usa_fluxo_documentos_em_contrato_sem_mao_de_obra_com_checklist_configurado(self) -> None:
        contrato = SimpleNamespace(mao_obra_exclusiva=False)
        dummy = SimpleNamespace(
            parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)),
            documentos_comprobatorios=MagicMock(),
        )

        with patch('contratos.models.ContratoTipoDocumentoComprobatorio.objects.filter') as filter_tipos:
            filter_tipos.return_value.exists.return_value = True

            resultado = Medicao.usa_fluxo_recebimento_definitivo_com_documentos(dummy)

        assert resultado is True
        dummy.documentos_comprobatorios.exists.assert_not_called()

    def test_limpar_conta_vinculada_recebimento_definitivo_remove_calculos_e_depositos(self):
        conta_vinculada_calculos = MagicMock()
        movimentacoes_conta = MagicMock()
        dummy = SimpleNamespace(
            conta_vinculada_calculos=conta_vinculada_calculos,
            movimentacoes_conta=movimentacoes_conta,
        )

        Medicao.limpar_conta_vinculada_recebimento_definitivo(dummy)

        conta_vinculada_calculos.all.return_value.delete.assert_called_once_with()
        movimentacoes_conta.filter.assert_called_once_with(deposito=True)
        movimentacoes_conta.filter.return_value.delete.assert_called_once_with()

    def test_tabela_conta_vinculada_termo_definitivo_html_exibe_resumo_e_itens(self):
        itens = MagicMock()
        itens.all.return_value = [
            SimpleNamespace(
                maodeobra='Trabalhador A',
                salario=Decimal('1000.00'),
                valor_13=Decimal('10.00'),
                valor_ferias=Decimal('11.00'),
                valor_fgts=Decimal('12.00'),
                valor_submodulo=Decimal('13.00'),
                total_item=Decimal('46.00'),
            )
        ]
        calculo = SimpleNamespace(itens=itens, valor_total=Decimal('46.00'))

        movimentacoes_conta = MagicMock()
        movimentacoes_conta.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(data=date(2026, 5, 20))

        dummy = SimpleNamespace(
            get_ultimo_calculo_conta_vinculada=lambda: calculo,
            movimentacoes_conta=movimentacoes_conta,
        )

        html = Medicao.tabela_conta_vinculada_termo_definitivo_html.fget(dummy)

        assert 'Demonstrativo da Conta Vinculada da Medicao' not in html
        assert '3 - Demonstrativo da Conta Vinculada da Medição' in html
        assert 'Valor recolhido na conta vinculada nesta medição' in html
        assert 'Trabalhador A' in html
        assert '20/05/2026' in html

    def test_posicionar_tabela_conta_vinculada_insere_entre_quadro_valor_final_e_declaracao(self):
        corpo = (
            '<table><tr><td>2- VALOR FINAL DA NOTA APLICANDO O IMR</td></tr></table>'
            '<table><tr><td>DECLARA&Ccedil;&Atilde;O DE RECEBIMENTO DEFINITIVO</td></tr></table>'
        )
        tabela_conta_vinculada = '<div class="conta-vinculada-medicao">Conta vinculada</div>'

        html = Medicao.posicionar_tabela_conta_vinculada_termo_definitivo(corpo, tabela_conta_vinculada)

        assert html.index('2- VALOR FINAL DA NOTA APLICANDO O IMR') < html.index('Conta vinculada')
        assert html.index('Conta vinculada') < html.index('DECLARA&Ccedil;&Atilde;O DE RECEBIMENTO DEFINITIVO')

    def test_posicionar_tabela_conta_vinculada_usa_quadro_valor_final_quando_declaracao_nao_for_encontrada(self):
        corpo = '<table><tr><td>2- VALOR FINAL DA NOTA APLICANDO O IMR</td></tr></table><p>Outro conteúdo</p>'
        tabela_conta_vinculada = '<div class="conta-vinculada-medicao">Conta vinculada</div>'

        html = Medicao.posicionar_tabela_conta_vinculada_termo_definitivo(corpo, tabela_conta_vinculada)

        assert html.index('</table>') < html.index('Conta vinculada')
        assert html.index('Conta vinculada') < html.index('Outro conteúdo')

    def test_atualizar_tabela_conta_vinculada_altera_apenas_corpo_do_documento(self) -> None:
        documento = SimpleNamespace(
            cabecalho='Cabecalho original {{ documento_identificador }}',
            corpo='<p>Corpo</p>',
            rodape='Rodape original {{ documento_identificador }}',
            cabecalho_base_original=object(),
            rodape_base_original=object(),
        )
        cabecalho_original = documento.cabecalho
        rodape_original = documento.rodape
        cabecalho_base_original = documento.cabecalho_base_original
        rodape_base_original = documento.rodape_base_original
        medicao = SimpleNamespace(
            tabela_conta_vinculada_termo_definitivo_html='<div class="conta-vinculada-medicao">Conta vinculada</div>',
            posicionar_tabela_conta_vinculada_termo_definitivo=Medicao.posicionar_tabela_conta_vinculada_termo_definitivo,
        )

        Medicao.atualizar_tabela_conta_vinculada_termo_definitivo_documento(medicao, documento)

        assert 'Conta vinculada' in documento.corpo
        assert documento.cabecalho == cabecalho_original
        assert documento.rodape == rodape_original
        assert documento.cabecalho_base_original is cabecalho_base_original
        assert documento.rodape_base_original is rodape_base_original

    def test_registrar_estorno_conta_vinculada_por_exclusao_gera_movimentacao_inversa_com_observacao(self):
        movimentacao = SimpleNamespace(
            conta='conta-x',
            deposito=True,
            valor='123.45',
            fiscal='fiscal-original',
            servidor='servidor-original',
        )
        manager = MagicMock()
        manager.select_related.return_value.order_by.return_value = [movimentacao]
        dummy = SimpleNamespace(
            pk=99,
            numero_documento='NF-001',
            data_inicio=date(2026, 5, 1),
            data_fim=date(2026, 5, 31),
            movimentacoes_conta=manager,
        )

        with patch('contratos.models.MovimentacaoContaContrato.objects.create') as create:
            total = Medicao.registrar_estorno_conta_vinculada_por_exclusao(dummy, fiscal='fiscal-novo', servidor='servidor-novo')

        assert total == 1
        create.assert_called_once()
        kwargs = create.call_args.kwargs
        assert kwargs['conta'] == 'conta-x'
        assert kwargs['medicao'] is None
        assert kwargs['deposito'] is False
        assert kwargs['valor'] == '123.45'
        assert kwargs['fiscal'] == 'fiscal-novo'
        assert kwargs['servidor'] == 'servidor-novo'
        assert 'exclusão da medição NF-001' in kwargs['observacao']

    def test_calcular_conta_vinculada_aplica_overrides_explicitos(self):
        class FakeQuerySet(list):
            def filter(self, id__in=None):
                if id__in is None:
                    return self
                return FakeQuerySet([item for item in self if item.id in id__in])

        mao = SimpleNamespace(id=1, salario_bruto=Decimal('1000.00'))
        contrato = SimpleNamespace(maosdeobra=SimpleNamespace(all=lambda: FakeQuerySet([mao])), grau_risco=1)
        medicao = SimpleNamespace(parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)))

        with patch('contratos.models.Configuracao.get_valor_por_chave', return_value=None):
            resultado = Medicao.calcular_conta_vinculada(
                medicao,
                per_item_overrides={
                    '1': {
                        'salario': '3000.00',
                        'valor_13': '250.00',
                        'valor_ferias': '500.00',
                        'valor_fgts': '240.00',
                        'valor_submodulo': '150.00',
                        'modo': 'manual',
                        'tipo': 'manual',
                        'justificativa': 'Ajuste do gestor.',
                    }
                },
            )

        item = resultado['itens'][0]
        assert item['salario'] == '3000.00'
        assert item['valor_13'] == '250.00'
        assert item['valor_ferias'] == '500.00'
        assert item['valor_fgts'] == '240.00'
        assert item['valor_submodulo'] == '150.00'
        assert item['total_item'] == '1140.00'
        assert item['modo'] == 'manual'
        assert item['tipo'] == 'manual'
        assert item['justificativa'] == 'Ajuste do gestor.'

    def test_calcular_conta_vinculada_usa_percentual_padrao_corrigido_de_ferias(self):
        class FakeQuerySet(list):
            def filter(self, id__in=None):
                if id__in is None:
                    return self
                return FakeQuerySet([item for item in self if item.id in id__in])

        mao = SimpleNamespace(id=1, salario_bruto=Decimal('1000.00'))
        contrato = SimpleNamespace(maosdeobra=SimpleNamespace(all=lambda: FakeQuerySet([mao])), grau_risco=1)
        medicao = SimpleNamespace(parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)))

        with patch('contratos.models.Configuracao.get_valor_por_chave', return_value=None):
            resultado = Medicao.calcular_conta_vinculada(medicao)

        item = resultado['itens'][0]
        assert item['valor_ferias'] == '121.00'
        assert resultado['percentuais']['perc_ferias'] == '0.121000'

    def test_calcular_conta_vinculada_com_lista_vazia_retorna_total_zero(self):
        class FakeQuerySet(list):
            def filter(self, id__in=None):
                if id__in is None:
                    return self
                return FakeQuerySet([item for item in self if item.id in id__in])

        mao = SimpleNamespace(id=1, salario_bruto=Decimal('1000.00'))
        contrato = SimpleNamespace(maosdeobra=SimpleNamespace(all=lambda: FakeQuerySet([mao])), grau_risco=1)
        medicao = SimpleNamespace(parcela=SimpleNamespace(cronograma=SimpleNamespace(contrato=contrato)))

        with patch('contratos.models.Configuracao.get_valor_por_chave', return_value=None):
            resultado = Medicao.calcular_conta_vinculada(medicao, maosdeobra_ids=[])

        assert resultado['itens'] == []
        assert resultado['totais']['valor_total'] == '0.00'
        assert resultado['totais']['quantidade_itens'] == 0


class ContaVinculadaCalculoHelpersTest(SimpleTestCase):
    def test_obter_percentuais_para_contrato_usa_novos_padroes_fgts_e_submodulo(self):
        contrato = SimpleNamespace(grau_risco=3)

        with patch('contratos.models.Configuracao.get_valor_por_chave', return_value=None):
            percentuais = ContaVinculadaCalculo.obter_percentuais_para_contrato(contrato)

        assert percentuais['perc_fgts'] == Decimal('0.04')
        assert percentuais['perc_submodulo'] == Decimal('0.0782')

    def test_contas_relacionadas_display_lista_contas_unicas_da_medicao(self):
        conta_a = SimpleNamespace(id=1, descricao='001')
        conta_b = SimpleNamespace(id=2, descricao='002')
        movimentacoes = [
            SimpleNamespace(conta_id=1, conta=conta_a, deposito=True),
            SimpleNamespace(conta_id=1, conta=conta_a, deposito=True),
            SimpleNamespace(conta_id=2, conta=conta_b, deposito=True),
            SimpleNamespace(conta_id=2, conta=conta_b, deposito=False),
        ]
        calculo = SimpleNamespace(
            medicao_id=10,
            medicao=SimpleNamespace(movimentacoes_conta=SimpleNamespace(all=lambda: movimentacoes)),
        )

        contas = ContaVinculadaCalculo.contas_relacionadas.fget(calculo)
        calculo.contas_relacionadas = contas
        display = ContaVinculadaCalculo.contas_relacionadas_display.fget(calculo)

        assert contas == [conta_a, conta_b]
        assert display == '001 | 002'


class TabelaDocumentosComprobatoriosHelperTest(SimpleTestCase):
    def test_monta_tabela_com_mensagem_quando_nao_ha_checklist(self):
        html = Medicao.montar_tabela_documentos_comprobatorios(
            docs_medicao=[],
            titulo_coluna_status='REVISADO?',
            status_getter=lambda doc: '',
            mensagem_vazia='Nenhum checklist de fiscalização foi cadastrado para esta medição.',
        )

        assert 'Nenhum checklist de fiscalização foi cadastrado para esta medição.' in html
        assert 'REVISADO?' in html
