"""Changelist do admin cai na página "Database error" do Django (``?e=1`` já na URL) (#17816).

O Django responde com ``SimpleTemplateResponse('admin/invalid_setup.html')``, que não roda context
processors: sem ``theme`` o ``base.html`` do SUAP levantava ``VariableDoesNotExist`` (500).

- Com filtro na URL, o culpado é o filtro: redireciona para a listagem sem parâmetros, com aviso.
- Só com o ``e``, a listagem falha sem filtro nenhum (bug): renderiza a página de erro (sem loop de
  redirect) e manda a causa ao Sentry.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.messages import get_messages
from django.test import Client

from djtools.contrib.admin.views import ChangeListPlus
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

PROCESSOS = '/admin/processo_eletronico/processo/'
AVISO = 'Você escolheu algum filtro inválido, por favor tente novamente nas opções disponíveis.'


@pytest.fixture
def superusuario(client: Client, sync_permissions: None) -> Client:
    user = ServidorFactory().get_user()
    user.is_superuser = True
    user.save()
    client.force_login(user)
    return client


@pytest.fixture
def listagem_quebrada(monkeypatch: pytest.MonkeyPatch) -> IncorrectLookupParameters:
    """Simula a listagem falhando mesmo sem filtro do usuário (p.ex. filtro padrão quebrado)."""
    erro = IncorrectLookupParameters('listagem quebrada')

    def get_filters(self, request):
        raise erro

    monkeypatch.setattr(ChangeListPlus, 'get_filters', get_filters)
    return erro


def test_lookup_invalido_com_flag_de_erro_redireciona_com_aviso(superusuario: Client) -> None:
    with mock.patch('djtools.contrib.admin.options.capture_exception') as capture:
        resposta = superusuario.get(PROCESSOS, {'e': '1', 'campo_invalido': 'x'})

    assert resposta.status_code == 302
    assert resposta['Location'] == PROCESSOS
    assert AVISO in [str(m) for m in get_messages(resposta.wsgi_request)]
    capture.assert_not_called()  # erro do filtro do usuário, não é bug


def test_listagem_que_falha_sem_filtro_renderiza_erro_e_avisa_o_sentry(superusuario: Client, listagem_quebrada: IncorrectLookupParameters) -> None:
    with mock.patch('djtools.contrib.admin.options.capture_exception') as capture:
        resposta = superusuario.get(PROCESSOS, {'e': '1'})

    assert resposta.status_code == 200
    assert 'Erro no banco de dados' in resposta.content.decode()
    assert resposta.context['theme']  # veio do context processor
    capture.assert_called_once_with(listagem_quebrada)


def test_listagem_que_falha_sem_flag_redireciona_para_a_flag_sem_loop(superusuario: Client, listagem_quebrada: IncorrectLookupParameters) -> None:
    with mock.patch('djtools.contrib.admin.options.capture_exception') as capture:
        resposta = superusuario.get(PROCESSOS)

    assert resposta.status_code == 302
    assert resposta['Location'] == f'{PROCESSOS}?e=1'  # comportamento do Django; o 2º GET cai no teste acima
    capture.assert_not_called()
