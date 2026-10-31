from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.http import HttpResponse
import pytest

from documento_eletronico.views import assinar_via_senha_documento_pessoal


@pytest.fixture
def servidor_solicitado():
    servidor = MagicMock()
    servidor.nome_usual = 'Servidor Teste'
    servidor.get_cpf_ou_passaporte.return_value = '00000000000'
    return servidor


@pytest.fixture
def usuario_autenticado(servidor_solicitado):
    usuario = MagicMock()
    usuario.is_authenticated = True
    usuario.get_profile.return_value = servidor_solicitado
    return usuario


@pytest.fixture
def requisicao_de_assinatura(rf, usuario_autenticado):
    request = rf.post('/documento_eletronico/assinar_via_senha_documento_pessoal/1/', data={'senha': '123'})
    request.user = usuario_autenticado
    return request


@pytest.fixture
def documento_pessoal(servidor_solicitado):
    documento = MagicMock()
    documento.pode_assinar.return_value = True
    documento.get_solicitacao_assinatura_com_anexacao_processo.return_value = None

    solicitacao = MagicMock()
    solicitacao.solicitado = servidor_solicitado
    solicitacao.get_solicitacoes_dependentes.return_value = []
    documento.get_solicitacao_balizadora.return_value = solicitacao
    return documento


@pytest.fixture
def colaboradores_da_view(monkeypatch, documento_pessoal):
    colaboradores = SimpleNamespace(
        get_documento_or_forbidden=MagicMock(return_value=documento_pessoal),
        assinar_documento_form=MagicMock(),
        httprr=MagicMock(return_value=HttpResponse('ok')),
        get_datetime_now=MagicMock(return_value=datetime(2026, 4, 30, 12, 0, 0)),
        reverse_lazy=MagicMock(return_value='/documento/1/'),
        atomic=MagicMock(),
        savepoint=MagicMock(return_value='sid'),
        savepoint_commit=MagicMock(),
        savepoint_rollback=MagicMock(),
        registrar_acao_documento_texto=MagicMock(),
    )
    colaboradores.atomic.return_value.__enter__.return_value = None
    colaboradores.atomic.return_value.__exit__.return_value = None

    formulario_valido = MagicMock()
    formulario_valido.is_valid.return_value = True
    formulario_valido.cleaned_data = {'papel': MagicMock()}
    colaboradores.assinar_documento_form.return_value = formulario_valido

    monkeypatch.setattr('documento_eletronico.views.get_documento_or_forbidden', colaboradores.get_documento_or_forbidden)
    monkeypatch.setattr('documento_eletronico.views.AssinarDocumentoForm', colaboradores.assinar_documento_form)
    monkeypatch.setattr('documento_eletronico.views.httprr', colaboradores.httprr)
    monkeypatch.setattr('documento_eletronico.views.get_datetime_now', colaboradores.get_datetime_now)
    monkeypatch.setattr('documento_eletronico.views.reverse_lazy', colaboradores.reverse_lazy)
    monkeypatch.setattr('documento_eletronico.views.transaction.atomic', colaboradores.atomic)
    monkeypatch.setattr('documento_eletronico.views.transaction.savepoint', colaboradores.savepoint)
    monkeypatch.setattr('documento_eletronico.views.transaction.savepoint_commit', colaboradores.savepoint_commit)
    monkeypatch.setattr('documento_eletronico.views.transaction.savepoint_rollback', colaboradores.savepoint_rollback)
    monkeypatch.setattr('documento_eletronico.views.registrar_acao_documento_texto', colaboradores.registrar_acao_documento_texto)
    return colaboradores


class TestAssinaturaDocumentoPessoal:
    def test_preserva_identificador_definitivo_ao_assinar_documento_pessoal(
        self,
        requisicao_de_assinatura,
        documento_pessoal,
        colaboradores_da_view,
    ):
        documento_pessoal.tem_identificador_definitivo = True

        response = assinar_via_senha_documento_pessoal(requisicao_de_assinatura, documento_id=1)

        assert response.status_code == 200
        documento_pessoal.atribuir_identificador_e_processar_conteudo_final.assert_not_called()
        documento_pessoal.save.assert_not_called()
        documento_pessoal.assinar_via_senha.assert_called_once()
        colaboradores_da_view.httprr.assert_called_with('/documento/1/', 'Documento assinado com sucesso.')
        colaboradores_da_view.get_datetime_now.assert_called_once()
        colaboradores_da_view.reverse_lazy.assert_called_once()
        colaboradores_da_view.savepoint.assert_called_once()
        colaboradores_da_view.savepoint_commit.assert_called_once()
        colaboradores_da_view.savepoint_rollback.assert_not_called()
        colaboradores_da_view.registrar_acao_documento_texto.assert_called_once()

    def test_gera_identificador_definitivo_ao_assinar_documento_pessoal_sem_identificador(
        self,
        requisicao_de_assinatura,
        documento_pessoal,
        colaboradores_da_view,
    ):
        documento_pessoal.tem_identificador_definitivo = False
        documento_pessoal.get_sugestao_identificador_definitivo.return_value = ('DOC', 10, 2026, 'SERVIDOR')
        documento_pessoal.modelo.tipo_documento_texto = MagicMock()
        documento_pessoal.usuario_criacao = MagicMock()

        response = assinar_via_senha_documento_pessoal(requisicao_de_assinatura, documento_id=1)

        assert response.status_code == 200
        documento_pessoal.get_sugestao_identificador_definitivo.assert_called_once()
        documento_pessoal.atribuir_identificador_e_processar_conteudo_final.assert_called_once()
        documento_pessoal.save.assert_called_once()
        documento_pessoal.assinar_via_senha.assert_called_once()
        colaboradores_da_view.httprr.assert_called_with('/documento/1/', 'Documento assinado com sucesso.')
        colaboradores_da_view.get_datetime_now.assert_called_once()
        colaboradores_da_view.reverse_lazy.assert_called_once()
        colaboradores_da_view.savepoint.assert_called_once()
        colaboradores_da_view.savepoint_commit.assert_called_once()
        colaboradores_da_view.savepoint_rollback.assert_not_called()
        colaboradores_da_view.registrar_acao_documento_texto.assert_called_once()
