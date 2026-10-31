"""Autocadastro de biometria pelo próprio servidor (``/comum/solicitar_autocadastro/``).

A tela responde "Solicitação realizada, verifique seu e-mail.", mas só o reenvio mandava o código:
o primeiro pedido gravava a ``BiometriaSolicitacao`` e não enviava nada (#17397).
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.test import Client

from comum.models import Configuracao
from rh.models import BiometriaSolicitacao, Servidor
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db

SOLICITAR = '/comum/solicitar_autocadastro/'
REENVIAR = '/comum/solicitar_autocadastro/reenviar/{pk}/'
SENHA = 'abcd'


def _servidor_logado(client: Client) -> Servidor:
    Configuracao.objects.update_or_create(app='comum', chave='biometria_expiracao', defaults={'valor': '7'})
    servidor = ServidorFactory()
    vinculo = servidor.get_vinculo()
    vinculo.email_pessoal = 'servidor@exemplo.com'
    vinculo.save()
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    client.force_login(user)
    return servidor


def test_solicitar_autocadastro_envia_o_codigo_e_o_reenvio_manda_de_novo(client: Client, sync_permissions) -> None:
    servidor = _servidor_logado(client)
    resposta = client.post(SOLICITAR, {'senha': SENHA, 'confirmar': 'on'})

    assert resposta.status_code == 302
    solicitacao = BiometriaSolicitacao.objects.get(pessoa_fisica=servidor.pessoa_fisica)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ['servidor@exemplo.com']
    assert solicitacao.codigo_verificacao in mail.outbox[0].body

    client.get(REENVIAR.format(pk=solicitacao.pk))

    assert len(mail.outbox) == 2
    assert solicitacao.codigo_verificacao in mail.outbox[1].body
