"""Fixtures da rodada que gera as capturas do manual do AE."""

from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from ae.tests.e2e.conftest import *  # noqa: F403
from ae.tests.e2e.conftest import PAPEIS
from ae.tests.e2e.seed import CAMPUS
from djtools.e2e_fixtures import campus, criar_servidores

DESTINO = Path(settings.BASE_DIR) / 'ae' / 'docs' / 'usuario'
capturar = capturas(DESTINO)  # noqa: F405

# Perfis que só o manual precisa; o seed do e2e cria coordenador sistêmico, assistente e aluno.
PAPEIS_DOC = {
    'coordenador_campus': ('103003', 'Coordenador de Atividades Estudantis'),
    'gerente_refeicoes': ('103004', 'Gerente de Refeições'),
}


@pytest.fixture(scope='session')
def ae_doc_seed(ae_seed) -> None:
    criar_servidores(campus(*CAMPUS), {matricula: (f'Doc {grupo}', [grupo]) for matricula, grupo in PAPEIS_DOC.values()})


@pytest.fixture
def logado_doc(logado, ae_doc_seed):
    """Como ``logado_ae``, aceitando também os perfis de ``PAPEIS_DOC``."""

    def _logado(papel: str):
        matricula = PAPEIS.get(papel) or PAPEIS_DOC[papel][0]
        return logado(matricula)

    return _logado
