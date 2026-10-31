"""Testes do command ``descartar_rits_gitlab_orfaos``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.management import call_command

from pgd2.models import PlanoIndividualTrabalho, RelatorioIndividualTrabalho
from pgd2.tests.conftest import CadeiaRit

pytestmark = pytest.mark.django_db(databases='__all__')


@pytest.fixture
def rit_gitlab(cadeia_rit_pgd2: CadeiaRit) -> RelatorioIndividualTrabalho:
    return RelatorioIndividualTrabalho.objects.create(
        entrega_pit=cadeia_rit_pgd2.entrega_pit,
        titulo='Execução do MR !7',
        descricao='Resolve #7',
        tempo_executado=Decimal('4'),
        gitlab_project_id=42,
        gitlab_mr_iid=7,
    )


class TestDescarteOrfaos:
    def test_remove_rit_de_mr_fechado_sem_merge(
        self, cadeia_rit_pgd2: CadeiaRit, rit_gitlab: RelatorioIndividualTrabalho, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'closed'})

        call_command('descartar_rits_gitlab_orfaos')

        assert not RelatorioIndividualTrabalho.objects.filter(id=rit_gitlab.id).exists()

    def test_mantem_rit_de_mr_merged(
        self, cadeia_rit_pgd2: CadeiaRit, rit_gitlab: RelatorioIndividualTrabalho, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'merged'})

        call_command('descartar_rits_gitlab_orfaos')

        assert RelatorioIndividualTrabalho.objects.filter(id=rit_gitlab.id).exists()

    def test_erro_de_rede_nao_aborta_lote_e_mantem_rit(
        self, cadeia_rit_pgd2: CadeiaRit, rit_gitlab: RelatorioIndividualTrabalho, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)

        def _explode(pid: int, iid: int) -> dict:
            raise ConnectionError('boom')

        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', _explode)

        # Não deve levantar: a falha de rede é tolerada e o lote prossegue.
        call_command('descartar_rits_gitlab_orfaos')

        assert RelatorioIndividualTrabalho.objects.filter(id=rit_gitlab.id).exists()

    def test_dry_run_nao_remove(self, cadeia_rit_pgd2: CadeiaRit, rit_gitlab: RelatorioIndividualTrabalho, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'closed'})

        call_command('descartar_rits_gitlab_orfaos', '--dry-run')

        assert RelatorioIndividualTrabalho.objects.filter(id=rit_gitlab.id).exists()

    def test_mantem_rit_de_mr_aberto(
        self, cadeia_rit_pgd2: CadeiaRit, rit_gitlab: RelatorioIndividualTrabalho, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)
        monkeypatch.setattr('djtools.utils.gitlab.get_merge_request', lambda pid, iid: {'state': 'opened'})

        call_command('descartar_rits_gitlab_orfaos')

        assert RelatorioIndividualTrabalho.objects.filter(id=rit_gitlab.id).exists()
