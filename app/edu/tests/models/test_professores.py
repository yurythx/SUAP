"""Testes de ``Professor``: derivação do slug (sem DB) e acesso sistêmico em ``can_change``."""

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import Group

from edu.models.professores import Professor
from rh.tests.factories import ServidorFactory


def test_slug_from_email_deriva_do_prefixo():
    vinculo = Mock(email_notificacao='Joao.Silva@campus.edu')
    with patch.object(Professor, 'get_vinculo', return_value=vinculo):
        assert Professor().get_slug_from_email() == 'joao-silva'


def test_slug_from_email_none_sem_vinculo():
    with patch.object(Professor, 'get_vinculo', return_value=None):
        assert Professor().get_slug_from_email() is None


@pytest.mark.django_db
def test_diretor_avaliacao_regulacao_edita_professor_de_outro_campus(sync_permissions: None) -> None:
    """O grupo é sistêmico: edita professor de qualquer campus, sem setor vinculado ao papel."""
    professor = Professor.objects.create(vinculo=ServidorFactory().get_vinculo())
    diretor = ServidorFactory().get_user()  # cada ServidorFactory nasce num campus próprio
    diretor.groups.add(Group.objects.get(name='Diretor de Avaliação e Regulação do Ensino'))

    assert professor.can_change(diretor)
