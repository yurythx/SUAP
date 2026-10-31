"""Testes DB-free de views finas de ``edu/views/nada_consta.py``.

A view decorada (`@rtr`/`@permission_required`) é desembrulhada com ``inspect.unwrap``
para chamar o corpo cru — que retorna o dict de contexto ou um ``HttpResponse`` direto,
sem renderizar template (sem DB). Como ``unwrap`` pula TODOS os decorators, o
``@permission_required`` externo NÃO é exercitado: o que se testa é o gate de permissão
*no corpo* da view (``pode_realizar_procedimento``). Os toques de ORM/Form são mockados
(padrão de ``plan_estrategico/tests/test_views.py``). Nenhum teste toca o banco.
"""

from inspect import unwrap
from unittest.mock import MagicMock, patch

from django.http.response import HttpResponseForbidden

from edu.views import nada_consta

# make_request: fixture em edu/tests/views/conftest.py


# --- informar_responsaveis_nada_consta (gate de permissão + form) -----------


def test_informar_responsaveis_sem_permissao_retorna_forbidden(make_request):
    user = MagicMock()
    user.has_group_cached.return_value = False
    request = make_request(user=user)
    with patch.object(nada_consta, 'get_object_or_404', return_value=MagicMock()):
        resposta = unwrap(nada_consta.informar_responsaveis_nada_consta)(request, pk=1)
    assert isinstance(resposta, HttpResponseForbidden)


def test_informar_responsaveis_form_valido_salva_e_redireciona(make_request):
    user = MagicMock()
    user.has_group_cached.return_value = True  # Administrador Acadêmico
    request = make_request(method='post', user=user)
    form = MagicMock()
    form.is_valid.return_value = True
    with (
        patch.object(nada_consta, 'get_object_or_404', return_value=MagicMock()),
        patch.object(nada_consta, 'InformarResponsaveisNadaConstaForm', return_value=form),
        patch.object(nada_consta, 'httprr', return_value='REDIRECT') as mock_httprr,
    ):
        resposta = unwrap(nada_consta.informar_responsaveis_nada_consta)(request, pk=1)
    form.save.assert_called_once()
    mock_httprr.assert_called_once()
    assert resposta == 'REDIRECT'


def test_informar_responsaveis_form_invalido_retorna_contexto(make_request):
    user = MagicMock()
    user.has_group_cached.return_value = True
    request = make_request(user=user)
    form = MagicMock()
    form.is_valid.return_value = False
    with (
        patch.object(nada_consta, 'get_object_or_404', return_value=MagicMock()),
        patch.object(nada_consta, 'InformarResponsaveisNadaConstaForm', return_value=form),
    ):
        resposta = unwrap(nada_consta.informar_responsaveis_nada_consta)(request, pk=1)
    assert isinstance(resposta, dict)
    assert resposta['title'] == 'Informar Responsáveis'
    assert resposta['form'] is form


# --- configuracaonadaconsta (smoke de contexto) -----------------------------


def test_configuracaonadaconsta_retorna_contexto(make_request):
    request = make_request()
    obj = MagicMock()
    with patch.object(nada_consta, 'get_object_or_404', return_value=obj):
        resposta = unwrap(nada_consta.configuracaonadaconsta)(request, pk=1)
    assert isinstance(resposta, dict)
    assert resposta['obj'] is obj
    assert resposta['title'] == 'Configuração de Nada Consta'
