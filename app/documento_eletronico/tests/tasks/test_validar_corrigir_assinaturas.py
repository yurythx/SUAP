"""Command ``validar_corrigir_assinaturas``: regera a assinatura por senha de um documento cujo hmac não confere.

Roda o ``handle`` do command de verdade, com a correção ligada (as opções que o ``otimizacao_05``
também passa direto), sobre um documento assinado por senha cujo hmac foi adulterado no banco.
"""

from __future__ import annotations

import pytest

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from documento_eletronico.assinar_documento import gerar_assinatura_documento_senha
from documento_eletronico.management.commands.validar_corrigir_assinaturas import Command
from documento_eletronico.models import Assinatura, AssinaturaDocumentoTexto
from documento_eletronico.tests.factories import DocumentoTextoFactory
from rh.tests.factories import PapelFactory, ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db


def test_assinatura_invalida_e_regerada_e_volta_a_validar(sync_permissions, tmp_path) -> None:
    """Antes da #17484 a correção morria em ``TypeError`` (``pessoa_fisica=`` em vez de ``vinculo=``)."""
    # O cabeçalho do documento resolve a unidade da reitoria (``get_variaveis``).
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': 'IFRN'})
    servidor = ServidorFactory(setor=SetorFactory(sigla=get_sigla_reitoria(), nome='Reitoria'))
    papel = PapelFactory(servidor=servidor)
    user = servidor.get_user()
    documento = DocumentoTextoFactory(usuario_criacao=user)
    # Assinatura por senha cujo hmac não confere com o conteúdo: o estado que o command existe para corrigir.
    assinatura = Assinatura.objects.create(
        vinculo=user.get_vinculo(), cpf=servidor.pessoa_fisica.cpf, nome_papel=papel.detalhamento, papel=papel, hmac='hmac-adulterado'
    )
    assinatura_doc = AssinaturaDocumentoTexto.objects.create(documento=documento, assinatura=assinatura)
    assert not assinatura_doc.validar_documento()

    command = Command()
    command.log_file = str(tmp_path / 'validar_corrigir_assinaturas.log')
    command.handle(executar_command=True, corrigir_assinaturas_invalidas=True)

    assinatura_doc = AssinaturaDocumentoTexto.objects.get(documento=documento)
    assert assinatura_doc.assinatura.hmac == gerar_assinatura_documento_senha(documento, user.get_vinculo())
    assert assinatura_doc.validar_documento()
