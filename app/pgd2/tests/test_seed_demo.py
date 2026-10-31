"""Teste de aceitação do command ``seed_pgd2_gitlab_demo``.

Prova que o cenário seedado é *lançável de verdade*: o PIT homologado passa o
gate real ``pode_cadastrar_entrega_rit`` e ``services.lancar_rit_via_gitlab``
cria um RIT sem ``PermissionDenied``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from pgd2 import services
from rh.tests.factories import ServidorFactory

pytestmark = pytest.mark.django_db(databases='__all__')


@pytest.fixture
def servidor(db, sync_permissions):
    """Dono do PIT/RIT; um segundo servidor fica disponível para o seed usar como chefe."""
    ServidorFactory()
    return ServidorFactory()


def test_seed_deixa_cenario_lancavel_via_gitlab(servidor) -> None:

    call_command('seed_pgd2_gitlab_demo', username_gitlab='dev.poc', matricula=servidor.matricula)

    # 1) o mapeamento gitlab -> servidor foi criado
    assert services.resolver_servidor_por_gitlab_username('dev.poc') == servidor

    # 2) há entregas disponíveis com PES casável (descricao + criterios)
    entregas = services.get_entregas_disponiveis_para_servidor(servidor)
    assert len(entregas) >= 1
    entrega = entregas[0]
    assert entrega.entrega_pes is not None
    assert entrega.entrega_pes.descricao
    assert entrega.entrega_pes.criterios_avaliacao

    # 3) gate completo: lançar RIT via service real cria o RIT sem PermissionDenied
    hoje = datetime.date.today()
    rit = services.lancar_rit_via_gitlab(
        entrega,
        {
            'titulo': 't',
            'descricao': 'd',
            'tempo_executado': Decimal('2'),
            'data_inicio': hoje,
            'data_fim': hoje,
        },
        gitlab_project_id=1,
        gitlab_mr_iid=1,
    )
    assert rit.pk is not None
    assert rit.gitlab_project_id == 1
    assert rit.gitlab_mr_iid == 1


def test_seed_idempotente(servidor) -> None:

    call_command('seed_pgd2_gitlab_demo', username_gitlab='dev.poc', matricula=servidor.matricula)
    entregas_1 = services.get_entregas_disponiveis_para_servidor(servidor)

    # rodar de novo não deve duplicar a cadeia nem quebrar
    call_command('seed_pgd2_gitlab_demo', username_gitlab='dev.poc2', matricula=servidor.matricula)
    entregas_2 = services.get_entregas_disponiveis_para_servidor(servidor)

    assert len(entregas_2) == len(entregas_1)
    # username atualizado no mapeamento existente
    assert services.resolver_servidor_por_gitlab_username('dev.poc2') == servidor


def test_seed_com_oauth_app(servidor, capsys) -> None:
    call_command('seed_pgd2_gitlab_demo', username_gitlab='dev.poc', matricula=servidor.matricula, with_oauth_app=True)

    from api.models import AplicacaoOAuth2

    app = AplicacaoOAuth2.full.filter(name__icontains='POC GitLab').first()
    assert app is not None
    assert app.skip_authorization is True
    assert app.user is not None
    saida = capsys.readouterr().out
    assert 'client_id' in saida
    assert 'client_secret' in saida
