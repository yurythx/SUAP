"""Guarda de N+1 dos métodos por-documento de ``DocumentoDigitalizado``.

Tranca contra regressão a otimização da tela de processo
(``processo_eletronico/processo/<id>/``): os métodos abaixo devem ler as
relações reversas (``.all()``) para aproveitarem o ``prefetch_related`` feito na
listagem de documentos, em vez de refazerem ``Model.objects.filter(documento=self)``
por documento (N+1):

- ``tem_solicitacao_compartilhamento_pessoa_documento_digitalizado_pendentes``
- ``solicitacoes_compartilhamento_pessoa_documento_digitalizado_pendentes``
- ``existe_solicitacoes_nivel_acesso_aberto``

Testamos com o cache de prefetch populado em memória: se um método voltar a
consultar o banco, o ``django_assert_num_queries(0)`` falha.
"""

from types import SimpleNamespace

import pytest

from documento_eletronico.models import DocumentoDigitalizado
from documento_eletronico.models import SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa as SolicCompart
from processo_eletronico.models import SolicitacaoAlteracaoNivelAcesso

# Nomes de acesso das relações reversas = chaves do cache de prefetch do Django.
CACHE_COMPART = 'solicitacao_compartilhamento_pessoa_documento_digitalizado'
CACHE_NIVEL = 'documentodigitalizado_analise_nivel_acesso_set'


def _doc_com_cache(solic_compart, solic_nivel):
    doc = DocumentoDigitalizado(pk=1)
    doc._prefetched_objects_cache = {CACHE_COMPART: list(solic_compart), CACHE_NIVEL: list(solic_nivel)}
    return doc


@pytest.mark.django_db
def test_metodos_leem_prefetch_sem_query(django_assert_num_queries):
    """Com o cache de prefetch presente, os três métodos não tocam o banco e filtram por status."""
    compart_pendente = SimpleNamespace(pk=10, status_solicitacao=SolicCompart.STATUS_AGUARDANDO)
    compart_outro = SimpleNamespace(pk=11, status_solicitacao=SolicCompart.STATUS_AGUARDANDO + 99)
    nivel_aberto = SimpleNamespace(pk=20, situacao=SolicitacaoAlteracaoNivelAcesso.SITUACAO_SOLICITADO)
    nivel_deferido = SimpleNamespace(pk=21, situacao=SolicitacaoAlteracaoNivelAcesso.SITUACAO_DEFERIDO)

    doc = _doc_com_cache([compart_pendente, compart_outro], [nivel_aberto, nivel_deferido])

    with django_assert_num_queries(0):
        assert doc.tem_solicitacao_compartilhamento_pessoa_documento_digitalizado_pendentes is True
        assert [s.pk for s in doc.solicitacoes_compartilhamento_pessoa_documento_digitalizado_pendentes] == [10]
        assert doc.existe_solicitacoes_nivel_acesso_aberto() is True


@pytest.mark.django_db
def test_metodos_sem_pendencias_retornam_vazio_sem_query(django_assert_num_queries):
    """Sem itens pendentes no cache, os métodos retornam falso/vazio e ainda assim não consultam o banco."""
    compart_outro = SimpleNamespace(pk=11, status_solicitacao=SolicCompart.STATUS_AGUARDANDO + 99)
    nivel_deferido = SimpleNamespace(pk=21, situacao=SolicitacaoAlteracaoNivelAcesso.SITUACAO_DEFERIDO)

    doc = _doc_com_cache([compart_outro], [nivel_deferido])

    with django_assert_num_queries(0):
        assert doc.tem_solicitacao_compartilhamento_pessoa_documento_digitalizado_pendentes is False
        assert list(doc.solicitacoes_compartilhamento_pessoa_documento_digitalizado_pendentes) == []
        assert doc.existe_solicitacoes_nivel_acesso_aberto() is False
