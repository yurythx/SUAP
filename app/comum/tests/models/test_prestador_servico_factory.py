"""``PrestadorServicoFactory`` entrega um prestador cuja pessoa já enxerga o próprio vínculo."""

from __future__ import annotations

import pytest

from comum.tests.factories import PrestadorServicoFactory
from rh.tests.factories import SetorFactory


@pytest.mark.django_db
@pytest.mark.usefixtures('sync_permissions')
def test_pessoa_do_prestador_e_marcada_como_prestador_e_acha_o_vinculo() -> None:
    """Sem o re-save da pessoa depois do prestador, ``eh_prestador`` ficava falso e
    ``PessoaFisica.get_vinculo()`` quebrava (500 na tela do NAPNE do edu)."""
    prestador = PrestadorServicoFactory(setor=SetorFactory())
    pessoa = prestador.pessoa_fisica
    pessoa.refresh_from_db()

    assert pessoa.eh_prestador
    assert pessoa.get_vinculo() == prestador.get_vinculo()
