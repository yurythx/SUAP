"""Seleção da banca avaliadora pela CPPD."""

import pytest

from professor_titular.forms import AvaliadorForm
from professor_titular.tests.factories import ProcessoTitularFactory
from rh.models import Servidor, Situacao
from rh.tests.factories import ServidorFactory, SituacaoFactory

pytestmark = pytest.mark.django_db


def _docente(codigo_situacao: str) -> Servidor:
    return ServidorFactory(eh_docente=True, situacao=SituacaoFactory(codigo=codigo_situacao))


def test_docente_em_outro_orgao_pode_ser_avaliador_interno(sync_permissions: None) -> None:
    processo = ProcessoTitularFactory()
    em_outro_orgao = _docente(Situacao.ATIVO_EM_OUTRO_ORGAO)
    substituto = _docente(Situacao.CONT_PROF_SUBSTITUTO)

    def _form(avaliador: Servidor) -> AvaliadorForm:
        return AvaliadorForm({'processo': str(processo.pk), 'avaliador_interno': [str(avaliador.pk)]}, processo=processo)

    assert _form(em_outro_orgao).is_valid()
    assert not _form(substituto).is_valid()
