"""Atualização dos dados do participante quando o CPF não tem vínculo do perfil (#17537).

``PerfilParticipanteForm.save`` chamava ``Participante.checar_vinculo``, que levanta
``ValidationError`` quando o CPF não tem vínculo ativo do perfil (aluno, servidor...): a
tela respondia 500. Agora a checagem roda na validação e vira erro do campo CPF.
"""

from __future__ import annotations

import pytest

from eventos.forms import PerfilParticipanteForm
from eventos.models import Participante, PublicoAlvoEvento
from eventos.tests.factories import ParticipanteFactory, PublicoAlvoEventoFactory

pytestmark = pytest.mark.django_db


def _dados(participante: Participante, **campos: str) -> dict[str, str]:
    return {'nome': participante.nome, 'cpf': participante.cpf, 'email': participante.email, **campos}


def test_cpf_sem_vinculo_do_perfil_vira_erro_do_formulario() -> None:
    participante = ParticipanteFactory(publico_alvo=PublicoAlvoEventoFactory(id=PublicoAlvoEvento.ESTUDANTES))

    form = PerfilParticipanteForm(_dados(participante), instance=participante)

    assert not form.is_valid()
    assert 'Nenhum vículo de' in form.errors['cpf'][0]


def test_publico_externo_atualiza_sem_exigir_vinculo() -> None:
    participante = ParticipanteFactory(publico_alvo=PublicoAlvoEventoFactory())

    form = PerfilParticipanteForm(_dados(participante, nome='Nome Atualizado'), instance=participante)

    assert form.is_valid(), form.errors
    form.save()
    assert Participante.objects.get(pk=participante.pk).nome == 'Nome Atualizado'
