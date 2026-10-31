from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from comum.tests.factories import AnoFactory
from plan_estrategico.models import (
    Indicador,
    NotaEmpenho,
    RequisicaoDespesa,
    TematicaVariavel,
    UnidadeGestora,
    Variavel,
    VariavelCampus,
    get_siglas_formula,
)
from plan_estrategico.tests.factories import PDIFactory, UnidadeGestoraFactory
from rh.models import Atividade, Setor, UnidadeOrganizacional
from rh.tests.factories import ServidorFactory, ServidorFuncaoHistoricoFactory, SetorFactory, SetorSiapeFactory


class RequisicaoDespesaGetDocumentoEmpenhoTesouroTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa(tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO)
        self.empenho_plan = mock.Mock(numero_empenho='2025NE000001', numero_ro=None)
        self.empenho_com_ro = mock.Mock(numero_empenho='2025NE000001', numero_ro='2025RO000001')

    def test_dotacao_empenho_encontra_documento(self):
        mock_queryset = mock.Mock()
        mock_queryset.exists.return_value = True
        mock_queryset.first.return_value = 'documento_encontrado'
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter', return_value=mock_queryset) as mock_filter:
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_plan)
            mock_filter.assert_called_once_with(numero='2025NE000001')
            assert result == 'documento_encontrado'

    def test_dotacao_empenho_nao_encontra_documento(self):
        mock_queryset = mock.Mock()
        mock_queryset.exists.return_value = False
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter', return_value=mock_queryset):
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_plan)
            assert result is None

    def test_reforco_empenho_busca_por_numero_ro(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_REFORCO_EMPENHO
        mock_queryset = mock.Mock()
        mock_queryset.exists.return_value = True
        mock_queryset.first.return_value = 'documento_reforco'
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter', return_value=mock_queryset) as mock_filter:
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_com_ro)
            mock_filter.assert_called_once_with(numero='2025RO000001')
            assert result == 'documento_reforco'

    def test_anulacao_empenho_busca_por_numero_ro(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_ANULACAO_EMPENHO
        mock_queryset = mock.Mock()
        mock_queryset.exists.return_value = True
        mock_queryset.first.return_value = 'documento_anulacao'
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter', return_value=mock_queryset) as mock_filter:
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_com_ro)
            mock_filter.assert_called_once_with(numero='2025RO000001')
            assert result == 'documento_anulacao'

    def test_linha_de_reforco_em_dotacao_busca_por_numero_ro(self):
        mock_queryset = mock.Mock()
        mock_queryset.exists.return_value = True
        mock_queryset.first.return_value = 'documento_reforco'
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter', return_value=mock_queryset) as mock_filter:
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_com_ro)
            mock_filter.assert_called_once_with(numero='2025RO000001')
            assert result == 'documento_reforco'

    def test_tipo_desconhecido_retorna_none(self):
        self.requisicao.tipo_requisicao = 999
        with mock.patch('plan_estrategico.models.DocumentoEmpenho.objects.filter') as mock_filter:
            result = self.requisicao.get_documento_empenho_tesouro(self.empenho_plan)
            mock_filter.assert_not_called()
            assert result is None


class RequisicaoDespesaGetDocumentosEmpenhoTesouroTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa(tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO)
        self.empenho1 = mock.Mock(numero_empenho='NE001', numero_ro=None)
        self.empenho2 = mock.Mock(numero_empenho='NE002', numero_ro=None)

    def test_dotacao_empenho_filtra_por_numero_empenho(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
        mock_none = mock.Mock()
        mock_none.none.return_value = 'empty_qs'
        mock.Mock()
        with (
            mock.patch.object(RequisicaoDespesa, 'empenhos', new_callable=mock.PropertyMock) as mock_empenhos,
            mock.patch('plan_estrategico.models.DocumentoEmpenho.objects') as mock_de_objects,
        ):
            mock_empenhos.return_value.all.return_value = [self.empenho1, self.empenho2]
            mock_de_objects.none.return_value = 'empty_qs'
            mock_de_objects.filter.return_value = 'documentos_encontrados'
            result = self.requisicao.get_documentos_empenho_tesouro()
            mock_de_objects.filter.assert_called_once_with(numero__in=['NE001', 'NE002'])
            assert result == 'documentos_encontrados'

    def test_reforco_empenho_filtra_por_numero_ro(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_REFORCO_EMPENHO
        empenho_a = mock.Mock(numero_ro='RO001')
        empenho_b = mock.Mock(numero_ro='RO002')
        with (
            mock.patch.object(RequisicaoDespesa, 'empenhos', new_callable=mock.PropertyMock) as mock_empenhos,
            mock.patch('plan_estrategico.models.DocumentoEmpenho.objects') as mock_de_objects,
        ):
            mock_empenhos.return_value.all.return_value = [empenho_a, empenho_b]
            mock_de_objects.none.return_value = 'empty_qs'
            mock_de_objects.filter.return_value = 'documentos_encontrados'
            result = self.requisicao.get_documentos_empenho_tesouro()
            mock_de_objects.filter.assert_called_once_with(numero__in=['RO001', 'RO002'])
            assert result == 'documentos_encontrados'

    def test_dotacao_com_linha_de_reforco_mistura_empenho_e_ro(self):
        reforco = mock.Mock(numero_empenho='NE001', numero_ro='RO001')
        with (
            mock.patch.object(RequisicaoDespesa, 'empenhos', new_callable=mock.PropertyMock) as mock_empenhos,
            mock.patch('plan_estrategico.models.DocumentoEmpenho.objects') as mock_de_objects,
        ):
            mock_empenhos.return_value.all.return_value = [self.empenho1, reforco]
            mock_de_objects.filter.return_value = 'documentos_encontrados'
            result = self.requisicao.get_documentos_empenho_tesouro()
            mock_de_objects.filter.assert_called_once_with(numero__in=['NE001', 'RO001'])
            assert result == 'documentos_encontrados'

    def test_sem_empenhos_retorna_queryset_vazio(self):
        with (
            mock.patch.object(RequisicaoDespesa, 'empenhos', new_callable=mock.PropertyMock) as mock_empenhos,
            mock.patch('plan_estrategico.models.DocumentoEmpenho.objects') as mock_de_objects,
        ):
            mock_empenhos.return_value.all.return_value = []

            mock_filter = mock.MagicMock()
            mock_de_objects.filter.return_value = mock_filter

            result = self.requisicao.get_documentos_empenho_tesouro()

            assert result == mock_filter

            mock_de_objects.filter.assert_called_once_with(numero__in=[])


class RequisicaoDespesaGetEventoEmpenhoTesouroTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa()

    def test_dotacao_empenho_retorna_inclusao(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO
        assert self.requisicao.get_evento_empenho_tesouro() == 401201

    def test_reforco_empenho_retorna_reforco(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_REFORCO_EMPENHO
        assert self.requisicao.get_evento_empenho_tesouro() == 401202

    def test_anulacao_empenho_retorna_anulacao(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_ANULACAO_EMPENHO
        assert self.requisicao.get_evento_empenho_tesouro() == 401203

    def test_dotacao_provisoria_retorna_none(self):
        self.requisicao.tipo_requisicao = RequisicaoDespesa.TIPO_DOTACAO_PROVISORIA
        assert self.requisicao.get_evento_empenho_tesouro() is None

    def test_tipo_desconhecido_retorna_none(self):
        self.requisicao.tipo_requisicao = 999
        assert self.requisicao.get_evento_empenho_tesouro() is None


class RequisicaoDespesaGetValorDocumentoEmpenhoTesouroTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa(tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO)
        self.empenho_tesouro = mock.Mock()

    def test_dotacao_empenho_filtra_por_documento_inicial(self):
        mock_item_qs = mock.Mock()
        mock_item_qs.filter.return_value = mock_item_qs
        mock_item_qs.aggregate.return_value = {'valor__sum': 15000.00}
        with (
            mock.patch.object(self.requisicao, 'get_evento_empenho_tesouro', return_value=401201),
            mock.patch('plan_estrategico.models.DocumentoEmpenhoItem.objects.filter', return_value=mock_item_qs) as mock_filter,
        ):
            result = self.requisicao.get_valor_documento_empenho_tesouro(self.empenho_tesouro)
            mock_filter.assert_called_once_with(evento__codigo=401201)
            assert result == 15000.00

    def test_linha_de_reforco_em_dotacao_usa_evento_de_reforco(self):
        mock_item_qs = mock.Mock()
        mock_item_qs.filter.return_value = mock_item_qs
        mock_item_qs.aggregate.return_value = {'valor__sum': 5000.00}
        linha_reforco = mock.Mock(numero_empenho='2025NE000001', numero_ro='2025RO000001')
        with mock.patch('plan_estrategico.models.DocumentoEmpenhoItem.objects.filter', return_value=mock_item_qs) as mock_filter:
            result = self.requisicao.get_valor_documento_empenho_tesouro(self.empenho_tesouro, linha_reforco)
            mock_filter.assert_called_once_with(evento__codigo=401202)
            mock_item_qs.filter.assert_called_once_with(documento_empenho=self.empenho_tesouro)
            assert result == 5000.00

    def test_dotacao_empenho_sem_valor_retorna_zero(self):
        mock_item_qs = mock.Mock()
        mock_item_qs.filter.return_value = mock_item_qs
        mock_item_qs.aggregate.return_value = {'valor__sum': None}
        with (
            mock.patch.object(self.requisicao, 'get_evento_empenho_tesouro', return_value=401201),
            mock.patch('plan_estrategico.models.DocumentoEmpenhoItem.objects.filter', return_value=mock_item_qs),
        ):
            result = self.requisicao.get_valor_documento_empenho_tesouro(self.empenho_tesouro)
            assert result == 0


class RequisicaoDespesaValidarRequisicaoTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa(
            tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
            status=RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
        )

    def test_early_return_quando_status_nao_aguardando_validacao(self):
        self.requisicao.status = RequisicaoDespesa.STATUS_CADASTRADA
        self.requisicao.validar_requisicao()
        assert self.requisicao.status == RequisicaoDespesa.STATUS_CADASTRADA


class RequisicaoDespesaPodeEditarEmpenhoTest:
    def setup_method(self):
        self.requisicao = RequisicaoDespesa(
            tipo_requisicao=RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
            status=RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
        )
        self.usuario = mock.Mock()
        self.usuario.get_vinculo.return_value.relacionamento.setor.sigla = 'DIAD'

    def executar(self, eh_executor: bool = True, pode_emitir: bool = False, sigla_setor_financeiro: str | None = 'DIAD') -> bool:
        with (
            mock.patch('plan_estrategico.models.tl.get_user', return_value=self.usuario),
            mock.patch('plan_estrategico.models.in_group', return_value=eh_executor),
            mock.patch.object(RequisicaoDespesa, 'pode_emitir_empenho', return_value=pode_emitir),
            mock.patch.object(RequisicaoDespesa, 'unidade_gestora', new_callable=mock.PropertyMock) as mock_unidade_gestora,
        ):
            if sigla_setor_financeiro is None:
                mock_unidade_gestora.return_value.setor_financeiro = None
            else:
                mock_unidade_gestora.return_value.setor_financeiro = mock.Mock(sigla=sigla_setor_financeiro)
            return self.requisicao.pode_editar_empenho()

    def test_permite_editar_quando_aguardando_validacao(self):
        assert self.executar() is True

    def test_nao_permite_editar_quando_usuario_nao_eh_executor_orcamentario(self):
        assert self.executar(eh_executor=False) is False

    def test_nao_permite_editar_quando_setor_do_usuario_difere_do_setor_financeiro(self):
        assert self.executar(sigla_setor_financeiro='DIREX') is False

    def test_nao_permite_editar_quando_unidade_gestora_sem_setor_financeiro(self):
        assert self.executar(sigla_setor_financeiro=None) is False

    def test_nao_permite_editar_em_status_sem_previsao(self):
        self.requisicao.status = RequisicaoDespesa.STATUS_CONCLUIDA
        assert self.executar() is False

    def test_permite_editar_quando_pode_emitir_empenho(self):
        self.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO
        assert self.executar(eh_executor=False, pode_emitir=True) is True


class NotaEmpenhoPodeReforcarTest:
    def setup_method(self):
        self.nota = NotaEmpenho(numero_empenho='2025NE000001')

    def executar(
        self,
        tipo_requisicao: int = RequisicaoDespesa.TIPO_DOTACAO_EMPENHO,
        pode_editar: bool = True,
    ) -> bool:
        with mock.patch.object(NotaEmpenho, 'requisicao', new_callable=mock.PropertyMock) as mock_requisicao:
            requisicao = mock.Mock(tipo_requisicao=tipo_requisicao)
            requisicao.pode_editar_empenho.return_value = pode_editar
            mock_requisicao.return_value = requisicao
            return self.nota.pode_reforcar()

    def test_permite_reforcar_na_linha_do_empenho_emitido(self):
        assert self.executar() is True

    def test_nao_permite_reforcar_em_requisicao_que_nao_eh_de_dotacao(self):
        assert self.executar(tipo_requisicao=RequisicaoDespesa.TIPO_REFORCO_EMPENHO) is False

    def test_nao_permite_reforcar_quando_a_requisicao_nao_permite_editar_o_empenho(self):
        assert self.executar(pode_editar=False) is False

    def test_nao_permite_reforcar_a_partir_de_uma_linha_de_reforco(self):
        self.nota.numero_ro = '2025RO000001'
        assert self.executar() is False

    def test_nao_permite_reforcar_antes_da_emissao_do_empenho(self):
        self.nota.numero_empenho = None
        assert self.executar() is False


class GetSiglasFormulaTest:
    def test_descarta_operadores_parenteses_e_constantes_inteiras(self):
        assert get_siglas_formula('(MAT_CONC / MAT_TOT) * 100') == ['MAT_CONC', 'MAT_TOT']

    def test_descarta_constante_decimal(self):
        assert get_siglas_formula('TX_EVASAO * 100.0') == ['TX_EVASAO']

    def test_ignora_token_vazio_de_operador_unario(self):
        assert get_siglas_formula('-NUM_ALUNOS + 1') == ['NUM_ALUNOS']

    def test_nao_repete_sigla(self):
        assert get_siglas_formula('MAT_TOT / MAT_TOT') == ['MAT_TOT']

    def test_formula_vazia(self):
        assert get_siglas_formula('') == []


class IndicadorGetVariaveisTest:
    def setup_method(self):
        self.indicador = Indicador(forma_calculo='(MAT_CONC / MAT_TOT) * 100')

    def executar(self, cadastradas):
        def get(sigla):
            if sigla not in cadastradas:
                raise Variavel.DoesNotExist
            return cadastradas[sigla]

        with mock.patch('plan_estrategico.models.Variavel.objects.get', side_effect=get):
            return self.indicador.get_variaveis()

    def test_retorna_as_variaveis_da_formula(self):
        cadastradas = {'MAT_CONC': mock.Mock(), 'MAT_TOT': mock.Mock()}
        assert self.executar(cadastradas) == [cadastradas['MAT_CONC'], cadastradas['MAT_TOT']]

    def test_retorna_vazio_quando_alguma_sigla_nao_esta_cadastrada(self):
        assert self.executar({'MAT_CONC': mock.Mock()}) == []

    def test_constante_decimal_nao_invalida_a_formula(self):
        self.indicador.forma_calculo = 'TX_EVASAO * 100.0'
        cadastradas = {'TX_EVASAO': mock.Mock()}
        assert self.executar(cadastradas) == [cadastradas['TX_EVASAO']]


class IndicadorCleanTest:
    def executar(self, forma_calculo, calcular_media=True):
        indicador = Indicador(sigla='TX', descricao='Taxa', forma_calculo=forma_calculo, calcular_media=calcular_media)
        with mock.patch('plan_estrategico.models.ModelPlus.clean'):
            indicador.clean()

    def test_aceita_media_com_uma_unica_variavel_e_constante_decimal(self):
        self.executar('TX_EVASAO * 100.0')

    def test_rejeita_media_com_duas_variaveis(self):
        with pytest.raises(ValidationError) as excecao:
            self.executar('(MAT_CONC / MAT_TOT) * 100')
        assert 'calcular_media' in excecao.value.message_dict

    def test_nao_valida_formula_quando_media_desmarcada(self):
        self.executar('(MAT_CONC / MAT_TOT) * 100', calcular_media=False)


class UnidadeGestoraEhDiretorTest:
    def setup_method(self):
        self.setor = mock.Mock()
        self.unidade_gestora = UnidadeGestora()
        self.unidade_gestora._state.fields_cache['setor_equivalente'] = self.setor

    def usuario(self, eh_servidor: bool = True, tem_funcao: bool = True) -> mock.Mock:
        vinculo = mock.Mock()
        vinculo.eh_servidor.return_value = eh_servidor
        vinculo.relacionamento.historico_funcao_ativa.filter.return_value.exists.return_value = tem_funcao
        user = mock.Mock()
        user.get_vinculo.return_value = vinculo
        return user

    def test_diretor_no_setor_da_ug(self):
        user = self.usuario()
        assert self.unidade_gestora.eh_diretor(user) is True
        user.get_vinculo().relacionamento.historico_funcao_ativa.filter.assert_called_once_with(
            atividade__codigo__in=[Atividade.DIRETOR, Atividade.DIRETOR_GERAL, Atividade.REITOR],
            setor_suap=self.setor,
        )

    def test_sem_funcao_de_diretor_no_setor(self):
        assert self.unidade_gestora.eh_diretor(self.usuario(tem_funcao=False)) is False

    def test_usuario_que_nao_e_servidor(self):
        assert self.unidade_gestora.eh_diretor(self.usuario(eh_servidor=False)) is False

    def test_usuario_sem_vinculo(self):
        user = mock.Mock()
        user.get_vinculo.return_value = None
        assert self.unidade_gestora.eh_diretor(user) is False


@pytest.mark.django_db
def test_possui_diretor_geral_sem_funcao_no_setor():
    unidade_gestora = UnidadeGestora(setor_equivalente=Setor(pk=1))
    assert unidade_gestora.possui_diretor_geral() is False


@pytest.mark.django_db
def test_reitor_conta_como_dirigente_da_ug(sync_permissions):
    """UG cujo dirigente é o Reitor (ex.: a Reitoria): sem isso toda despesa exigiria anuência e ninguém poderia anuir."""
    setor_equivalente = SetorFactory()
    reitor = ServidorFactory()
    atividade, _ = Atividade.objects.get_or_create(codigo=Atividade.REITOR, defaults={'nome': 'Reitor'})
    ServidorFuncaoHistoricoFactory(servidor=reitor, atividade=atividade, setor=SetorSiapeFactory(), setor_suap=setor_equivalente)
    unidade_gestora = UnidadeGestora(setor_equivalente=setor_equivalente)

    assert unidade_gestora.possui_diretor_geral() is True
    assert unidade_gestora.possui_anuente() is True
    assert unidade_gestora.eh_diretor(reitor.get_user()) is True


@pytest.mark.django_db
def test_reitor_conta_como_dirigente_da_ug_abaixo_da_reitoria(sync_permissions):
    """UG de pró-reitoria (ex.: PROAD) não tem Diretor-Geral próprio: o dirigente é o Reitor, no setor do campus (Reitoria)."""
    reitoria = SetorFactory()
    proad = SetorFactory(superior=reitoria)
    atividade, _ = Atividade.objects.get_or_create(codigo=Atividade.REITOR, defaults={'nome': 'Reitor'})
    ServidorFuncaoHistoricoFactory(servidor=ServidorFactory(), atividade=atividade, setor=SetorSiapeFactory(), setor_suap=reitoria)
    requisicao = RequisicaoDespesa(unidade_gestora=UnidadeGestora(setor_equivalente=proad, setor_anuencia_despesa=SetorFactory()))

    assert requisicao.precisa_anuencia() is False


@pytest.mark.django_db
def test_possui_anuente_sem_funcao_no_setor():
    unidade_gestora = UnidadeGestora(setor_equivalente=Setor(pk=1))
    assert unidade_gestora.possui_anuente() is False


class RequisicaoDespesaFluxoAnuenciaTest:
    def setup_method(self):
        self.ordenador = Setor(pk=1, sigla='GABIN')
        self.anuencia = Setor(pk=2, sigla='DAP')
        self.ordenador_secundaria = Setor(pk=3, sigla='GABIN2')
        self.unidade_gestora = UnidadeGestora(setor_ordenador_despesa=self.ordenador, setor_anuencia_despesa=self.anuencia)
        self.ug_secundaria = UnidadeGestora(setor_ordenador_despesa=self.ordenador_secundaria)
        self.requisicao = RequisicaoDespesa(ua_vinculada=RequisicaoDespesa.UA_PRINCIPAL)
        self.requisicao._state.fields_cache['unidade_gestora'] = self.unidade_gestora

    def patch_diretor_geral(self, possui: bool):
        return mock.patch.object(UnidadeGestora, 'possui_diretor_geral', return_value=possui)

    def test_ua_principal_com_diretor_geral_vai_direto_para_o_ordenador(self):
        with self.patch_diretor_geral(True):
            assert self.requisicao.get_setor_destino_apos_cdo() == self.ordenador
            assert self.requisicao.get_status_apos_cdo() == RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO

    def test_ua_principal_sem_diretor_geral_passa_pela_anuencia(self):
        with self.patch_diretor_geral(False):
            assert self.requisicao.get_setor_destino_apos_cdo() == self.anuencia
            assert self.requisicao.get_status_apos_cdo() == RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
        assert self.requisicao.get_setor_destino_autorizacao() == self.ordenador

    def test_sem_setor_anuencia_vai_direto_para_o_ordenador(self):
        self.unidade_gestora.setor_anuencia_despesa = None
        with self.patch_diretor_geral(False):
            assert self.requisicao.get_setor_destino_apos_cdo() == self.ordenador
            assert self.requisicao.get_status_apos_cdo() == RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO

    def test_ua_secundaria_passa_pela_anuencia_mesmo_com_diretor_geral(self):
        self.requisicao.ua_vinculada = RequisicaoDespesa.UA_SECUNDARIA
        with self.patch_diretor_geral(True):
            assert self.requisicao.get_setor_destino_apos_cdo() == self.anuencia
            assert self.requisicao.get_status_apos_cdo() == RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA

    def test_ua_secundaria_autoriza_no_ordenador_da_ug_secundaria(self):
        self.requisicao.ua_vinculada = RequisicaoDespesa.UA_SECUNDARIA
        with mock.patch.object(UnidadeGestora, 'get_ug_secundaria', return_value=self.ug_secundaria):
            assert self.requisicao.get_setor_destino_autorizacao() == self.ordenador_secundaria

    def test_ua_secundaria_nao_encontrada(self):
        self.requisicao.ua_vinculada = RequisicaoDespesa.UA_SECUNDARIA
        with mock.patch.object(UnidadeGestora, 'get_ug_secundaria', return_value=None):
            assert self.requisicao.get_setor_destino_autorizacao() is None

    def test_pode_anuir_somente_aguardando_anuencia_e_sendo_diretor(self):
        with mock.patch('plan_estrategico.models.tl.get_user'), mock.patch.object(UnidadeGestora, 'eh_diretor', return_value=True):
            self.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
            assert self.requisicao.pode_anuir_despesa() is True
            self.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_AUTORIZACAO
            assert self.requisicao.pode_anuir_despesa() is False

    def test_nao_pode_anuir_sem_ser_diretor(self):
        self.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_ANUENCIA
        with mock.patch('plan_estrategico.models.tl.get_user'), mock.patch.object(UnidadeGestora, 'eh_diretor', return_value=False):
            assert self.requisicao.pode_anuir_despesa() is False


@pytest.mark.django_db
def test_ug_secundaria_busca_pelo_codigo_ug_no_mesmo_pdi():
    pdi = PDIFactory()
    pdi_seguinte = PDIFactory(ano_inicial_pdi=AnoFactory(ano=pdi.ano_inicial_pdi.ano + 5), ano_final_pdi=AnoFactory(ano=pdi.ano_final_pdi.ano + 5))
    secundaria = UnidadeGestoraFactory(pdi=pdi, codigo_ug='158155')
    UnidadeGestoraFactory(pdi=pdi_seguinte, codigo_ug='158155')
    principal = UnidadeGestoraFactory(pdi=pdi, codigo_ug='158366', ug_secundaria='158155')

    assert principal.get_ug_secundaria() == secundaria

    principal.ug_secundaria = '158999'
    assert principal.get_ug_secundaria() is None

    principal.ug_secundaria = ''
    assert principal.get_ug_secundaria() is None


class VariavelStrTest:
    def setup_method(self):
        self.variavel = Variavel(sigla='MAT_TOT', nome='Matrículas totais', descricao='Total de matrículas')

    def test_tematica_exibe_o_nome(self):
        assert str(TematicaVariavel(nome='Ensino')) == 'Ensino'

    def test_variavel_exibe_sigla_e_nome(self):
        assert str(self.variavel) == 'MAT_TOT - Matrículas totais'

    def test_variavel_campus_exibe_variavel_e_unidade(self):
        variavel_campus = VariavelCampus(variavel=self.variavel, uo=UnidadeOrganizacional(sigla='CNAT'), ano=2026)
        assert str(variavel_campus) == 'MAT_TOT - Matrículas totais: CNAT'
