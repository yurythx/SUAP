"""Criar progressão a partir do "Docente a Progredir" sem duplicar a do mesmo período (#17738)."""

import pytest
from django.contrib.auth.models import Permission

from progressao_docente.models import ProgressaoDocente
from progressao_docente.tests.factories import DocenteAProgredirFactory, ProgressaoDocenteFactory

pytestmark = pytest.mark.django_db


def _progressao_do_relatorio(relatorio, situacao):
    return ProgressaoDocenteFactory(
        avaliado=relatorio.avaliado,
        data_inicio_periodo=relatorio.data_inicio_contagem,
        nivel_atual=relatorio.nivel_atual,
        proximo_nivel=relatorio.proximo_nivel,
        relatorio_a_progredir=relatorio,
        situacao=situacao,
    )


def test_progressao_ja_avancada_nao_ganha_copia(client, sync_permissions):
    relatorio = DocenteAProgredirFactory()
    existente = _progressao_do_relatorio(relatorio, ProgressaoDocente.FINALIZADO)
    usuario = relatorio.avaliado.get_user()
    usuario.user_permissions.add(Permission.objects.get(content_type__app_label='progressao_docente', codename='change_docenteaprogredir'))
    client.force_login(usuario)

    resposta = client.get(f'/progressao_docente/criar_progressao/{relatorio.pk}/')

    assert resposta.status_code == 302
    assert resposta.url == f'/progressao_docente/ver/{existente.pk}/'
    assert ProgressaoDocente.objects.filter(avaliado=relatorio.avaliado, data_inicio_periodo=relatorio.data_inicio_contagem).count() == 1
    relatorio.refresh_from_db()
    assert relatorio.progressao_criada
    assert relatorio.progressao_finalizada


def test_excluir_copia_nao_reabre_o_relatorio_mas_excluir_a_unica_reabre(sync_permissions, django_capture_on_commit_callbacks):
    relatorio = DocenteAProgredirFactory(progressao_criada=True, progressao_finalizada=True)
    valida = _progressao_do_relatorio(relatorio, ProgressaoDocente.FINALIZADO)
    copia = ProgressaoDocenteFactory(avaliado=relatorio.avaliado, data_inicio_periodo=relatorio.data_inicio_contagem, relatorio_a_progredir=relatorio)

    with django_capture_on_commit_callbacks(execute=True):
        copia.delete()
    relatorio.refresh_from_db()
    assert relatorio.progressao_criada
    assert relatorio.progressao_finalizada

    with django_capture_on_commit_callbacks(execute=True):
        valida.delete()
    relatorio.refresh_from_db()
    assert not relatorio.progressao_criada
    assert not relatorio.progressao_finalizada
