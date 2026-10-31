import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

# `suap_client` e `sync_permissions` vêm do plugin global (`pytest_plugins` no conftest raiz);
# não as importamos aqui para poder usá-las como parâmetro de fixture.
from remanejamento.models import Edital
from rh.models import TipoUnidadeOrganizacional, UnidadeOrganizacional
from rh.tests.factories import (
    CargoEmpregoFactory,
    GrupoCargoEmpregoFactory,
    ServidorFactory,
    SetorFactory,
    UnidadeOrganizacionalFactory,
)

SENHA = '123'


INICIO_EXERCICIO = datetime.date(2010, 1, 1)


def _servidor_do_fluxo(**kwargs):
    """Servidor pronto para os fluxos de remoção interna.

    Duas coisas que o ``suap_data`` dava e o ``ServidorFactory`` não dá:

    * senha — os fluxos autenticam de verdade (``client.login``);
    * ``data_inicio_exercicio_no_cargo`` — o form da inscrição ignora o valor postado e
      copia o do servidor (``forms.py``, ``form.instance.inicio_exercicio = ...``); sem ela
      o INSERT da inscrição viola o NOT NULL da coluna.
    """
    servidor = ServidorFactory(
        data_inicio_exercicio_na_instituicao=INICIO_EXERCICIO,
        data_inicio_exercicio_no_cargo=INICIO_EXERCICIO,
        **kwargs,
    )
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor


# --- Fixtures de fluxo (Remoção Interna) -------------------------------------
# Montam o estado mínimo de cada etapa com as factories; os fluxos (cadastrar edital,
# inscrever-se) são exercitados pelos endpoints reais nos testes.


@pytest.fixture
def servidor_coordenador(sync_permissions):
    servidor = _servidor_do_fluxo()
    servidor.get_user().groups.add(Group.objects.get(name='Coordenador de Remanejamento'))
    return servidor


@pytest.fixture
def coordenador(suap_client, servidor_coordenador):
    """Client autenticado como Coordenador de Remanejamento — quem abre os editais."""
    suap_client.login(username=servidor_coordenador.get_user().username, password=SENHA)
    return suap_client


@pytest.fixture
def candidato(sync_permissions):
    """Servidor cujo cargo o torna elegível ao edital (ver fixture `edital`)."""
    return _servidor_do_fluxo()


@pytest.fixture
def servidor_de_outro_cargo(sync_permissions):
    """Inelegível por cargo.

    O cargo precisa ser informado: o ``CargoEmpregoFactory`` usa ``django_get_or_create``
    num código fixo, então dois ``ServidorFactory`` nascem com o MESMO cargo — e o teste do
    inelegível passaria sem testar nada.
    """
    return _servidor_do_fluxo(cargo_emprego=CargoEmpregoFactory(codigo='02', nome='Cargo B'))


@pytest.fixture
def campus(db):
    """Campus de destino das vagas, distinto do de origem dos servidores.

    Precisa de ``tipo``: o form do edital lista ``UnidadeOrganizacional.objects.uo()``, que
    filtra por campus/reitoria. A UO que o ``SetorFactory`` cria sozinho nasce sem tipo e o
    form a recusa com "Escolha(s) inválida(s)".
    """
    tipo, _ = TipoUnidadeOrganizacional.objects.get_or_create(id=UnidadeOrganizacional.TIPO_REITORIA, defaults={'descricao': 'Reitoria'})
    return UnidadeOrganizacionalFactory(setor=SetorFactory(campus=False), tipo=tipo)


@pytest.fixture
def edital(servidor_coordenador, candidato, campus):
    """Edital de TAE aberto para inscrições, restrito ao cargo do `candidato`."""
    agora = datetime.datetime.now()
    edital = Edital.objects.create(
        categoria=Edital.TAE,
        titulo='Remoção Interna para Cargo X',
        descricao='Descrição de Remoção Interna para cargo X',
        chave_hash='uma_chave_hash',
        inicio_inscricoes=agora - datetime.timedelta(days=1),
        fim_inscricoes=agora + datetime.timedelta(days=7),
        inicio_resultados=agora + datetime.timedelta(days=10),
        data_homologacao_resultado=agora + datetime.timedelta(days=15),
    )
    edital.cargos.add(candidato.cargo_emprego)
    edital.campus.add(campus)
    edital.coordenadores.add(servidor_coordenador.get_user())
    return edital


@pytest.fixture
def estrutura_remocao(db, sync_permissions, suap_client):
    """Topologia completa do fluxo de remoção interna: dois campi, com equivalente SIAPE.

    Reusa o helper `cadastrar_setor` (que continua em `comum.pytest_fixtures`, é só helper,
    não fixture) porque ele monta exatamente o par SUAP/SIAPE que o fluxo exige: o
    processamento do resultado resolve o campus de destino **casando pela sigla** da UO
    SIAPE, e é por isso que o teste precisa corrigi-la — `cadastrar_setor` cria a UO SIAPE
    sem sigla, como em produção.

    Os quatro servidores ficam distribuídos como no antigo `suap_data`: `a` e `c` no campus
    A, `b` e `d` no campus B. A distribuição importa — o fluxo é justamente sobre mudar de
    campus.
    """
    from comum.pytest_fixtures import cadastrar_setor

    tipo, _ = TipoUnidadeOrganizacional.objects.get_or_create(id=UnidadeOrganizacional.TIPO_REITORIA, defaults={'descricao': 'Reitoria'})

    raiz_suap, _ = cadastrar_setor('RAIZ')
    setor_re, _ = cadastrar_setor('RE', raiz_suap, '00001')
    setor_a0, setor_a0_siape = cadastrar_setor('A0', raiz_suap, '00002')
    setor_b0, setor_b0_siape = cadastrar_setor('B0', raiz_suap, '00003')

    # `cadastrar_setor` cria a UO do campus SEM tipo, e o form do edital lista
    # `UnidadeOrganizacional.objects.uo()`, que filtra justamente por ele: sem isto o campus
    # é recusado com "Escolha(s) inválida(s): A0, B0".
    UnidadeOrganizacional.objects.filter(pk__in=[setor_a0.uo_id, setor_b0.uo_id]).update(tipo=tipo)
    setor_a0.refresh_from_db()
    setor_b0.refresh_from_db()

    admin = _servidor_do_fluxo(setor=SetorFactory(sigla='A1', superior=setor_a0))
    usuario_admin = admin.get_user()
    usuario_admin.is_superuser = True
    usuario_admin.is_staff = True
    usuario_admin.save(update_fields=['is_superuser', 'is_staff'])

    return SimpleNamespace(
        client=suap_client,
        admin=admin,
        servidor_a=_servidor_do_fluxo(setor=SetorFactory(sigla='A1x', superior=setor_a0)),
        servidor_b=_servidor_do_fluxo(setor=SetorFactory(sigla='B1', superior=setor_b0)),
        servidor_c=_servidor_do_fluxo(setor=SetorFactory(sigla='A2', superior=setor_a0)),
        servidor_d=_servidor_do_fluxo(setor=SetorFactory(sigla='B2', superior=setor_b0)),
        grupo_cargo_emprego=GrupoCargoEmpregoFactory(),
        setor_raiz_suap=raiz_suap,
        setor_re_suap=setor_re,
        campus_a_suap=setor_a0.uo,
        campus_b_suap=setor_b0.uo,
        campus_a_suap_siape=setor_a0_siape.uo,
        campus_b_suap_siape=setor_b0_siape.uo,
    )
