"""Regressão do falso positivo de compartilhamento intrassetor em documento pessoal.

``DocumentoTexto.tem_permissao_editar`` (ramo ``eh_documento_pessoal``) não filtrava o
resultado de ``DocumentoTextoPessoal.objects.compartilhados`` pelo ``pk`` do próprio
documento, e o manager pessoal ignorava o parâmetro ``nivel_permissao``. Juntos, os dois
bugs faziam o método retornar ``True`` para QUALQUER documento pessoal sempre que o
usuário tivesse qualquer compartilhamento (mesmo só de leitura) em outro documento seu.
"""

import pytest

from djtools.middleware import threadlocals as tl
from documento_eletronico.models import CompartilhamentoDocumentoPessoa, NivelPermissao
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.usefixtures('db', 'sync_permissions')


def compartilhar(documento, colega, nivel_permissao):
    """Compartilha o documento com ``colega`` como o dono dele (o ``save`` lê o usuário do threadlocal)."""
    tl.context.user = documento.usuario_criacao
    try:
        return CompartilhamentoDocumentoPessoa.objects.create(
            documento=documento, vinculo_permitido=colega.get_vinculo(), nivel_permissao=nivel_permissao
        )
    finally:
        tl.context.user = None


def test_editar_em_outro_documento_pessoal_nao_libera_edicao():
    dono_a, colega, dono_c = ServidorFactory(), ServidorFactory(), ServidorFactory()
    documento_a = DocumentoTextoFactory(usuario_criacao=dono_a.get_user())
    documento_c = DocumentoTextoFactory(usuario_criacao=dono_c.get_user())
    # O colega tem EDITAR no documento de C, não no de A.
    compartilhar(documento_c, colega, NivelPermissao.EDITAR)

    assert documento_a.tem_permissao_editar(colega.get_user()) is False


def test_compartilhamento_explicito_de_edicao_libera_edicao():
    dono, colega = ServidorFactory(), ServidorFactory()
    documento = DocumentoTextoFactory(usuario_criacao=dono.get_user())
    compartilhar(documento, colega, NivelPermissao.EDITAR)

    assert documento.tem_permissao_editar(colega.get_user()) is True


def test_compartilhamento_apenas_de_leitura_nao_libera_edicao():
    dono, colega = ServidorFactory(), ServidorFactory()
    documento = DocumentoTextoFactory(usuario_criacao=dono.get_user())
    compartilhar(documento, colega, NivelPermissao.LER)

    assert documento.tem_permissao_editar(colega.get_user()) is False
