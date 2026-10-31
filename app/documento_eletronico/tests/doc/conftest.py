"""Fixtures da documentação de usuário gerada pelo navegador.

As imagens ficam em ``documento_eletronico/docs/usuario/`` durante a rodada e são ignoradas
pelo Git. O build as recria com ``pytest -m doc documento_eletronico``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from documento_eletronico.tests.e2e.conftest import *  # noqa: F403

DESTINO = Path(settings.BASE_DIR) / 'documento_eletronico' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405


@pytest.fixture(scope='session', autouse=True)
def limpar_documentos_da_documentacao(documento_seed, django_db_blocker) -> None:
    """Remove documentos criados por rodadas anteriores do manual reutilizando o banco."""
    with django_db_blocker.unblock():
        from django.db.models import Q

        from documento_eletronico.models import DocumentoTexto

        assuntos = Q(assunto__regex=r'^(Documento|Conteúdo|Conclusão|Rascunho|Assinatura|Clone|Vínculo) doc ')
        DocumentoTexto.objects.filter(assuntos).delete()


@pytest.fixture(autouse=True)
def limpar_estado_do_documento_documentacao(documento_seed) -> None:
    """Restaura o documento compartilhado antes de cada tarefa do manual."""
    from documento_eletronico.models import DocumentoTexto, SolicitacaoAssinatura
    from documento_eletronico.status import DocumentoStatus
    from processo_eletronico.models import SolicitacaoAlteracaoNivelAcesso

    documento = DocumentoTexto.objects.get(identificador='MEMO 1/2020 - DIDE/CEN/RAIZ')
    documento.assinaturadocumentotexto_set.all().delete()
    SolicitacaoAssinatura.objects.filter(documento=documento).delete()
    SolicitacaoAlteracaoNivelAcesso.objects.filter(documento_texto=documento).delete()
    DocumentoTexto.objects.filter(pk=documento.pk).update(
        status=DocumentoStatus.STATUS_CONCLUIDO,
        nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
        hipotese_legal=None,
        assinatura_balizadora=None,
    )
