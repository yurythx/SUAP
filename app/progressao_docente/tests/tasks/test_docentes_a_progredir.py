"""Cálculo diário da lista de docentes a progredir (comando ``docentes_a_progredir``)."""

import pytest
from django.core.management import call_command

from progressao_docente.models import DocenteAProgredir
from progressao_docente.tests.factories import DocenteAProgredirFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def test_docente_que_perdeu_o_vinculo_sai_da_lista_sem_perder_a_progressao_ja_criada(
    sync_permissions: None, capsys: pytest.CaptureFixture[str]
) -> None:
    # redistribuição (ocorrência 02100) deixa ativo=False e mantém a situação "ATIVO PERMANENTE"
    redistribuida = DocenteAProgredirFactory(avaliado=ServidorFactory(eh_docente=True, ativo=False))
    com_processo = DocenteAProgredirFactory(avaliado=ServidorFactory(eh_docente=True, ativo=False), progressao_criada=True)
    em_exercicio = DocenteAProgredirFactory(avaliado=ServidorFactory(eh_docente=True))

    call_command('docentes_a_progredir')

    restantes = set(DocenteAProgredir.objects.values_list('pk', flat=True))
    assert redistribuida.pk not in restantes
    assert {com_processo.pk, em_exercicio.pk} <= restantes
    assert 'Linhas removidas de docentes fora do quadro: 1' in capsys.readouterr().out
