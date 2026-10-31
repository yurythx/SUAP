"""Substrato da rodada de geração da doc de usuário do ``eventos``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

Reusa por completo o substrato dos e2e do módulo (``eventos/tests/e2e/conftest.py``) — seed,
papéis, fábricas de evento — sem duplicar nada. Os dois star-imports são obrigatórios e
nesta ordem:

1. ``djtools.e2e_fixtures`` traz os nomes **privados** (``_django_db_helper``,
   ``_exige_banco_de_e2e``), que ``import *`` do conftest do e2e não reexportaria — é a
   armadilha documentada em ``djtools/e2e_fixtures.py:53-57``;
2. o conftest do e2e traz ``eventos_seed``, ``logado_eventos`` e as fixtures de evento.

Rodar::

    DATABASE_PORT=5434 TEST_DATABASE_NAME=test_suap_doc_e2e \\
        DJANGO_SETTINGS_MODULE=suap.settings_test uv run pytest -m doc --create-db eventos/tests/doc/

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI (o job ``gerar-doc`` roda
``pytest -m doc`` sobre o serviço recém-subido, sem flag nenhuma) e esta suíte **não** é
idempotente entre execuções. Medido em 05/08/2026: com ``--reuse-db``,
``test_inscricao_publica_e_confirmacao`` falha na segunda rodada porque o ``CPF_VISITANTE`` já
está inscrito e o passo 2 do wizard (``/eventos/inscricao/2/<pk>/``) renderiza página vazia.
O preço é o seed frio a cada iteração.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from eventos.tests.e2e.conftest import *  # noqa: F403
from djtools.e2e_fixtures import criar_servidores
from eventos.tests.e2e.conftest import PAPEIS, campus_eventos

DESTINO = Path(settings.BASE_DIR) / 'eventos' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Papéis que só a doc precisa — as duas telas fora do grupo "Cadastros" do menu
# (`Atendimentos ao Público` e `Banners`) exigem grupos que nenhum usuário do seed do e2e
# tem. Um usuário só, com os dois grupos, evita um segundo login por tela.
PAPEIS_DOC = {'comunicacao': '155003'}

SERVIDORES_DOC = {'155003': ('Comunicacao Evento', ['Comunicador Social', 'Coordenador de Comunicação Sistêmico'])}


def _nomenclatura_atendimento() -> list[tuple[type, str]]:
    """``(modelo, descrição)`` das cinco tabelas de apoio do atendimento ao público."""
    from eventos.models import AssuntoAtendimento, MotivoAtendimento, PublicoAtendimento, SituacaoAtendimento, TipoAtendimento

    return [
        (TipoAtendimento, 'Presencial'),
        (MotivoAtendimento, 'Informação'),
        (AssuntoAtendimento, 'Processo Seletivo'),
        (PublicoAtendimento, 'Público Externo'),
        (SituacaoAtendimento, 'Concluído'),
    ]


@pytest.fixture(scope='session')
def doc_seed(eventos_seed):
    """``eventos_seed`` + o servidor de comunicação social, criado antes da 1ª request.

    Session-scoped e eager pelo mesmo motivo do conftest do e2e: o cache de permissão é por
    processo, então um usuário que ganha grupo depois do primeiro login continua sem acesso.
    """
    from comum.models import Ano

    criar_servidores(campus_eventos(), SERVIDORES_DOC)
    # As cinco tabelas de `Cadastros::Atendimentos` não existem no seed do módulo (o
    # `dados_basicos_eventos` só cobre as de evento), e sem elas os selects do
    # formulário de atendimento saem vazios e o Salvar não passa da validação.
    for modelo, descricao in _nomenclatura_atendimento():
        modelo.objects.get_or_create(descricao=descricao)
    # `calendario_eventos` (`eventos/views.py:1182`) faz `Ano.objects.get(ano=<ano atual>)`
    # sem defaults: sem esta linha a tela responde `Ano.DoesNotExist` e a rodada documentaria
    # um traceback. Medido em 02/08/2026.
    Ano.objects.get_or_create(ano=date.today().year)


@pytest.fixture
def logado_doc(logado, doc_seed):
    """``(papel) -> Page`` autenticada, aceitando os papéis do e2e e os desta rodada."""
    papeis = PAPEIS | PAPEIS_DOC

    def _logado(papel: str):
        assert papel in papeis, f'papel desconhecido: {papel}; declare em PAPEIS ou PAPEIS_DOC'
        return logado(papeis[papel])

    return _logado
