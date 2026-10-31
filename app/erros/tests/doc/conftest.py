"""Substrato da rodada de geração da doc de usuário do ``erros``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é o roteiro de uma tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma — doc que descreve um passo
inexistente é pior que doc velha.

Reusa por completo o substrato dos e2e do módulo (``erros/tests/e2e/conftest.py``) — seed dos
quatro servidores com papel, fábrica ``criar_erro``, chamado reclassificável — sem duplicar
nada. Os dois star-imports são obrigatórios e nesta ordem:

1. ``djtools.e2e_fixtures`` traz os nomes **privados** (``_django_db_helper``,
   ``_exige_banco_de_e2e``), que ``import *`` do conftest do e2e não reexportaria — é a
   armadilha documentada em ``djtools/e2e_fixtures.py:53-57``;
2. o conftest do e2e traz ``erros_seed``, ``vinculos_erros``, ``logado_erros`` e as fixtures
   de erro.

**Papéis**: os quatro do e2e cobrem quase tudo — ``interessado`` (quem reporta e acompanha),
``atendente`` e ``atendente_auxiliar`` (Analista, quem atende) e ``gerente`` (Recebedor de
Demandas, quem tria) — mais **um** papel só desta rodada, ``triador``, com os dois grupos.
Ele existe porque "Cancelar por erro de abertura" exige os dois ao mesmo tempo e isso não está
escrito em lugar nenhum: o item aparece no menu para quem é Recebedor de Demandas
(``pode_cancelar_por_erro_de_abertura``, ``erros/models.py:210``), mas o tratamento do
parâmetro mora **dentro** do ``if eh_atendente:`` da view (``erros/views.py:328`` e ``:360``),
que é ``in_group(user, 'Analista')``. Medido: com o ``gerente`` (só Recebedor) o clique navega
e não acontece nada — nem mensagem de erro. Nenhuma tabela de apoio é semeada: as telas do
módulo não dependem de nenhuma.

Rodar::

    DATABASE_HOST=localhost DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db erros/tests/doc/

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI (o job ``gerar-doc`` roda
``pytest -m doc`` sobre o serviço recém-subido, sem flag nenhuma) e as suítes de doc **não**
são idempotentes entre execuções — medido em 05/08/2026 no ``eventos`` (CPF fixo do visitante
já inscrito) e no ``edu`` (vínculos de diretoria já criados). O preço é o seed frio a cada
iteração.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.conf import settings

if TYPE_CHECKING:
    from erros.models import Erro

from djtools.e2e_fixtures import *  # noqa: F403
from erros.tests.e2e.conftest import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores
from erros.tests.e2e.conftest import PAPEIS, criar_erro

DESTINO = Path(settings.BASE_DIR) / 'erros' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# O único papel que a doc precisa e o e2e não tem: Analista **e** Recebedor de Demandas.
# Não é acrescentado ao `gerente` do e2e de propósito — lá a ausência de Analista é o que faz
# os testes de triagem afirmarem a permissão de grupo, e não o acúmulo de papéis.
PAPEIS_DOC = {'triador': '103016'}

SERVIDORES_DOC = {'103016': ('Triador de Erros', ['Servidor', 'Analista', 'Recebedor de Demandas'])}


@pytest.fixture(scope='session')
def doc_seed(erros_seed):
    """``erros_seed`` + o triador, criado antes da primeira request.

    Session-scoped e eager pelo mesmo motivo do conftest do e2e: o cache de permissão é por
    processo, então usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
    criar_servidores(campus('CEN', 'Campus Central'), SERVIDORES_DOC)


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada, aceitando os papéis do e2e e o desta rodada."""
    papeis = PAPEIS | PAPEIS_DOC

    def _logado(papel: str):
        assert papel in papeis, f'papel desconhecido: {papel}; declare em PAPEIS ou PAPEIS_DOC'
        return logado(papeis[papel])

    return _logado


def _assumido(vinculos: dict) -> Erro:
    """Erro do ``interessado`` já assumido pelo ``atendente`` — o ponto de partida das duas
    fixtures abaixo, porque só o atendente atual move a situação."""
    erro = criar_erro(vinculos['interessado'])
    erro.gerenciar_atendente(vinculos['atendente'], forcar_assumir=True)
    return erro


@pytest.fixture
def erro_aguardando_feedback(vinculos_erros) -> Erro:
    """Erro que o atendente devolveu ao informante pedindo mais informação.

    É o único estado em que a caixa de interação troca "Alterar situação" por "Enviar
    feedback" para quem **não** atende (``erros/forms.py:170-175``), e é o que a tarefa de
    acompanhamento documenta. Montado pelo domínio (``gerenciar_situacao``) e não por
    ``update``: é ele que grava o histórico que a linha do tempo mostra.
    """
    erro = _assumido(vinculos_erros)
    erro.gerenciar_situacao(vinculo=vinculos_erros['atendente'], situacao=erro.SITUACAO_AGUARDANDO_FEEDBACK)
    erro.refresh_from_db()
    return erro


@pytest.fixture
def erro_resolvido(vinculos_erros) -> Erro:
    """Erro fechado pelo atendente — o estado em que o informante ganha "O erro persiste?".

    ``get_situacoes_disponiveis`` (``erros/models.py:212``) só devolve ``[REABERTO]``, e só
    para o atendente ou o informante, quando a situação é Resolvido ou Cancelado.
    """
    erro = _assumido(vinculos_erros)
    erro.gerenciar_situacao(vinculo=vinculos_erros['atendente'], situacao=erro.SITUACAO_RESOLVIDO)
    erro.refresh_from_db()
    return erro
