"""Substrato dos e2e do Saúde: seed por factories, doze papéis e relógio em janeiro de 2019.

O seed é o do behave que o módulo tinha (as antigas ``saude/features/``), agora por factories
(#17486): ``semear_base()`` dá catálogos, permissões e a raiz; ``seed.py`` acrescenta os campi
CEN/CZN, os profissionais com o cargo de cada especialidade, o aluno com turma e matrícula em
período, o chefe de setor, o verificador de passaporte, os cadastros gerais e o paciente
bloqueado. Os papéis são criados de forma eager antes da primeira request para não depender do
cache de permissões.

O relógio é de sessão e parte de 21/01/2019, data fixada pela agenda no behave; isso mantém
coerentes atendimento, bloqueio futuro e sessões Django. Por essa razão cada teste faz login
real, sem ``storage_states``. Os arquivos são uma cadeia: ``test_01`` materializa os
prontuários; os seguintes criam e fecham atendimentos, sempre com estado clínico consumível
próprio, e os últimos cobrem agenda, atividades, relatórios, COVID e cadastros gerais.

Rodar (invocação separada da suíte unitária)::

    TEST_DATABASE_NAME=test_suap_saude_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \
        uv run pytest saude/tests/e2e -m e2e --reuse-db
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from playwright.sync_api import BrowserContext, Page

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import Relogio, aquecer_urlconf

if TYPE_CHECKING:
    from comum.models import User

DATA_BASE = '21/01/2019'
PAPEIS = {
    'coordenador_sistemico': '111001',
    'medico': '111002',
    'odontologo': '111003',
    'enfermeiro': '111004',
    'tecnico_enfermagem': '111005',
    'auxiliar_enfermagem': '111006',
    'fisioterapeuta': '111007',
    'psicologo': '111008',
    'nutricionista': '111009',
    'tecnico_saude_bucal': '111010',
    'aluno': '20191101011111',
    'chefe_setor': '111011',
    'verificador_passaporte': '111012',
}

_MODULO = Path(__file__).resolve().parents[2]
_RELOGIO = Relogio()


@pytest.fixture(scope='session')
def relogio() -> Iterator[Relogio]:
    """Mantém o processo inteiro na data-base, inclusive a thread do servidor."""
    aquecer_urlconf()
    _RELOGIO.congelar(DATA_BASE)
    yield _RELOGIO
    _RELOGIO.descongelar()


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Retoma o relógio quando a coleta volta aos testes do Saúde."""
    _RELOGIO.retomar()


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Impede que janeiro de 2019 vaze para outro módulo e2e."""
    if nextitem is None or not nextitem.path.is_relative_to(_MODULO):
        _RELOGIO.suspender()


@pytest.fixture(autouse=True)
def data_do_modulo(request: pytest.FixtureRequest, relogio: Relogio) -> Iterator[None]:
    """Aplica a data declarada no arquivo ou a data-base do módulo."""
    relogio.congelar(getattr(request.module, 'DATA', DATA_BASE))
    yield
    relogio.descongelar()


@pytest.fixture(scope='session')
def saude_seed(e2e_seed: None, relogio: Relogio) -> None:
    """Monta, sem flush, o substrato idempotente do domínio Saúde sob a data-base."""
    from saude.tests.e2e import seed

    seed.montar()
    relogio.congelar(DATA_BASE)


@pytest.fixture(scope='session')
def papeis(saude_seed: None) -> dict[str, User]:
    """Resolve todos os atores antes da primeira request para aquecer permissões corretamente."""
    from comum.models import User

    usuarios = {matricula: User.objects.filter(username=matricula).first() for matricula in PAPEIS.values()}
    ausentes = [matricula for matricula, usuario in usuarios.items() if usuario is None]
    assert not ausentes, f'papéis ausentes no seed do Saúde: {ausentes}'
    return {matricula: cast('User', usuario) for matricula, usuario in usuarios.items()}


@pytest.fixture
def logado_saude(new_context: Callable[[], BrowserContext], login_ui: Callable[[Page, str], Page], papeis: dict[str, User]) -> Callable[[str], Page]:
    """Devolve ``(papel) -> Page`` com login real, necessário sob relógio congelado."""

    def _logado(papel: str) -> Page:
        matricula = PAPEIS.get(papel, papel)
        assert matricula in papeis, f'papel desconhecido: {papel!r}; declare em PAPEIS'
        contexto = new_context()
        pagina = contexto.new_page()
        pagina.on('dialog', lambda dialog: dialog.accept())
        return login_ui(pagina, matricula)

    return _logado


# O gate lê este dicionário como literal. Só ficam aqui as rotas que o modo 2 não cobre por
# construção: chamada a API externa, ação que muda estado por GET exercitada por botão ou
# ícone, download/PDF/planilha, impressão/preview e rota órfã (sem ponto de entrada em tela).
ROTAS_DISPENSADAS = {
    '/saude/importar_vacinas_rnvacina_profissional/<int:prontuario_id>/': 'consulta a API externa do RN+Vacina; coberta por teste unitário com mock (`saude/tests/test_importacao_rnvacina.py`).',
    '/saude/deletar_vacina/<int:prontuario_id>/<int:vacina_id>/': 'ação que apaga a vacina do cartão por GET; o fluxo a exercita pelo botão "Remover Vacina".',
    '/saude/adicionar_dose/<int:prontuario_id>/<int:vacina_id>/': 'ação que cria a dose por GET; o fluxo a exercita pelo botão "Adicionar Dose" do cartão vacinal.',
    '/saude/adicionar_reforco/<int:prontuario_id>/<int:vacina_id>/': 'ação que cria o reforço por GET; o fluxo a exercita pelo botão "Adicionar Reforço".',
    '/saude/remover_dose/<int:registro_id>/': 'ação que apaga a dose por GET; o fluxo a exercita pelo botão "Remover Dose".',
    '/saude/remover_previsao/<int:vacinacao_id>/': 'ação que apaga o aprazamento por GET; o fluxo a exercita pelo botão "Remover Aprazamento".',
    '/saude/importar_vacinas_rnvacina_autoatendimento/': 'consulta a API externa do RN+Vacina; coberta por teste unitário com mock.',
    '/saude/previsualizar_documento_prontuario/': 'pré-visualização por AJAX que abre um blob de PDF numa janela nova, sem tela persistente para asserir.',
    '/saude/remover_conduta_nutricao/<int:atendimentonutricao_id>/': 'ação que apaga a conduta por GET; o fluxo a exercita pelo ícone de remoção da aba Conduta Nutricional.',
    '/saude/imprimir_plano_alimentar/<int:plano_id>/': 'impressão/preview do plano alimentar; sem tela para asserir além do content-type.',
    '/saude/remover_plano_alimentar/<int:plano_id>/': 'ação que apaga o plano por GET; o fluxo a exercita pelo botão Remover Plano.',
    '/saude/remover_receita/<int:atendimentonutricao_id>/<int:receita_id>/': 'rota órfã: não há ponto de entrada em tela nenhuma — a receita sai junto com o plano alimentar.',
    '/saude/remover_consumo/<int:consumo_id>/': 'ação que apaga o consumo por GET; o fluxo a exercita pelo ícone de remoção do Recordatório alimentar.',
    '/saude/excluir_marcadores_consumo_alimentar/<int:atendimento_id>/': 'ação que apaga os marcadores por GET; o fluxo a exercita pelo botão Remover.',
    '/saude/adicionar_hipotese_fisioterapia/<int:atendimento_id>/': 'rota órfã: não há ponto de entrada em tela nenhuma — a hipótese saiu do fluxo de fisioterapia.',
    '/saude/excluir_encaminhamento_fisioterapia/<int:encaminhamento_id>/': 'ação que apaga o encaminhamento por GET; o fluxo a exercita pelo ícone de remoção da aba Encaminhamento.',
    '/saude/excluir_procedimento_fisioterapia/<int:procedimento_id>/': 'ação que apaga o procedimento por GET; o fluxo a exercita pelo ícone de remoção da aba Procedimentos.',
}
