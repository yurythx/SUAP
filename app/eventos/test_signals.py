from datetime import date, time
from unittest.mock import patch

import pytest

from eventos.models import CriterioAvaliacao, Evento, FluxoSubmissao, Modalidade, TipoParticipacao, TipoParticipante
from eventos.signals import (
    recalcular_flags_criterio_delete,
    recalcular_flags_fluxo_delete,
    recalcular_flags_modalidade_delete,
    recalcular_flags_tipo_participante_delete,
)
from djtools.middleware import threadlocals as tl
from rh.models import Setor, UnidadeOrganizacional

PK_INEXISTENTE = 10**9


@pytest.fixture(autouse=True)
def _threadlocal_sem_usuario():
    """
    Zera o usuário do threadlocal, que o `ThreadLocals` não limpa ao fim da requisição.

    Sem isso, o `CurrentUserField` do Evento herda o usuário logado por outro teste do
    mesmo worker; como aquele teste já sofreu rollback, o INSERT aponta para um usuário
    inexistente e o save levanta `User.DoesNotExist`.
    """
    tl.context.user = None
    yield
    tl.context.user = None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('receiver', 'instance'),
    [
        (recalcular_flags_modalidade_delete, Modalidade(evento_id=PK_INEXISTENTE)),
        (recalcular_flags_tipo_participante_delete, TipoParticipante(evento_id=PK_INEXISTENTE)),
        (recalcular_flags_fluxo_delete, FluxoSubmissao(evento_id=PK_INEXISTENTE)),
        (recalcular_flags_criterio_delete, CriterioAvaliacao(modalidade_id=PK_INEXISTENTE)),
    ],
)
def test_recalculo_no_delete_nao_levanta_quando_evento_ja_foi_apagado(receiver, instance) -> None:
    """Cascade do Evento apaga os filhos: no on_commit o pai já não existe."""
    with patch('eventos.signals.transaction.on_commit', side_effect=lambda fn: fn()):
        receiver(type(instance), instance)


@pytest.mark.django_db
def test_delete_de_evento_com_tipo_participante_nao_levanta(django_capture_on_commit_callbacks) -> None:
    """Repro original: o cascade apaga os filhos e o on_commit relia a FK do pai."""
    setor = Setor.objects.create(sigla='E2E', nome='Setor E2E')
    campus = UnidadeOrganizacional.objects.create(nome='Campus E2E', sigla='E2E', setor=setor)
    evento = Evento.objects.create(
        nome='Evento E2E',
        apresentacao='Apresentação',
        local='Local',
        data_inicio=date(2026, 1, 1),
        hora_inicio=time(8, 0),
        campus=campus,
        gera_certificado=False,
    )
    TipoParticipante.objects.create(evento=evento, tipo_participacao=TipoParticipacao.objects.create(descricao='Ouvinte'))

    with django_capture_on_commit_callbacks(execute=True):
        evento.delete()

    assert not Evento.objects.filter(pk=evento.pk).exists()


def test_recalculo_no_delete_repassa_o_id_do_evento_ao_helper() -> None:
    """O receiver deve usar `evento_id` (sem tocar o descritor da FK)."""
    instance = TipoParticipante(evento_id=42)

    with (
        patch('eventos.signals.transaction.on_commit', side_effect=lambda fn: fn()),
        patch('eventos.signals._recalcular_flags_evento') as recalcular,
    ):
        recalcular_flags_tipo_participante_delete(TipoParticipante, instance)

    recalcular.assert_called_once_with(42)
