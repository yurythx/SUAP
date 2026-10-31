"""Fluxo: caixa de processos do processo eletrônico (fronteira de acesso + tela pesada).

Por que este fluxo: ``caixa_processos`` é tela de alto uso, com muitos joins, e já foi alvo
de otimização (734 → ~200 queries). O acesso NÃO é por permissão Django — é por cadeia de
chefia (``@login_required`` só; a regra está dentro da view), então nem superusuário entra
sem ser chefe. É exatamente o tipo de regra que teste de unidade não protege e que quebra
silenciosamente.

Os dois lados são testados: bloqueio para quem não é chefe, e renderização para quem é.
"""

from datetime import timedelta

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL = '/processo_eletronico/caixa_processos/'
# Criados pelo `e2e_seed` de `tests/e2e/conftest.py`.
SERVIDOR_SEM_GRUPO = '7000001'
SERVIDOR_CHEFE = '7000002'
TRECHO_BLOQUEIO = 'Você não possui acesso a caixa de processos'


@pytest.fixture
def tornar_chefe():
    """Devolve ``(matricula) -> Setor`` que dá chefia do próprio setor ao servidor.

    Só o ``setor_suap`` decide a chefia (``Servidor.eh_chefe_do_setor_hoje``); o ``setor``
    SIAPE é obrigatório no model, então vem de ``SetorSiapeFactory``. ``get_or_create`` e
    não a factory de histórico porque ``ServidorFuncaoHistorico`` é único por
    (servidor, data de início) e a suíte e2e nunca dá flush — repetir a run com
    ``--reuse-db`` reencontraria a linha em vez de estourar ``ValidationError``.
    """

    def _tornar_chefe(matricula: str):
        from djtools.utils import get_datetime_now
        from rh.models import Servidor, ServidorFuncaoHistorico
        from rh.tests.factories import FuncaoChefiaFactory, SetorSiapeFactory

        servidor = Servidor.objects.get(matricula=matricula)
        ServidorFuncaoHistorico.objects.get_or_create(
            servidor=servidor,
            funcao=FuncaoChefiaFactory(),
            setor_suap=servidor.setor,
            defaults={'setor': SetorSiapeFactory, 'data_inicio_funcao': get_datetime_now().date() - timedelta(days=30), 'data_fim_funcao': None},
        )
        assert servidor.eh_chefe_do_setor_hoje(servidor.setor), 'a factory de chefia não surtiu efeito'
        return servidor.setor

    return _tornar_chefe


def test_quem_nao_e_chefe_nao_acessa_a_caixa(logado):
    page = logado(SERVIDOR_SEM_GRUPO)
    page.goto(URL)
    expect(page.get_by_text(TRECHO_BLOQUEIO)).to_be_visible()


def test_nem_superusuario_acessa_sem_chefia(logado):
    """Trava a regra: a caixa é por cadeia de chefia, não por ``is_superuser``."""
    page = logado('admin')
    page.goto(URL)
    expect(page.get_by_text(TRECHO_BLOQUEIO)).to_be_visible()


def test_chefe_de_setor_acessa_a_caixa(logado, tornar_chefe):
    tornar_chefe(SERVIDOR_CHEFE)
    page = logado(SERVIDOR_CHEFE)
    page.goto(URL)
    expect(page.get_by_role('heading', name='Caixa de processos')).to_be_visible()
    expect(page.get_by_text(TRECHO_BLOQUEIO)).to_have_count(0)
