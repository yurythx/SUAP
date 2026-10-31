"""Formulário de compartilhamento de documento pessoal (``gerenciar_compartilhamento_documento``).

A validação "já tem permissão de Leitura e Edição" usava ``tem_permissao_editar``, que dava
falso positivo para qualquer documento pessoal quando o colega tinha compartilhamento de
edição em outro documento — e o formulário recusava um compartilhamento legítimo.
"""

import pytest

from djtools.middleware import threadlocals as tl
from documento_eletronico.models import CompartilhamentoDocumentoPessoa, NivelPermissao
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.usefixtures('db', 'sync_permissions')


def url_compartilhamento(documento):
    return f'/documento_eletronico/gerenciar_compartilhamento_documento/{documento.pk}/'


def test_compartilha_edicao_com_quem_ja_edita_outro_documento_pessoal(client):
    dono_a, colega, dono_c = ServidorFactory(), ServidorFactory(), ServidorFactory()
    documento_a = DocumentoTextoFactory(usuario_criacao=dono_a.get_user())
    documento_c = DocumentoTextoFactory(usuario_criacao=dono_c.get_user())
    tl.context.user = dono_c.get_user()
    try:
        CompartilhamentoDocumentoPessoa.objects.create(
            documento=documento_c, vinculo_permitido=colega.get_vinculo(), nivel_permissao=NivelPermissao.EDITAR
        )
    finally:
        tl.context.user = None

    client.force_login(dono_a.get_user())
    response = client.post(
        url_compartilhamento(documento_a),
        {'pessoas_permitidas_podem_ler': [], 'pessoas_permitidas_podem_escrever': [colega.get_vinculo().pk]},
    )

    assert response.status_code == 302
    assert CompartilhamentoDocumentoPessoa.objects.filter(
        documento=documento_a, vinculo_permitido=colega.get_vinculo(), nivel_permissao=NivelPermissao.EDITAR
    ).exists()


def test_recusa_compartilhar_edicao_com_o_proprio_dono(client):
    """O dono já tem acesso implícito (``usuario_criacao == user``): o formulário continua recusando."""
    dono = ServidorFactory()
    documento = DocumentoTextoFactory(usuario_criacao=dono.get_user())

    client.force_login(dono.get_user())
    response = client.post(
        url_compartilhamento(documento),
        {'pessoas_permitidas_podem_ler': [], 'pessoas_permitidas_podem_escrever': [dono.get_vinculo().pk]},
    )

    assert response.status_code == 200
    assert 'já tem permissão de Leitura e Edição' in response.content.decode('utf-8')
    assert not CompartilhamentoDocumentoPessoa.objects.filter(documento=documento).exists()
