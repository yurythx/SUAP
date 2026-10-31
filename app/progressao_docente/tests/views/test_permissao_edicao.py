"""Quem pode editar um processo de progressão docente no admin (issue #17156)."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from comum.tests.factories import UserFactory
from progressao_docente.admin import ProgressaoDocenteAdmin
from progressao_docente.models import ProgressaoDocente
from progressao_docente.tests.factories import ProgressaoDocenteFactory
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db


def _admin():
    return ProgressaoDocenteAdmin(ProgressaoDocente, AdminSite())


def _request(user):
    request = RequestFactory().get('/admin/progressao_docente/progressaodocente/')
    request.user = user
    return request


def _processo(situacao=ProgressaoDocente.REAVALIACAO):
    """O avaliado sai em ``processo.avaliado`` quando o teste precisa dele."""
    return ProgressaoDocenteFactory(situacao=situacao)


def _com_rh_sistemico(servidor):
    user = servidor.get_user()
    user.user_permissions.add(Permission.objects.get(content_type__app_label='rh', codename='eh_rh_sistemico'))
    # has_perm memoiza as permissões no objeto; recarrega para enxergar a que acabou de ser concedida.
    return type(user).objects.get(pk=user.pk)


class TestPermissaoEdicao:
    def test_avaliado_nao_edita_o_proprio_processo(self, sync_permissions):
        """Bug do chamado 10617: reaberto para reavaliação, o avaliado alterava os Níveis."""
        processo = _processo()
        assert _admin().has_change_permission(_request(processo.avaliado.get_user()), processo) is False

    def test_usuario_sem_papel_nao_edita(self, sync_permissions):
        processo = _processo()
        assert _admin().has_change_permission(_request(ServidorFactory().get_user()), processo) is False

    def test_rh_sistemico_edita_processo_em_andamento(self, sync_permissions):
        processo = _processo()
        rh = _com_rh_sistemico(ServidorFactory())
        assert _admin().has_change_permission(_request(rh), processo) is True

    def test_rh_sistemico_edita_processo_finalizado(self, sync_permissions):
        processo = _processo(ProgressaoDocente.FINALIZADO)
        rh = _com_rh_sistemico(ServidorFactory())
        assert _admin().has_change_permission(_request(rh), processo) is True

    def test_superusuario_edita_ate_processo_finalizado(self, sync_permissions):
        processo = _processo(ProgressaoDocente.FINALIZADO)
        assert _admin().has_change_permission(_request(UserFactory(is_superuser=True)), processo) is True

    def test_permissao_generica_do_superusuario_e_preservada(self, db):
        """Sem `obj`, o admin pergunta pela permissão genérica (índice, redirecionamento
        pós-salvamento). Negá-la ao superusuário o jogaria para fora da listagem."""
        assert _admin().has_change_permission(_request(UserFactory(is_superuser=True))) is True
