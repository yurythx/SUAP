"""Homologação, pelo chefe da auditoria, dos afastamentos planejados por um auditor.

O planejamento anual em homologação só é aprovado quando o último afastamento
pendente é homologado. Homologar um afastamento não pode aprovar o planejamento
enquanto outro do **mesmo mês** ainda aguarda avaliação — senão o planejamento
sai de homologação e os pendentes restantes ficam sem como ser avaliados.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from auditoria.models import AfastamentoPlanejado, PlanejamentoAnual
from auditoria.models.afastamento import StatusAfastamento
from auditoria.models.planejamento import StatusPlanejamento
from auditoria.tests import factories as f
from comum.tests.factories import AnoFactory
from rh.tests.factories import JornadaTrabalhoFactory, ServidorFactory

ANO = 2027
OUTUBRO = 10


@pytest.fixture
def cenario_homologacao(db, sync_permissions, suap_client) -> SimpleNamespace:
    """Planejamento em homologação com dois afastamentos pendentes em outubro."""
    auditor = ServidorFactory(jornada_trabalho=JornadaTrabalhoFactory(codigo='40S', nome='40 HORAS SEMANAIS'))
    chefe_user = ServidorFactory().get_user()
    chefe_user.groups.add(Group.objects.get(name='Auditor'), Group.objects.get(name='Auditor Sistêmico'))

    planejamento = f.PlanejamentoAnualFactory(
        auditor=auditor,
        paint=f.PaintFactory(ano=AnoFactory(ano=ANO)),
        status=StatusPlanejamento.EM_HOMOLOGACAO,
    )
    outubro = f.PlanejamentoMensalFactory(planejamento_anual=planejamento, mes=OUTUBRO, carga_horaria_prevista=152)
    primeiro = f.AfastamentoPlanejadoFactory(
        planejamento=outubro, data_inicio=date(ANO, OUTUBRO, 11), data_fim=date(ANO, OUTUBRO, 11), status=StatusAfastamento.PENDENTE
    )
    segundo = f.AfastamentoPlanejadoFactory(
        planejamento=outubro, data_inicio=date(ANO, OUTUBRO, 18), data_fim=date(ANO, OUTUBRO, 27), status=StatusAfastamento.PENDENTE
    )
    suap_client.force_login(chefe_user)
    return SimpleNamespace(client=suap_client, planejamento=planejamento, primeiro=primeiro, segundo=segundo)


def _aprovar(client, afastamento: AfastamentoPlanejado):
    return client.post(
        reverse('auditoria:avaliar_afastamento', args=[afastamento.pk]),
        {
            'data_inicio': afastamento.data_inicio.strftime('%d/%m/%Y'),
            'data_fim': afastamento.data_fim.strftime('%d/%m/%Y'),
            'tipo_afastamento': afastamento.tipo_afastamento_id,
            'motivo': afastamento.motivo,
            'acao': 'aprovar',
        },
    )


def test_homologar_um_afastamento_mantem_pendente_do_mesmo_mes_avaliavel(cenario_homologacao):
    c = cenario_homologacao

    _aprovar(c.client, c.primeiro)

    assert AfastamentoPlanejado.objects.get(pk=c.primeiro.pk).status == StatusAfastamento.HOMOLOGADO
    assert PlanejamentoAnual.objects.get(pk=c.planejamento.pk).status == StatusPlanejamento.EM_HOMOLOGACAO
    resposta = c.client.get(reverse('auditoria:avaliar_afastamento', args=[c.segundo.pk]))
    assert 'Salvar' in resposta.content.decode()


def test_auditor_sem_papel_de_chefe_nao_homologa_por_post_direto(cenario_homologacao):
    # O formulário só esconde o botão Salvar de quem não pode homologar; o POST
    # precisa ser recusado também, senão basta enviá-lo à mão.
    c = cenario_homologacao
    auditor_user = ServidorFactory().get_user()
    auditor_user.groups.add(Group.objects.get(name='Auditor'))
    c.client.force_login(auditor_user)

    _aprovar(c.client, c.primeiro)

    assert AfastamentoPlanejado.objects.get(pk=c.primeiro.pk).status == StatusAfastamento.PENDENTE


def test_homologar_o_ultimo_pendente_aprova_o_planejamento(cenario_homologacao):
    c = cenario_homologacao

    _aprovar(c.client, c.primeiro)
    _aprovar(c.client, c.segundo)

    assert AfastamentoPlanejado.objects.get(pk=c.segundo.pk).status == StatusAfastamento.HOMOLOGADO
    assert PlanejamentoAnual.objects.get(pk=c.planejamento.pk).status == StatusPlanejamento.APROVADO
