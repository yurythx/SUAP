"""Fixtures dos testes da deduplicação de pessoas."""

from collections.abc import Iterator

import pytest
from django.db.models.signals import post_save

from comum.models import Comentario
from rh.models import PessoaFisica


@pytest.fixture
def pf_sem_relacionamento() -> None:
    """Pede que as PFs do teste nasçam sem relacionamento (ver ``pessoas_com_relacionamento``)."""


@pytest.fixture
def pessoas_com_relacionamento(request: pytest.FixtureRequest) -> Iterator[None]:
    """O planejar apaga a PF sem relacionamento; nos testes das outras regras, cada PF nova ganha um comentário (GFK)."""
    if 'pf_sem_relacionamento' in request.fixturenames:
        yield
        return

    def relacionar(sender: type, instance: PessoaFisica, created: bool, **kwargs: object) -> None:
        if created:
            Comentario.objects.create(content_object=instance, texto='relacionamento de teste')

    post_save.connect(relacionar, sender=PessoaFisica, weak=False, dispatch_uid='dedup-relacionamento')
    yield
    post_save.disconnect(sender=PessoaFisica, dispatch_uid='dedup-relacionamento')
