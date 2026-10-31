"""Testes do prazo da etapa atual da avaliação (exibido na listagem de processos).

`data_limite_etapa_atual()` retorna a data limite da etapa atual conforme a
situação da avaliação; `dias_restantes_etapa_atual()` retorna os dias até esse
limite (negativo = vencido), permitindo acompanhamento na listagem do admin.
"""

from datetime import date, datetime, timedelta

import pytest
from django.apps.registry import apps

from comum.tests.factories import UserFactory
from progressao_docente.tests.factories import AvaliacaoFactory, ProgressaoDocenteFactory

ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

pytestmark = pytest.mark.django_db


def _criar_avaliacao(*, dias_atras, situacao):
    progressao = ProgressaoDocenteFactory(situacao=ProgressaoDocente.AGUARDANDO_PREENCHIMENTO)
    return AvaliacaoFactory(
        progressao=progressao,
        situacao=situacao,
        data_liberacao_preenchimento=datetime.now() - timedelta(days=dias_atras),
    )


def test_prazo_preenchimento_vencido_dias_negativos(sync_permissions):
    # liberado há 40 dias, prazo padrão 30 => vencido há ~10 dias
    avaliacao = _criar_avaliacao(dias_atras=40, situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO)

    limite = avaliacao.data_limite_etapa_atual()
    assert limite is not None
    assert avaliacao.dias_restantes_etapa_atual() == (limite.date() - date.today()).days
    assert avaliacao.dias_restantes_etapa_atual() < 0


def test_prazo_preenchimento_a_vencer_dias_positivos(sync_permissions):
    # liberado há 5 dias, prazo 30 => faltam ~25 dias
    avaliacao = _criar_avaliacao(dias_atras=5, situacao=Avaliacao.AGUARDANDO_PREENCHIMENTO)

    assert avaliacao.dias_restantes_etapa_atual() > 0


def test_prazo_none_quando_etapa_sem_data(sync_permissions):
    # CONCLUIDA não tem prazo de etapa atual
    avaliacao = _criar_avaliacao(dias_atras=5, situacao=Avaliacao.CONCLUIDA)

    assert avaliacao.data_limite_etapa_atual() is None
    assert avaliacao.dias_restantes_etapa_atual() is None


def test_coluna_prazo_apenas_na_aba_iniciado(db):
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    admin_obj = site._registry[ProgressaoDocente]
    user = UserFactory(is_superuser=True)
    rf = RequestFactory()
    url = '/admin/progressao_docente/progressaodocente/'

    req_iniciado = rf.get(url, {'tab': 'tab_iniciado'})
    req_iniciado.user = user
    assert 'get_prazo' in admin_obj.get_list_display(req_iniciado)

    for tab in ('tab_a_iniciar', 'tab_finalizado'):
        req = rf.get(url, {'tab': tab})
        req.user = user
        assert 'get_prazo' not in admin_obj.get_list_display(req)

    # sem aba selecionada também não exibe
    req_sem_tab = rf.get(url)
    req_sem_tab.user = user
    assert 'get_prazo' not in admin_obj.get_list_display(req_sem_tab)
