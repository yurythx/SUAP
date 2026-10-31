"""Fixtures de fluxo do Protocolo.

Montam o estado mínimo por ORM: um cadastrador autenticado e um processo recém
aberto. Os trâmites de cada cenário são criados pela fixture-fábrica
`criar_tramite`, deixando os testes livres para exercitar apenas a ação em
exame (encaminhar, receber, editar, verificar atraso).
"""

from datetime import datetime

import pytest
from django.contrib.auth.models import Group, Permission

# `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest raiz);
# não as importamos aqui para poder usá-las como parâmetro de fixture.
from protocolo.models import Processo, Tramite
from rh.tests.factories import ServidorFactory, SetorFactory

SENHA = '123'


def _servidor_logavel(**kwargs):
    """O ``ServidorFactory`` não define senha e os fluxos autenticam de verdade."""
    servidor = ServidorFactory(**kwargs)
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor


@pytest.fixture
def servidor_cadastrador(db, sync_permissions):
    """Servidor com permissão de cadastrar/receber processos."""
    servidor = _servidor_logavel()
    servidor.get_user().groups.add(Group.objects.get(name='Cadastrador de processos'))
    return servidor


@pytest.fixture
def cadastrador(suap_client, servidor_cadastrador):
    """Client autenticado como o servidor cadastrador."""
    suap_client.login(username=servidor_cadastrador.get_user().username, password=SENHA)
    return suap_client


@pytest.fixture
def campus_do_tramite(db):
    """Campus comum aos setores dos trâmites.

    `Setor` sem superior vira campus próprio no `SetorFactory`, e `is_atrasado()` consulta
    `tempo_tramite_mesmo_campus`: setores em campi diferentes cairiam noutro prazo. No
    `suap_data` os setores usados nos trâmites eram irmãos do mesmo campus.
    """
    return SetorFactory()


# Três setores quaisquer, distintos entre si e irmãos no mesmo campus: os testes só
# precisam de origem e destino diferentes, nunca de um setor específico da árvore.
@pytest.fixture
def setor_a(campus_do_tramite):
    return SetorFactory(superior=campus_do_tramite)


@pytest.fixture
def setor_b(campus_do_tramite):
    return SetorFactory(superior=campus_do_tramite)


@pytest.fixture
def setor_c(campus_do_tramite):
    return SetorFactory(superior=campus_do_tramite)


@pytest.fixture
def processo(servidor_cadastrador):
    """Processo recém-aberto, ainda sem trâmite, do setor do cadastrador."""
    servidor = servidor_cadastrador
    return Processo.objects.create(
        vinculo_cadastro=servidor.get_vinculo(),
        assunto='Assunto Qualquer',
        tipo=1,
        setor_origem=servidor.setor,
    )


@pytest.fixture
def criar_tramite(servidor_cadastrador):
    """Fábrica de trâmites: encaminhamento (e opcionalmente recebimento) de um processo."""

    def _criar(processo, *, encaminha_de, recebe_em, data_encaminhamento=None, data_recebimento=None, vinculo_recebimento=None):
        return Tramite.objects.create(
            processo=processo,
            ordem=processo.tramite_set.count() + 1,
            tipo_encaminhamento=Tramite.TIPO_ENCAMINHAMENTO_INTERNO,
            orgao_interno_encaminhamento=encaminha_de,
            vinculo_encaminhamento=servidor_cadastrador.get_vinculo(),
            data_encaminhamento=data_encaminhamento or datetime.now(),
            orgao_interno_recebimento=recebe_em,
            data_recebimento=data_recebimento,
            vinculo_recebimento=vinculo_recebimento,
            observacao_encaminhamento='Despachei',
        )

    return _criar


@pytest.fixture
def editor_em_tramite(db, sync_permissions):
    """Usuário com a permissão de editar processo já em trâmite."""
    user = ServidorFactory().get_user()
    user.user_permissions.add(Permission.objects.get(codename='pode_editar_processo_em_tramite'))
    return user


@pytest.fixture
def editor_sem_tramite_completo(db, sync_permissions):
    """Usuário com a permissão de editar apenas processos sem trâmite completo."""
    user = ServidorFactory().get_user()
    user.user_permissions.add(Permission.objects.get(codename='pode_editar_processo_sem_tramite_completo'))
    return user
