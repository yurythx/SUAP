"""Tests for beat.admin — ResultadoExecucaoAdmin configuration."""

from unittest import mock

import pytest

from beat.admin import ResultadoExecucaoAdmin
from beat.models import ResultadoExecucao


@pytest.fixture
def admin_instance():
    return ResultadoExecucaoAdmin(
        model=ResultadoExecucao,
        admin_site=mock.MagicMock(),
    )


@pytest.mark.django_db
def test_has_add_permission_false(admin_instance, rf):
    request = rf.get('/admin/beat/resultadoexecucao/')
    assert admin_instance.has_add_permission(request) is False


@pytest.mark.django_db
def test_has_change_permission_false(admin_instance, rf):
    request = rf.get('/admin/beat/resultadoexecucao/')
    assert admin_instance.has_change_permission(request) is False
