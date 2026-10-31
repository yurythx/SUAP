from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied

from plan_estrategico.models import RequisicaoDespesa


pytestmark = pytest.mark.django_db


class EncaminharValidacaoSiafiTest:
    def get_request(self, rf):
        request = rf.get('/plan_estrategico/requisicao/1/encaminhar-validacao-siafi/')
        request.user = mock.Mock()
        request.user.get_all_permissions.return_value = []
        request.session = {}
        request._messages = mock.Mock()
        return request

    def get_requisicao(self, status):
        requisicao = mock.Mock()
        requisicao.pode_encaminhar_validacao_siafi.return_value = True
        requisicao.status = status
        requisicao.save.return_value = None
        requisicao.validar_requisicao.return_value = None
        return requisicao

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.get_object_or_404')
    @mock.patch('plan_estrategico.views.RequisicaoDespesaHistorico.objects.create')
    @mock.patch('plan_estrategico.views.NotaEmpenho.objects.filter')
    @mock.patch('plan_estrategico.views.httprr')
    def test_requisicao_concluida_retorna_mensagem_sucesso(
        self,
        mock_httprr,
        mock_nota_filter,
        mock_historico_create,
        mock_get_object_or_404,
        mock_render,
        rf,
    ):
        mock_httprr.return_value = {}

        request = self.get_request(rf)
        requisicao = self.get_requisicao(RequisicaoDespesa.STATUS_CONCLUIDA)

        def validar_requisicao():
            requisicao.status = RequisicaoDespesa.STATUS_CONCLUIDA

        requisicao.validar_requisicao.side_effect = validar_requisicao
        mock_get_object_or_404.return_value = requisicao

        from plan_estrategico.views import encaminhar_validacao_siafi

        encaminhar_validacao_siafi(request, 1)

        requisicao.validar_requisicao.assert_called_once()
        mock_httprr.assert_called_once_with('..', 'Requisição de despesa concluída com sucesso.')

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.get_object_or_404')
    @mock.patch('plan_estrategico.views.RequisicaoDespesaHistorico.objects.create')
    @mock.patch('plan_estrategico.views.NotaEmpenho.objects.filter')
    @mock.patch('plan_estrategico.views.httprr')
    def test_requisicao_nao_concluida_retorna_mensagem_padrao(
        self,
        mock_httprr,
        mock_nota_filter,
        mock_historico_create,
        mock_get_object_or_404,
        mock_render,
        rf,
    ):
        mock_httprr.return_value = {}

        request = self.get_request(rf)
        requisicao = self.get_requisicao(RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO)

        def validar_requisicao():
            requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO

        requisicao.validar_requisicao.side_effect = validar_requisicao
        mock_get_object_or_404.return_value = requisicao

        from plan_estrategico.views import encaminhar_validacao_siafi

        encaminhar_validacao_siafi(request, 1)

        requisicao.validar_requisicao.assert_called_once()
        mock_httprr.assert_called_once_with('..', 'Requisição encaminhada para validação SIAFI.')

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.httprr')
    def test_raise_permission_denied_quando_nao_pode_encaminhar(
        self,
        mock_httprr,
        mock_render,
        rf,
    ):
        requisicao = mock.Mock()
        requisicao.pode_encaminhar_validacao_siafi.return_value = False

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=requisicao):
            from plan_estrategico.views import encaminhar_validacao_siafi

            request = self.get_request(rf)

            with pytest.raises(PermissionDenied):
                encaminhar_validacao_siafi(request, 1)


class EditarEmpenhoPermissaoTest:
    def get_request(self, rf):
        request = rf.get('/plan_estrategico/adicionar_notaempenho/1/')
        request.user = mock.Mock()
        request.user.get_all_permissions.return_value = []
        request.session = {}
        request._messages = mock.Mock()
        return request

    def get_notaempenho(self, pode_editar):
        notaempenho = mock.Mock()
        notaempenho.requisicao.pode_editar_empenho.return_value = pode_editar
        return notaempenho

    @mock.patch('djtools.utils.response.render', return_value={})
    def test_adicionar_notaempenho_nega_quando_requisicao_nao_permite_edicao(self, mock_render, rf):
        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=self.get_notaempenho(False)):
            from plan_estrategico.views import adicionar_notaempenho

            with pytest.raises(PermissionDenied):
                adicionar_notaempenho(self.get_request(rf), 1)

    @mock.patch('djtools.utils.response.render', return_value={})
    def test_adicionar_ro_nega_quando_requisicao_nao_permite_edicao(self, mock_render, rf):
        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=self.get_notaempenho(False)):
            from plan_estrategico.views import adicionar_ro

            with pytest.raises(PermissionDenied):
                adicionar_ro(self.get_request(rf), 1)

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.NotaEmpenhoForm')
    def test_adicionar_notaempenho_prossegue_quando_requisicao_permite_edicao(self, mock_form, mock_render, rf):
        mock_form.return_value.is_valid.return_value = False
        notaempenho = self.get_notaempenho(True)

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=notaempenho):
            from plan_estrategico.views import adicionar_notaempenho

            adicionar_notaempenho(self.get_request(rf), 1)

        notaempenho.requisicao.pode_editar_empenho.assert_called_once()


class RevalidarRequisicaoAposEdicaoTest:
    def get_requisicao(self, status_inicial, status_apos_validacao=None):
        requisicao = mock.Mock()
        requisicao.status = status_inicial

        def validar_requisicao():
            requisicao.status = status_apos_validacao

        requisicao.validar_requisicao.side_effect = validar_requisicao
        return requisicao

    def test_nao_revalida_quando_requisicao_nao_aguarda_validacao(self):
        from plan_estrategico.views import revalidar_requisicao_apos_edicao

        requisicao = self.get_requisicao(RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO)

        mensagem = revalidar_requisicao_apos_edicao(requisicao, 'Nota de empenho salva.')

        requisicao.validar_requisicao.assert_not_called()
        assert mensagem == 'Nota de empenho salva.'

    def test_revalida_e_conclui_requisicao(self):
        from plan_estrategico.views import revalidar_requisicao_apos_edicao

        requisicao = self.get_requisicao(
            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
            RequisicaoDespesa.STATUS_CONCLUIDA,
        )

        mensagem = revalidar_requisicao_apos_edicao(requisicao, 'Nota de empenho salva.')

        requisicao.validar_requisicao.assert_called_once()
        assert mensagem == 'Nota de empenho salva. Requisição de despesa concluída com sucesso.'

    def test_revalida_e_aponta_inconsistencia(self):
        from plan_estrategico.views import revalidar_requisicao_apos_edicao

        requisicao = self.get_requisicao(
            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
            RequisicaoDespesa.STATUS_INCONSISTENTE,
        )

        mensagem = revalidar_requisicao_apos_edicao(requisicao, 'RO Salvo.')

        requisicao.validar_requisicao.assert_called_once()
        assert mensagem == 'RO Salvo. A conferência com o tesouro apontou inconsistências.'

    def test_revalida_e_segue_aguardando_validacao(self):
        from plan_estrategico.views import revalidar_requisicao_apos_edicao

        requisicao = self.get_requisicao(
            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
        )

        mensagem = revalidar_requisicao_apos_edicao(requisicao, 'RO Salvo.')

        requisicao.validar_requisicao.assert_called_once()
        assert mensagem == 'RO Salvo. A requisição segue aguardando a validação do SIAFI.'

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.httprr')
    @mock.patch('plan_estrategico.views.NotaEmpenhoForm')
    def test_adicionar_notaempenho_dispara_revalidacao_apos_salvar(self, mock_form, mock_httprr, mock_render, rf):
        mock_form.return_value.is_valid.return_value = True
        mock_httprr.return_value = {}

        notaempenho = mock.Mock()
        notaempenho.requisicao = self.get_requisicao(
            RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO,
            RequisicaoDespesa.STATUS_CONCLUIDA,
        )
        notaempenho.requisicao.pode_editar_empenho.return_value = True

        request = rf.get('/plan_estrategico/adicionar_notaempenho/1/')
        request.user = mock.Mock()
        request.user.get_all_permissions.return_value = []
        request.session = {}
        request._messages = mock.Mock()

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=notaempenho):
            from plan_estrategico.views import adicionar_notaempenho

            adicionar_notaempenho(request, 1)

        notaempenho.requisicao.validar_requisicao.assert_called_once()
        mock_httprr.assert_called_once_with('..', 'Nota de empenho salva. Requisição de despesa concluída com sucesso.')


class ReforcarEmpenhoTest:
    def get_request(self, rf):
        request = rf.get('/plan_estrategico/reforcar_empenho/1/')
        request.user = mock.Mock()
        request.user.get_all_permissions.return_value = []
        request.session = {}
        request._messages = mock.Mock()
        return request

    def get_notaempenho(self, pode_reforcar):
        notaempenho = mock.Mock()
        notaempenho.pode_reforcar.return_value = pode_reforcar
        return notaempenho

    @mock.patch('djtools.utils.response.render', return_value={})
    def test_nega_quando_a_linha_nao_permite_vincular_reforco(self, mock_render, rf):
        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=self.get_notaempenho(False)):
            from plan_estrategico.views import reforcar_empenho

            with pytest.raises(PermissionDenied):
                reforcar_empenho(self.get_request(rf), 1)

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.ReforcoEmpenhoForm')
    def test_exibe_formulario_quando_a_linha_permite_vincular_reforco(self, mock_form, mock_render, rf):
        mock_form.return_value.is_valid.return_value = False
        notaempenho = self.get_notaempenho(True)

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=notaempenho):
            from plan_estrategico.views import reforcar_empenho

            reforcar_empenho(self.get_request(rf), 1)

        notaempenho.pode_reforcar.assert_called_once()
        assert mock_form.call_args.kwargs['nota_empenho'] is notaempenho

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.httprr')
    @mock.patch('plan_estrategico.views.ReforcoEmpenhoForm')
    def test_salva_o_reforco_e_informa_o_vinculo(self, mock_form, mock_httprr, mock_render, rf):
        mock_form.return_value.is_valid.return_value = True
        mock_httprr.return_value = {}
        notaempenho = self.get_notaempenho(True)
        notaempenho.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_EMISSAO_EMPENHO

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=notaempenho):
            from plan_estrategico.views import reforcar_empenho

            reforcar_empenho(self.get_request(rf), 1)

        mock_form.return_value.save.assert_called_once()
        notaempenho.requisicao.validar_requisicao.assert_not_called()
        mock_httprr.assert_called_once_with('..', 'Reforço vinculado ao empenho.')

    @mock.patch('djtools.utils.response.render', return_value={})
    @mock.patch('plan_estrategico.views.httprr')
    @mock.patch('plan_estrategico.views.ReforcoEmpenhoForm')
    def test_dispara_a_validacao_siafi_apos_salvar_o_reforco(self, mock_form, mock_httprr, mock_render, rf):
        mock_form.return_value.is_valid.return_value = True
        mock_httprr.return_value = {}
        notaempenho = self.get_notaempenho(True)
        notaempenho.requisicao.status = RequisicaoDespesa.STATUS_AGUARDANDO_VALIDACAO

        def validar_requisicao():
            notaempenho.requisicao.status = RequisicaoDespesa.STATUS_CONCLUIDA

        notaempenho.requisicao.validar_requisicao.side_effect = validar_requisicao

        with mock.patch('plan_estrategico.views.get_object_or_404', return_value=notaempenho):
            from plan_estrategico.views import reforcar_empenho

            reforcar_empenho(self.get_request(rf), 1)

        notaempenho.requisicao.validar_requisicao.assert_called_once()
        mock_httprr.assert_called_once_with('..', 'Reforço vinculado ao empenho. Requisição de despesa concluída com sucesso.')
