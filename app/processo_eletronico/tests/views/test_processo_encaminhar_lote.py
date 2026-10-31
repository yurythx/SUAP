"""Encaminhamento de processos em lote."""

import pytest
from django.contrib.messages import get_messages
from django.test import Client

from comum.tests.factories import UserFactory
from processo_eletronico.tests.factories import ProcessoFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory


@pytest.mark.django_db
def test_usuario_sem_setor_e_redirecionado_com_mensagem(client: Client, sync_permissions: None, setor_com_siorg: Setor) -> None:
    """Sem setor, a view usava ``processo`` antes de defini-lo e estourava ``NameError`` (#17774).

    O superusuário sem vínculo passa pelo middleware de usuário sem setor e chega à view.
    """
    processo = ProcessoFactory(setor_criacao=setor_com_siorg, usuario_gerador=ServidorFactory(setor=setor_com_siorg).get_user())
    client.force_login(UserFactory(is_superuser=True, is_staff=True))

    resposta = client.get(f'/processo_eletronico/processo/encaminhar_lote/{processo.pk}/')

    assert resposta.status_code == 302
    assert resposta.url == '/'
    assert [str(m) for m in get_messages(resposta.wsgi_request)] == ['O usuário não possui setor definido.']
