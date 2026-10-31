"""Substrato da rodada de geração da doc de usuário do ``pnp`` (Plataforma Nilo Peçanha).

Esta suíte NÃO é de regressão: ela navega o sistema vivo para descobrir o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma.

O módulo não tem ``features/`` nem ``tests/e2e/`` e não aparece em
``docs/agents/inventario-tarefas.yaml``: o roteiro foi PROPOSTO a partir de ``menu.yaml``,
``admin.py`` e das telas de importação (a revisão do MR precisa saber disso).

Papel: ``coletor`` (grupo ``Coletor de Dados`` — o único que o ``permissions.yaml`` do
módulo declara, ver ``bin/scripts/papeis.py``).

O seed de domínio reproduz o mínimo que as importações precisam para resolver vínculos:
uma unidade organizacional, uma área do conhecimento, um eixo tecnológico, um servidor com
matrícula SIAPE, um aluno com CPF/curso e uma estrutura já importada. As pendências
(estrutura sem unidade, servidor sem vínculo, matrícula sem aluno) também são semeadas por
ORM: são elas que a tarefa de revisão corrige pela tela.

Rodar::

    DATABASE_PORT=5433 TEST_DATABASE_NAME=test_suap_doc_e2e \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m doc pnp/tests/doc/
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import aluno_com_login, campus, servidor_com_login

PAPEIS = {'coletor': 'PNPDOC1'}

DESTINO = Path(settings.BASE_DIR) / 'pnp' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405


@pytest.fixture(scope='session')
def doc_seed(e2e_seed):
    """Usuários e domínio da doc, antes da primeira request.

    Session-scoped e eager pelo mesmo motivo dos e2e: o cache de permissão é por processo,
    então um usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
    from edu.models import EixoTecnologico
    from pnp.models import EstruturaPNP, MatriculaPNP, ServidorPNP
    from rh.models import AreaConhecimento
    from rh.tests.factories import cpf_valido

    unidade = campus('PNP1', 'Campus Demonstração PNP')
    unidade_pendente = campus('PNP2', 'Campus Demonstração PNP Dois')
    coletor = servidor_com_login(
        PAPEIS['coletor'],
        unidade,
        grupos=['Coletor de Dados'],
        staff=True,
        pessoa_fisica__nome='Coletor PNP Doc',
        pessoa_fisica__cpf=cpf_valido(900001),
    )
    importado = servidor_com_login(
        '900002',
        unidade,
        staff=False,
        pessoa_fisica__nome='Servidor PNP Importado',
        pessoa_fisica__cpf=cpf_valido(900002),
    )
    livre = servidor_com_login(
        '900003',
        unidade,
        staff=False,
        pessoa_fisica__nome='Servidor PNP Livre',
        pessoa_fisica__cpf=cpf_valido(900003),
    )
    aluno = aluno_com_login(
        '2026001',
        unidade,
        'Aluno PNP Doc',
        codigo_curso='PNPDOC',
        pessoa_fisica__cpf=cpf_valido(2026001),
    )
    aluno_livre = aluno_com_login(
        '2026002',
        unidade,
        'Aluno PNP Livre',
        codigo_curso='PNPDOC',
        pessoa_fisica__cpf=cpf_valido(2026002),
    )

    # filter-first e não `update_or_create`: o manager desses models usa `select_for_update`
    # com join anulável, que o Postgres recusa ("FOR UPDATE cannot be applied to the nullable
    # side of an outer join").
    AreaConhecimento.objects.get_or_create(codigo='10300007', defaults={'descricao': 'Física'})
    EixoTecnologico.objects.get_or_create(codigo_inep='PNP-DOC', defaults={'descricao': 'Informação e Comunicação'})

    # Estrutura de uma importação anterior: as matrículas e os servidores dependem dela.
    # Fica sem unidade de propósito — a importação de estruturas da tarefa 1 é quem pode
    # vinculá-la, e uma UO já ocupada nunca é transferida para outro código.
    estrutura = EstruturaPNP.objects.filter(codigo='PNP1-EST').first()
    if estrutura is None:
        estrutura = EstruturaPNP.objects.create(codigo='PNP1-EST', nome=unidade.nome)
    if estrutura.uo_id or estrutura.nome != unidade.nome:
        estrutura.uo = None
        estrutura.nome = unidade.nome
        estrutura.save()
    # Pendências que a tarefa de revisão resolve pela tela.
    EstruturaPNP.objects.filter(codigo='PNP1-SEM-UO').first() or EstruturaPNP.objects.create(codigo='PNP1-SEM-UO', nome='Unidade Não Identificada')
    ServidorPNP.objects.filter(matricula='PNPSRV1').first() or ServidorPNP.objects.create(
        matricula='PNPSRV1',
        nome='Servidor Sem Vínculo',
        cpf='111.222.333-44',
        unidade=unidade.nome,
        codigo_estrutura='PNP1-EST',
        estrutura=estrutura,
    )
    MatriculaPNP.objects.filter(matricula='PNPMAT1').first() or MatriculaPNP.objects.create(
        matricula='PNPMAT1',
        nome='Aluno Sem Vínculo',
        cpf='000.000.000-00',
        curso='Técnico em Informática',
        unidade=unidade.nome,
        codigo_estrutura='PNP1-EST',
        estrutura=estrutura,
    )
    # Os campos de texto do modelo não são `blank`; o formulário do admin os exige preenchidos.
    ServidorPNP.objects.filter(matricula='PNPSRV1').update(
        cpf='111.222.333-44', unidade=unidade.nome, codigo_estrutura='PNP1-EST', estrutura=estrutura
    )
    MatriculaPNP.objects.filter(matricula='PNPMAT1').update(
        cpf='000.000.000-00', curso='Técnico em Informática', unidade=unidade.nome, codigo_estrutura='PNP1-EST', estrutura=estrutura
    )

    return {
        'unidade': unidade,
        'unidade_pendente': unidade_pendente,
        'coletor': coletor,
        'servidor': importado,
        'servidor_livre': livre,
        'aluno': aluno,
        'aluno_livre': aluno_livre,
        'estrutura': estrutura,
    }


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``Page`` autenticada como o coletor de dados da PNP."""

    def _logado():
        return logado(PAPEIS['coletor'])

    return _logado
