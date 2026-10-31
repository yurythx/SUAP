"""Substrato da rodada de geração da doc de usuário do ``pgd2`` (Programa de Gestão).

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

O módulo não tem ``features/`` nem ``tests/e2e/`` — o roteiro e o seed foram PROPOSTOS
por este subagente a partir de ``menu.yaml``, ``urls.py`` e ``models.py`` (nada foi colhido
de ``.feature``, e a revisão do MR precisa saber disso).

Papéis (servidores criados por factories no ``doc_seed``, #17486):

- ``servidor``: grupo ``Servidor`` (``rh.eh_servidor``), no setor A1 (campus A0) — o mesmo
  setor que o ``chefe`` chefia, condição para o chefe enxergar e avaliar as solicitações e os
  planos do servidor (``setores_que_sou_chefe_hoje`` em ``pgd2/utils.py:22``).
- ``chefe``: servidor próprio do módulo (155102) com ``ServidorFuncaoHistorico`` de chefia
  (função FG) no A1 — o papel que o 1111111 do seed legado do behave fazia. A chefia vem da
  função; o grupo ``Chefe de Setor`` entra por segurança.

Seed de domínio (tudo via ORM, no ``doc_seed``): a cadeia que ``pode_solicitar``
(``pgd2/models.py:2797``) e ``pode_iniciar_cadastro`` (``pgd2/models.py:4695``) exigem
para o servidor conseguir cadastrar PIT:

1. ``ConfiguracaoPerfilServidor`` vigente para TAE com a situação do servidor;
2. ``DocumentoAdesaoServidor`` vigente;
3. ``ConfiguracaoOrientacaoPit`` sistêmica vigente;
4. ``PeriodoPes`` + ``PeriodoPitRit`` vigentes cobrindo o período de hoje;
5. ``PlanoEntregasSetorial`` APROVADO do setor A1 para o período PES;
6. adesão PGD deferida e adesão PES deferida para o servidor, no mesmo período;
7. uma entrega no PES do A1 (é ela que o servidor vincula à entrega do PIT na tela de
   ``selecionar_entrega_pes_cadastrar_entrega_pit``, e é o vínculo que o RIT exige).

Rodar::

    DATABASE_PORT=5433 TEST_DATABASE_NAME=test_suap_pgd2_doc_e2e \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m doc pgd2/tests/doc/
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores, setor

# Apelido -> matrícula. `chefe` chefia o A1 (função criada no `doc_seed`).
PAPEIS = {'servidor': '155101', 'chefe': '155102', 'gestor': '155103', 'novato': '155104'}

# Matrícula -> (nome, grupos); todos no setor A1. O `novato` fica sem adesão vigente nem
# solicitação pendente: é o estado que `pode_solicitar` (``pgd2/models.py:2797``) exige para
# a tarefa 1 (o 155101 já tem adesão deferida porque é dele que as tarefas de PIT/RIT precisam).
SERVIDORES = {
    '155101': ('Servidor PGD Doc', ['Servidor']),
    '155102': ('Chefe PGD Doc', ['Servidor', 'Chefe de Setor']),
    '155103': ('Gestor PGD Doc', ['Gestor do PGD 2']),
    '155104': ('Novato PGD Doc', ['Servidor']),
}

DESTINO = Path(settings.BASE_DIR) / 'pgd2' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405


def _criar_cadeia_adesao(servidor, setor, hoje: date) -> dict:
    """A cadeia PGD → PES que libera o cadastro de PIT, criada por ORM.

    Devolve os objetos para os testes enxergarem (e para criarem PITs adicionais).
    """
    from pgd2.models import (
        ConfiguracaoOrientacaoPit,
        ConfiguracaoPerfilServidor,
        DocumentoAdesaoServidor,
        PeriodoPes,
        PeriodoPitRit,
        PlanoEntregasSetorial,
        PlanoEntregasSetorialEntregas,
        SolicitacaoAdesaoPesServidor,
        SolicitacaoAdesaoServidor,
    )
    from rh.models import Situacao

    situacao = Situacao.objects.get(codigo=Situacao.ATIVO_PERMANENTE)

    perfil, _ = ConfiguracaoPerfilServidor.objects.get_or_create(
        categoria=ConfiguracaoPerfilServidor.PERFIL_TAE,
        data_inicio=hoje - timedelta(days=400),
        data_fim=None,
        cancelado=False,
        deve_ter_funcao=False,
    )
    perfil.situacoes.add(situacao)

    documento_adesao, _ = DocumentoAdesaoServidor.objects.get_or_create(
        descricao='Regras de adesão ao PGD vigentes (doc de usuário)',
        data_inicio=hoje - timedelta(days=400),
        data_fim=None,
        cancelado=False,
    )

    ConfiguracaoOrientacaoPit.objects.get_or_create(
        orientacao='Orientação sistêmica para o preenchimento do plano individual de trabalho (doc de usuário)',
        eh_sistemica=True,
        data_inicio=hoje - timedelta(days=400),
        data_fim=None,
        cancelado=False,
    )

    periodo_pes, _ = PeriodoPes.objects.get_or_create(
        titulo='PES doc de usuário',
        data_inicio=hoje - timedelta(days=60),
        data_fim=hoje + timedelta(days=120),
        cancelado=False,
    )
    periodo_pit_rit, _ = PeriodoPitRit.objects.get_or_create(
        periodo_pes=periodo_pes,
        titulo='PIT/RIT doc de usuário',
        data_inicio=hoje - timedelta(days=30),
        data_fim=hoje + timedelta(days=90),
        cancelado=False,
    )

    pes, _ = PlanoEntregasSetorial.objects.get_or_create(
        periodo_pes=periodo_pes,
        setor=setor,
        situacao=PlanoEntregasSetorial.APROVADO,
        doc_percentual_maximo_teletrabalho=100,
    )
    entrega_pes, _ = PlanoEntregasSetorialEntregas.objects.get_or_create(
        pes=pes,
        titulo='Entrega de exemplo do PES',
        descricao='Entrega do plano de entregas setorial usada como exemplo na doc de usuário.',
        metrica=PlanoEntregasSetorialEntregas.PERCENTUAL,
        meta=100,
    )

    adesao_pgd, _ = SolicitacaoAdesaoServidor.objects.get_or_create(
        servidor=servidor,
        situacao=SolicitacaoAdesaoServidor.DEFERIDO,
        data_inicio=hoje - timedelta(days=60),
        documento_adesao=documento_adesao,
        preferencia_contato=SolicitacaoAdesaoServidor.PREFERENCIA_CONTATO_LIGACAO,
        telefone='(84) 99999-9999',
    )
    SolicitacaoAdesaoPesServidor.objects.get_or_create(
        adesao=adesao_pgd,
        setor=setor,
        situacao=SolicitacaoAdesaoPesServidor.DEFERIDO,
    )

    return {
        'perfil': perfil,
        'documento_adesao': documento_adesao,
        'periodo_pes': periodo_pes,
        'periodo_pit_rit': periodo_pit_rit,
        'pes': pes,
        'entrega_pes': entrega_pes,
        'adesao_pgd': adesao_pgd,
    }


def _criar_chefia(chefe, setor_chefiado) -> None:
    """Chefia (função FG) de ``chefe`` sobre ``setor_chefiado``, desde 2010."""
    from rh.models import Funcao, ServidorFuncaoHistorico
    from rh.tests.factories import FuncaoFactory

    ServidorFuncaoHistorico.objects.get_or_create(
        servidor=chefe,
        funcao=FuncaoFactory(codigo=Funcao.CODIGO_FG, nome='Chefe de Setor'),
        data_inicio_funcao=date(2010, 1, 1),
        setor=setor_chefiado,
        setor_suap=setor_chefiado,
    )


@pytest.fixture(scope='session')
def doc_seed(e2e_seed) -> dict:
    """Usuários da doc + chefia do A1 + cadeia PGD/PES do servidor, antes da 1ª request.

    Session-scoped e eager pelo mesmo motivo dos e2e: o cache de permissão é por processo,
    então um usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
    from rh.models import ModalidadePGD, Servidor

    setor_a1 = setor('A1', campus('A0'))
    criar_servidores(setor_a1, SERVIDORES)
    _criar_chefia(Servidor.objects.get(matricula=PAPEIS['chefe']), setor_a1)

    servidor = Servidor.objects.get(matricula=PAPEIS['servidor'])
    # `get_pendencia_geral_servidor_pgd` (`pgd2/pendencias_alertas.py:9`) compara o SUAP
    # com o SouGov; sem API externa configurada o SouGov é a própria base (`participa_pgd`
    # + `modalidade_pgd` do servidor, `pgd2/utils.py:712-716`). Sem estes dois campos o
    # servidor "não participa do PGD no SouGov" e a homologação do PIT/RIT é bloqueada
    # por pendência — medido na rodada.
    servidor.participa_pgd = True
    servidor.modalidade_pgd = ModalidadePGD.objects.get_or_create(nome='integral')[0]
    servidor.save()

    return _criar_cadeia_adesao(servidor, setor_a1, date.today())


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada como o usuário daquele papel de ``PAPEIS``."""

    def _logado(papel: str):
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def servidor_pgd(doc_seed) -> object:
    """O servidor da doc (155101), com a adesão vigente já deferida pelo seed."""
    from rh.models import Servidor

    return Servidor.objects.get(matricula=PAPEIS['servidor'])
