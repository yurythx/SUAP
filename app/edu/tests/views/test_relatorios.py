"""Testes DB-free de views finas de ``edu/views/relatorios.py``.

Mesmo padrão de ``test_nada_consta``: ``inspect.unwrap`` na view ``@rtr`` + RequestFactory
+ mock dos toques de ORM/Form. Nenhum teste toca o banco.
"""

from inspect import unwrap
from unittest.mock import MagicMock, patch

from edu.views import relatorios

# make_request: fixture em edu/tests/views/conftest.py


# --- salvar_relatorio (form válido → redirect; inválido → contexto) ---------


def test_salvar_relatorio_form_valido_processa_e_redireciona(make_request):
    request = make_request(method='post')
    form = MagicMock()
    form.is_valid.return_value = True
    with (
        patch.object(relatorios, 'SalvarRelatorioForm', return_value=form),
        patch.object(relatorios, 'httprr', return_value='REDIRECT') as mock_httprr,
    ):
        resposta = unwrap(relatorios.salvar_relatorio)(request, tipo=1, query_string='a=1')
    form.processar.assert_called_once_with('a=1')
    mock_httprr.assert_called_once()
    assert resposta == 'REDIRECT'


def test_salvar_relatorio_form_invalido_retorna_contexto(make_request):
    request = make_request()
    form = MagicMock()
    form.is_valid.return_value = False
    with patch.object(relatorios, 'SalvarRelatorioForm', return_value=form):
        resposta = unwrap(relatorios.salvar_relatorio)(request, tipo=1, query_string='a=1')
    assert isinstance(resposta, dict)
    assert resposta['form'] is form


# --- meus_relatorios (listagem vs deleção) ----------------------------------


def test_meus_relatorios_lista_consultas_do_usuario(make_request):
    user = MagicMock()
    user.historicorelatorio_set.filter.return_value = ['r1', 'r2']
    request = make_request(user=user)
    resposta = unwrap(relatorios.meus_relatorios)(request, tipo=1)
    assert isinstance(resposta, dict)
    assert resposta['relatorios'] == ['r1', 'r2']
    user.historicorelatorio_set.filter.assert_called_once_with(tipo=1)


def test_meus_relatorios_delecao_exclui_e_redireciona(make_request):
    user = MagicMock()
    request = make_request(path='/?del_historicorelatorio=5', user=user)
    historico = MagicMock()
    historico.get_url_sem_parametro.return_value = '/edu/relatorio/'
    with (
        patch.object(relatorios, 'get_object_or_404', return_value=historico),
        patch.object(relatorios, 'httprr', return_value='REDIRECT') as mock_httprr,
    ):
        resposta = unwrap(relatorios.meus_relatorios)(request, tipo=1)
    historico.delete.assert_called_once()
    mock_httprr.assert_called_once()
    assert resposta == 'REDIRECT'
